"""Backend của app: chạy UC-01 ở tác vụ nền và stream từng bước của agent bằng SSE (D-03).

- POST /runs {brief, topics} -> {run_id}
- GET /runs/{run_id}/events -> mỗi message SSE là một trace event dạng JSON; đóng stream sau
  event `output` hoặc `error`. Run không còn trong RAM (server đã khởi động lại) thì phát lại
  từ traces/<run_id>.jsonl do Task 6 ghi (D-04).

Chạy từ gốc repo (skill được đọc theo đường dẫn trong repo):
    uvicorn app.backend.main:app --reload
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterable, AsyncIterator
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi import Path as UrlPath
from fastapi.sse import EventSourceResponse
from pydantic import BaseModel, Field

from agent.llm import LLM
from agent.trace import Tracer
from agent.uc01 import run_uc01

MAX_BRIEF_CHARS = 20_000
POLL_S = 0.2
TERMINAL = {"output", "error"}
TRACES_DIR = Path(__file__).resolve().parents[2] / "traces"
# run_id là uuid4().hex. Chặn mọi dạng khác vì run_id được ghép vào đường dẫn file trace.
RUN_ID_PATTERN = r"^[0-9a-f]{32}$"

# ponytail: giữ mọi run trong RAM tới khi tắt server; Phase 2 chuyển sang Postgres (D-04).
RUNS: dict[str, Tracer] = {}

log = logging.getLogger(__name__)
app = FastAPI(title="GEO Content Writer Agent")


class RunRequest(BaseModel):
    # Brief rỗng, số chủ đề sai do run_uc01 kiểm, để run bị từ chối vẫn có trace (HR-05).
    brief: str = Field(max_length=MAX_BRIEF_CHARS)
    topics: list[str]


def get_llm() -> LLM | None:
    """None: run_uc01 tự tạo GeminiLLM từ .env. Test thay bằng FakeLLM qua dependency_overrides."""
    return None


@app.post("/runs")
def create_run(
    req: RunRequest,
    background: BackgroundTasks,
    llm: Annotated[LLM | None, Depends(get_llm)],
) -> dict[str, str]:
    tracer = Tracer(uuid4().hex)
    RUNS[tracer.run_id] = tracer  # cất trước khi trả về: client mở /events ngay sau đó
    background.add_task(execute_run, req, llm, tracer)
    return {"run_id": tracer.run_id}


def execute_run(req: RunRequest, llm: LLM | None, tracer: Tracer) -> None:
    """Chạy UC-01; lỗi nào cũng phải kết thúc trace bằng event `error`, nếu không stream chờ mãi."""
    try:
        run_uc01(req.brief, req.topics, llm=llm, tracer=tracer)
    except Exception as e:
        if tracer.events[-1]["event"] != "error":  # lỗi đã biết thì agent đã ghi rồi
            tracer.log("error", reason="internal_error", message=f"{type(e).__name__}: {e}")
        log.exception("run %s lỗi", tracer.run_id)


async def follow(events: list[dict], live: bool = True) -> AsyncIterator[dict]:
    """Phát lần lượt các event; dừng sau `output`/`error`. `live`: chờ event mới khi hết."""
    sent = 0
    while True:
        while sent < len(events):
            event = events[sent]
            sent += 1
            yield event
            if event["event"] in TERMINAL:
                return
        if not live:
            return
        await asyncio.sleep(POLL_S)


def find_events(
    run_id: Annotated[str, UrlPath(pattern=RUN_ID_PATTERN)],
) -> tuple[list[dict], bool]:
    """Dependency: tìm run trước khi stream bắt đầu, để còn trả được 404.

    Run đang có trong RAM thì theo dõi tiếp; không có thì phát lại file trace một lần.
    """
    if tracer := RUNS.get(run_id):
        return tracer.events, True
    path = TRACES_DIR / f"{run_id}.jsonl"
    if not path.exists():
        raise HTTPException(404, "Không tìm thấy run")
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()], False


@app.get("/runs/{run_id}/events", response_class=EventSourceResponse)
async def run_events(
    source: Annotated[tuple[list[dict], bool], Depends(find_events)],
) -> AsyncIterable[dict]:
    async for event in follow(*source):
        yield event
