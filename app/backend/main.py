"""Backend của app: chạy các UC ở tác vụ nền, lưu lịch sử vào bảng `runs`, stream SSE (D-03, D-04).

- POST /runs/uc01 {brief, topics} -> {run_id}
- POST /runs/uc02 {topic, questions} -> {run_id}
- POST /runs/uc03 {topic, prompts} -> {run_id}; prompts lấy từ PromptSet của một run UC-01
- POST /runs/uc04 {article} -> {run_id}
- POST /runs/uc09 {brief, topics, auto_approve?} -> {run_id}
- POST /runs/{run_id}/approval {decision, reason, reviewer} -> 202 (409 khi bị chặn)
- POST /runs/{run_id}/resume -> 202
- GET /runs -> [{run_id, uc, status, created_at}] (mới nhất trước)
- GET /runs/{run_id}/events -> mỗi message SSE là một trace event dạng JSON; đóng stream sau
  event `output` hoặc `error` (hoặc khi tác vụ nền tạm dừng chờ người duyệt). Run không còn trong
  RAM (server đã khởi động lại) thì phát lại từ traces/<run_id>.jsonl (D-04).

Chạy từ gốc repo (skill được đọc theo đường dẫn trong repo):
    uvicorn app.backend.main:app --reload
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterable, AsyncIterator, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi import Path as UrlPath
from fastapi.responses import JSONResponse
from fastapi.sse import EventSourceResponse
from pydantic import BaseModel, Field

from agent import trace as trace_mod
from agent.article import Article
from agent.graph import (
    approve_graph,
    build_graph,
    graph_config,
    make_checkpointer,
    resume_graph,
    start_graph,
    validate_approval_state,
)
from agent.kb import KB, MemoryKB
from agent.llm import LLM
from agent.schemas import Prompt
from agent.trace import TRACES_DIR as _DEFAULT_TRACES_DIR
from agent.trace import Tracer
from agent.uc01 import run_uc01
from agent.uc02 import run_uc02
from agent.uc03 import run_uc03
from agent.uc04 import run_uc04
from agent.uc09 import (
    ApprovalBlockedError,
    ApprovalConflictError,
    ApprovalDecision,
)

MAX_BRIEF_CHARS = 20_000
POLL_S = 0.2
TERMINAL = {"output", "error"}
# run_id là uuid4().hex. Chặn mọi dạng khác vì run_id được ghép vào đường dẫn file trace.
RUN_ID_PATTERN = r"^[0-9a-f]{32}$"

# Cho phép test monkeypatch `main.TRACES_DIR`; mặc định theo `agent.trace.TRACES_DIR`.
TRACES_DIR: Path = _DEFAULT_TRACES_DIR

# Run đang chạy giữ trong RAM để stream trực tiếp qua tracer.events; lịch sử nằm ở bảng runs.
RUNS: dict[str, Tracer] = {}
ACTIVE_TASKS: set[str] = set()
_UNREACHABLE_DB_URLS: set[str] = set()

log = logging.getLogger(__name__)
app = FastAPI(title="GEO Content Writer Agent")


def _active_db_url() -> str:
    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url or db_url in _UNREACHABLE_DB_URLS:
        return ""
    return db_url


def _traces_dir() -> Path:
    if TRACES_DIR != _DEFAULT_TRACES_DIR:
        return TRACES_DIR
    return trace_mod.TRACES_DIR


def _read_trace_file(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:  # dòng trống, hoặc dòng ghi dở khi server tắt
            continue
    return events


def _infer_status_from_events(events: list[dict[str, Any]], *, is_active: bool = False) -> str:
    if not events:
        return "running"
    last = events[-1]
    if last.get("event") == "output":
        return "done"
    if last.get("event") == "error":
        return "failed"
    # Kiểm tra xem có đang dừng ở await_approval chưa được trả lời không
    await_count = sum(
        1 for e in events if e.get("event") == "decision" and e.get("action") == "await_approval"
    )
    approval_count = sum(
        1 for e in events if e.get("event") == "decision" and e.get("action") == "approval"
    )
    if await_count > approval_count and not is_active:
        return "awaiting_approval"
    return "running"


def _infer_uc_from_events(events: list[dict[str, Any]]) -> str:
    for e in events:
        if e.get("uc") in {"uc01", "uc02", "uc03", "uc04", "uc09"}:
            return str(e["uc"])
        if e.get("event") == "node":
            return "uc09"
        if e.get("event") == "input":
            if "questions" in e:
                return "uc02"
            if "prompts" in e or "revise" in e:
                return "uc03"
            if "article_title" in e:
                return "uc04"
            if "brief" in e:
                return "uc01"
        if e.get("event") == "output":
            if "calendar" in e:
                return "uc09"
            if "article" in e:
                return "uc03"
            if "report" in e and isinstance(e["report"], dict):
                return "uc04" if "claims" in e["report"] else "uc02"
            if "prompt_set" in e:
                return "uc01"
    return "uc01"


# ---------------------------------------------------------------------------
# Lưu trữ lịch sử run: bảng `runs` trong Postgres + index local trong _traces_dir()
# ---------------------------------------------------------------------------


def _runs_index_path() -> Path:
    return _traces_dir() / "runs_index.jsonl"


def _record_run(
    run_id: str, uc: str, status: str, input_data: dict[str, Any] | None = None
) -> None:
    now_iso = datetime.now(UTC).isoformat()
    # 1. Ghi index local để test offline không có Postgres vẫn đọc được sau khi xoá RUNS
    try:
        idx_path = _runs_index_path()
        idx_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "run_id": run_id,
            "uc": uc,
            "status": status,
            "created_at": now_iso,
        }
        with idx_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass

    # 2. Ghi vào bảng `runs` trên Postgres khi có DATABASE_URL
    db_url = _active_db_url()
    if not db_url:
        return
    try:
        from agent.db import connect, migrate

        with connect({"DATABASE_URL": db_url}) as conn:
            migrate(conn)
            if input_data is not None:
                conn.execute(
                    """
                    INSERT INTO runs (run_id, uc, status, input, created_at)
                    VALUES (%s, %s, %s, %s::jsonb, %s)
                    ON CONFLICT (run_id) DO UPDATE
                    SET status = EXCLUDED.status,
                        input = COALESCE(EXCLUDED.input, runs.input)
                    """,
                    (run_id, uc, status, json.dumps(input_data, ensure_ascii=False), now_iso),
                )
            else:
                conn.execute(
                    "UPDATE runs SET status = %s WHERE run_id = %s",
                    (status, run_id),
                )
    except Exception:
        _UNREACHABLE_DB_URLS.add(db_url)
        log.debug("Không ghi được bảng runs Postgres, dùng fallback file trace", exc_info=True)


def run_output(run_id: str) -> dict[str, Any] | None:
    """Lấy event `output` của một run (từ RAM hoặc file trace), để UC sau lấy kết quả UC trước."""
    events: list[dict[str, Any]]
    if tracer := RUNS.get(run_id):
        events = list(tracer.events)
    else:
        events = _read_trace_file(_traces_dir() / f"{run_id}.jsonl")
    for event in reversed(events):
        if event.get("event") == "output":
            return event
    return None


@app.get("/runs")
def list_runs() -> list[dict[str, Any]]:
    """Trả danh sách lịch sử các run `[{run_id, uc, status, created_at}]`, mới nhất trước."""
    by_id: dict[str, dict[str, Any]] = {}

    # 1. Đọc từ bảng `runs` trong Postgres nếu có kết nối
    db_url = _active_db_url()
    if db_url:
        try:
            from agent.db import connect, migrate

            with connect({"DATABASE_URL": db_url}) as conn:
                migrate(conn)
                rows = conn.execute(
                    "SELECT run_id, uc, status, created_at FROM runs ORDER BY created_at DESC"
                ).fetchall()
                for rid, uc, status, created_at in rows:
                    ts = (
                        created_at.isoformat()
                        if hasattr(created_at, "isoformat")
                        else str(created_at or "")
                    )
                    by_id[str(rid)] = {
                        "run_id": str(rid),
                        "uc": str(uc or "uc01"),
                        "status": str(status or "running"),
                        "created_at": ts,
                    }
        except Exception:
            _UNREACHABLE_DB_URLS.add(db_url)
            log.debug("Không đọc được bảng runs Postgres, dùng fallback file trace", exc_info=True)

    # 2. Đọc từ runs_index.jsonl trong _traces_dir()
    idx_path = _runs_index_path()
    if idx_path.is_file():
        for line in idx_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            rid = rec.get("run_id")
            if not rid:
                continue
            if rid not in by_id:
                by_id[rid] = {
                    "run_id": rid,
                    "uc": rec.get("uc", "uc01"),
                    "status": rec.get("status", "running"),
                    "created_at": rec.get("created_at", ""),
                }
            else:
                by_id[rid]["status"] = rec.get("status", by_id[rid]["status"])

    # 3. Quét thêm các file trace <run_id>.jsonl trong _traces_dir() và đồng bộ trạng thái thực tế
    tdir = _traces_dir()
    if tdir.is_dir():
        for path in tdir.glob("*.jsonl"):
            rid = path.stem
            if len(rid) != 32:
                continue
            evs = _read_trace_file(path)
            if not evs:
                continue
            inferred_status = _infer_status_from_events(evs, is_active=(rid in ACTIVE_TASKS))
            if rid not in by_id:
                by_id[rid] = {
                    "run_id": rid,
                    "uc": _infer_uc_from_events(evs),
                    "status": inferred_status,
                    "created_at": str(evs[0].get("ts", "")),
                }
            else:
                by_id[rid]["status"] = inferred_status

    # 4. Cập nhật từ các run đang nằm trong RAM (RUNS)
    for rid, tracer in list(RUNS.items()):
        evs = list(tracer.events)
        if not evs:
            continue
        inferred_status = _infer_status_from_events(evs, is_active=(rid in ACTIVE_TASKS))
        if rid not in by_id:
            by_id[rid] = {
                "run_id": rid,
                "uc": _infer_uc_from_events(evs),
                "status": inferred_status,
                "created_at": str(evs[0].get("ts", "")),
            }
        else:
            by_id[rid]["status"] = inferred_status

    items = list(by_id.values())
    items.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return items


# ---------------------------------------------------------------------------
# Dependencies & Khung đăng ký chạy tác vụ nền cho các UC
# ---------------------------------------------------------------------------


def get_llm() -> LLM | None:
    """None: mỗi UC tự tạo GeminiLLM từ .env. Test thay bằng FakeLLM qua dependency_overrides."""
    return None


def get_uc03_kb() -> KB | None:
    """Kho cho UC-03/04/09: Postgres nếu có DATABASE_URL, không thì None để dùng kho offline.
    Test thay qua dependency_overrides."""
    db_url = _active_db_url()
    if not db_url:
        return None
    try:
        from agent.db import connect, migrate
        from agent.kb import PgKB

        conn = connect({"DATABASE_URL": db_url})
        migrate(conn)
        return PgKB(conn)
    except Exception:
        _UNREACHABLE_DB_URLS.add(db_url)
        log.warning("không kết nối được Postgres, dùng kho offline", exc_info=True)
        return None


def _run_background_uc(
    uc: str,
    tracer: Tracer,
    fn: Callable[[Tracer], None],
) -> None:
    """Thực thi hàm của UC trong tác vụ nền, đảm bảo ghi event `error` nếu gặp lỗi bất ngờ
    và cập nhật trạng thái vào bảng `runs`."""
    try:
        fn(tracer)
    except Exception as e:
        if not tracer.events or tracer.events[-1]["event"] != "error":
            tracer.log("error", reason="internal_error", message=f"{type(e).__name__}: {e}")
            log.exception("run %s (%s) lỗi", tracer.run_id, uc)
    finally:
        ACTIVE_TASKS.discard(tracer.run_id)
        final_status = _infer_status_from_events(list(tracer.events), is_active=False)
        _record_run(tracer.run_id, uc, final_status)


def _start_uc_run(
    uc: str,
    input_data: dict[str, Any],
    background: BackgroundTasks,
    fn: Callable[[Tracer], None],
) -> dict[str, str]:
    tracer = Tracer(uuid4().hex, traces_dir=_traces_dir())
    RUNS[tracer.run_id] = tracer  # cất trước khi trả về: client mở /events ngay sau đó
    ACTIVE_TASKS.add(tracer.run_id)
    _record_run(tracer.run_id, uc, "running", input_data)
    background.add_task(_run_background_uc, uc, tracer, fn)
    return {"run_id": tracer.run_id}


# ---------------------------------------------------------------------------
# Routes: POST /runs/{uc} (uc01, uc02, uc03, uc04, uc09)
# ---------------------------------------------------------------------------


class RunRequest(BaseModel):
    # Brief rỗng, số chủ đề sai do run_uc01 kiểm, để run bị từ chối vẫn có trace (HR-05).
    brief: str = Field(max_length=MAX_BRIEF_CHARS)
    topics: list[str]


@app.post("/runs/uc01")
def create_run_uc01(
    req: RunRequest,
    background: BackgroundTasks,
    llm: Annotated[LLM | None, Depends(get_llm)],
) -> dict[str, str]:
    return _start_uc_run(
        "uc01",
        req.model_dump(mode="json"),
        background,
        lambda tracer: execute_run(req, llm, tracer),
    )


def execute_run(req: RunRequest, llm: LLM | None, tracer: Tracer) -> None:
    """Chạy UC-01; lỗi nào cũng phải kết thúc trace bằng event `error`, nếu không stream chờ mãi."""
    try:
        run_uc01(req.brief, req.topics, llm=llm, tracer=tracer)
    except Exception as e:
        if not tracer.events or tracer.events[-1]["event"] != "error":
            tracer.log("error", reason="internal_error", message=f"{type(e).__name__}: {e}")
            log.exception("run %s lỗi", tracer.run_id)


class UC02RunRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=1000)
    questions: list[str] = Field(min_length=1, max_length=20)


@app.post("/runs/uc02")
def create_run_uc02(
    req: UC02RunRequest,
    background: BackgroundTasks,
    llm: Annotated[LLM | None, Depends(get_llm)],
) -> dict[str, str]:
    return _start_uc_run(
        "uc02",
        req.model_dump(mode="json"),
        background,
        lambda tracer: execute_run_uc02(req, llm, tracer),
    )


def execute_run_uc02(req: UC02RunRequest, llm: LLM | None, tracer: Tracer) -> None:
    """Chạy UC-02 trong tác vụ nền."""
    try:
        db_url = os.getenv("DATABASE_URL")
        kb: KB
        if db_url:
            try:
                from agent.db import connect, migrate
                from agent.kb import PgKB

                conn = connect({"DATABASE_URL": db_url})
                migrate(conn)
                kb = PgKB(conn)
            except Exception:
                kb = MemoryKB()
        else:
            kb = MemoryKB()
        run_uc02(req.topic, req.questions, kb=kb, llm=llm, tracer=tracer)
    except Exception as e:
        if not tracer.events or tracer.events[-1]["event"] != "error":
            tracer.log("error", reason="internal_error", message=f"{type(e).__name__}: {e}")
            log.exception("run uc02 %s lỗi", tracer.run_id)


class UC03RunRequest(BaseModel):
    # Kiểm sâu (prompt trùng id, quá nhiều prompt) do run_uc03 làm, để run bị từ chối có trace.
    topic: str = Field(min_length=1, max_length=1000)
    prompts: list[Prompt] = Field(min_length=1, max_length=50)


@app.post("/runs/uc03")
def create_run_uc03(
    req: UC03RunRequest,
    background: BackgroundTasks,
    llm: Annotated[LLM | None, Depends(get_llm)],
    kb: Annotated[KB | None, Depends(get_uc03_kb)],
) -> dict[str, str]:
    return _start_uc_run(
        "uc03",
        req.model_dump(mode="json"),
        background,
        lambda tracer: execute_run_uc03(req, llm, kb, tracer),
    )


def execute_run_uc03(req: UC03RunRequest, llm: LLM | None, kb: KB | None, tracer: Tracer) -> None:
    """Chạy UC-03 trong tác vụ nền; lỗi nào cũng kết thúc trace bằng event `error`."""
    try:
        run_uc03(req.topic, req.prompts, kb=kb, llm=llm, tracer=tracer)
    except Exception as e:
        if not tracer.events or tracer.events[-1]["event"] != "error":
            tracer.log("error", reason="internal_error", message=f"{type(e).__name__}: {e}")
            log.exception("run uc03 %s lỗi", tracer.run_id)


class UC04RunRequest(BaseModel):
    article: Article


@app.post("/runs/uc04")
def create_run_uc04(
    req: UC04RunRequest,
    background: BackgroundTasks,
    llm: Annotated[LLM | None, Depends(get_llm)],
    kb: Annotated[KB | None, Depends(get_uc03_kb)],
) -> dict[str, str]:
    return _start_uc_run(
        "uc04",
        req.model_dump(mode="json"),
        background,
        lambda tracer: execute_run_uc04(req, llm, kb, tracer),
    )


def execute_run_uc04(req: UC04RunRequest, llm: LLM | None, kb: KB | None, tracer: Tracer) -> None:
    """Chạy UC-04 trong tác vụ nền; lỗi nào cũng kết thúc trace bằng event `error`."""
    try:
        run_uc04(req.article, kb=kb, llm=llm, tracer=tracer)
    except Exception as e:
        if not tracer.events or tracer.events[-1]["event"] != "error":
            tracer.log("error", reason="internal_error", message=f"{type(e).__name__}: {e}")
            log.exception("run uc04 %s lỗi", tracer.run_id)


class UC09RunRequest(BaseModel):
    brief: str = Field(max_length=MAX_BRIEF_CHARS)
    topics: list[str]
    auto_approve: bool = False


@app.post("/runs/uc09")
def create_run_uc09(
    req: UC09RunRequest,
    background: BackgroundTasks,
    llm: Annotated[LLM | None, Depends(get_llm)],
    kb: Annotated[KB | None, Depends(get_uc03_kb)],
) -> dict[str, str]:
    return _start_uc_run(
        "uc09",
        req.model_dump(mode="json"),
        background,
        lambda tracer: execute_run_uc09(req, llm, kb, tracer),
    )


def execute_run_uc09(req: UC09RunRequest, llm: LLM | None, kb: KB | None, tracer: Tracer) -> None:
    """Chạy workflow LangGraph của UC-09 trong tác vụ nền."""
    try:
        saver = make_checkpointer(run_id=tracer.run_id, traces_dir=_traces_dir())
        graph = build_graph(saver, tracer=tracer, llm=llm, kb=kb)
        start_graph(
            graph,
            tracer.run_id,
            brief=req.brief,
            topics=req.topics,
            auto_approve=req.auto_approve,
        )
    except Exception as e:
        if not tracer.events or tracer.events[-1]["event"] != "error":
            tracer.log("error", reason="internal_error", message=f"{type(e).__name__}: {e}")
            log.exception("run uc09 %s lỗi", tracer.run_id)


@app.post("/runs/{run_id}/approval", status_code=202)
def approve_run(
    run_id: Annotated[str, UrlPath(pattern=RUN_ID_PATTERN)],
    decision: ApprovalDecision,
    background: BackgroundTasks,
    llm: Annotated[LLM | None, Depends(get_llm)],
    kb: Annotated[KB | None, Depends(get_uc03_kb)],
) -> JSONResponse:
    """Gửi quyết định duyệt (approve / reject) cho bài đang dừng chờ duyệt của UC-09.

    - Run không chờ duyệt -> 409.
    - approve khi blocking_claims khác rỗng -> 409 kèm danh sách claim chặn.
    """
    if run_id in ACTIVE_TASKS:
        raise HTTPException(409, f"Run {run_id} đang thực thi, chưa ở trạng thái chờ duyệt")

    tracer = RUNS.get(run_id)
    if tracer is None:
        tracer = Tracer(run_id, traces_dir=_traces_dir())
    saver = make_checkpointer(run_id=run_id, traces_dir=_traces_dir())
    graph = build_graph(saver, tracer=tracer, llm=llm, kb=kb)

    try:
        validate_approval_state(graph, run_id, decision)
    except ApprovalBlockedError as e:
        raise HTTPException(
            409,
            detail={
                "message": str(e),
                "blocking_claims": e.blocking,
                "claims": e.blocking,
            },
        ) from e
    except ApprovalConflictError as e:
        raise HTTPException(409, detail=str(e)) from e

    RUNS[run_id] = tracer
    ACTIVE_TASKS.add(run_id)
    _record_run(run_id, "uc09", "running")
    background.add_task(
        _run_background_uc,
        "uc09",
        tracer,
        lambda t: execute_approve_uc09(run_id, decision, llm, kb, t),
    )
    return JSONResponse({"run_id": run_id, "status": "accepted"}, status_code=202)


def execute_approve_uc09(
    run_id: str,
    decision: ApprovalDecision,
    llm: LLM | None,
    kb: KB | None,
    tracer: Tracer,
) -> None:
    try:
        saver = make_checkpointer(run_id=run_id, traces_dir=_traces_dir())
        graph = build_graph(saver, tracer=tracer, llm=llm, kb=kb)
        approve_graph(graph, run_id, decision)
    except Exception as e:
        if not tracer.events or tracer.events[-1]["event"] != "error":
            tracer.log("error", reason="internal_error", message=f"{type(e).__name__}: {e}")
            log.exception("approve uc09 %s lỗi", run_id)


@app.post("/runs/{run_id}/resume", status_code=202)
def resume_run(
    run_id: Annotated[str, UrlPath(pattern=RUN_ID_PATTERN)],
    background: BackgroundTasks,
    llm: Annotated[LLM | None, Depends(get_llm)],
    kb: Annotated[KB | None, Depends(get_uc03_kb)],
) -> JSONResponse:
    """Chạy tiếp một run UC-09 đang dở từ checkpoint."""
    if run_id in ACTIVE_TASKS:
        raise HTTPException(409, f"Run {run_id} đang chạy")

    tracer = RUNS.get(run_id)
    if tracer is None:
        tracer = Tracer(run_id, traces_dir=_traces_dir())
    saver = make_checkpointer(run_id=run_id, traces_dir=_traces_dir())
    graph = build_graph(saver, tracer=tracer, llm=llm, kb=kb)
    snap = graph.get_state(graph_config(run_id))
    if not snap or not snap.values:
        raise HTTPException(404, f"Không tìm thấy checkpoint cho run {run_id}")

    RUNS[run_id] = tracer
    ACTIVE_TASKS.add(run_id)
    _record_run(run_id, "uc09", "running")
    background.add_task(
        _run_background_uc,
        "uc09",
        tracer,
        lambda t: execute_resume_uc09(run_id, llm, kb, t),
    )
    return JSONResponse({"run_id": run_id, "status": "accepted"}, status_code=202)


def execute_resume_uc09(
    run_id: str,
    llm: LLM | None,
    kb: KB | None,
    tracer: Tracer,
) -> None:
    try:
        saver = make_checkpointer(run_id=run_id, traces_dir=_traces_dir())
        graph = build_graph(saver, tracer=tracer, llm=llm, kb=kb)
        resume_graph(graph, run_id)
    except Exception as e:
        if not tracer.events or tracer.events[-1]["event"] != "error":
            tracer.log("error", reason="internal_error", message=f"{type(e).__name__}: {e}")
            log.exception("resume uc09 %s lỗi", run_id)


# ---------------------------------------------------------------------------
# Stream SSE: GET /runs/{run_id}/events
# ---------------------------------------------------------------------------


def _is_terminal(event: dict[str, Any], events: list[dict[str, Any]]) -> bool:
    kind = event.get("event")
    if kind == "error":
        return True
    if kind == "output":
        is_uc09 = any(e.get("event") == "node" or e.get("uc") == "uc09" for e in events)
        if is_uc09:
            return event.get("uc") == "uc09" or "calendar" in event
        return True
    return False


async def follow(
    events: list[dict], live: bool | Callable[[], bool] = True
) -> AsyncIterator[dict]:
    """Phát lần lượt các event; dừng sau `output`/`error` cuối của run. `live`: chờ event mới."""
    sent = 0
    while True:
        while sent < len(events):
            event = events[sent]
            sent += 1
            yield event
            if _is_terminal(event, events):
                return
        still_live = live() if callable(live) else live
        if not still_live and sent >= len(events):
            return
        await asyncio.sleep(POLL_S)


def find_events(
    run_id: Annotated[str, UrlPath(pattern=RUN_ID_PATTERN)],
) -> tuple[list[dict], bool | Callable[[], bool]]:
    """Dependency: tìm run trước khi stream bắt đầu, để còn trả được 404.

    Run đang có trong RAM thì theo dõi tiếp khi tác vụ nền đang chạy; không có thì phát lại file
    trace một lần.
    """
    if tracer := RUNS.get(run_id):
        return tracer.events, (lambda: run_id in ACTIVE_TASKS)
    path = _traces_dir() / f"{run_id}.jsonl"
    if not path.exists():
        raise HTTPException(404, "Không tìm thấy run")
    return _read_trace_file(path), False


@app.get("/runs/{run_id}/events", response_class=EventSourceResponse)
async def run_events(
    source: Annotated[tuple[list[dict], bool | Callable[[], bool]], Depends(find_events)],
) -> AsyncIterable[dict]:
    async for event in follow(*source):
        yield event
