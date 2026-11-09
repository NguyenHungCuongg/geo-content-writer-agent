"""Workflow LangGraph của UC-09 (Phase 2, Task 7).

Luồng 6 node:
    prompt_set (UC-01) -> plan (ContentCalendar >= 8 bài) -> với từng bài:
        research (UC-02) -> write (UC-03 / revise_uc03) -> fact_check (UC-04, <= 2 vòng)
          -> approve (interrupt chờ người duyệt)
               --approve--> approved -> bài tiếp theo (hoặc END)
               --reject lần 1--> write (revise_uc03) -> fact_check -> approve
               --reject lần 2--> failed -> bài tiếp theo (hoặc END)

Ràng buộc:
- State của LangGraph chỉ chứa dữ liệu JSON (model_dump(mode="json")).
- Node approve không gọi LLM hay ghi trace trước interrupt(), vì LangGraph chạy lại node đó
  từ đầu khi resume (D-15).
"""

from __future__ import annotations

import json
import os
import pickle
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, TypedDict
from uuid import uuid4

from dotenv import load_dotenv
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from agent.article import (
    READER_TERMS,
    Article,
    content_sentences,
    has_number,
    phrase_pattern,
    split_sentences,
)
from agent.claims import ClaimReport, blocking_claims
from agent.kb import BRAND_KIT_PATH, KB, Chunk, MemoryKB, ingest_brand_kit, ingest_miniweb
from agent.llm import LLM, FakeLLM, GeminiLLM, LLMError, LLMResponse, Message, ToolCall
from agent.loop import CHECKPOINT_HEADER, AgentStopped, Checkpoint
from agent.schemas import BrandProfile, Prompt, PromptSet
from agent.tools import Tool
from agent.tools.similarity import load_miniweb_pages
from agent.trace import TRACES_DIR, Tracer
from agent.uc01 import run_uc01
from agent.uc02 import ResearchReport, run_uc02
from agent.uc03 import load_brand, revise_uc03, run_uc03, voice_rules
from agent.uc04 import fact_check_loop
from agent.uc09 import (
    ApprovalBlockedError,
    ApprovalConflictError,
    ApprovalDecision,
    ContentCalendar,
    plan_calendar,
)


class WorkflowState(TypedDict, total=False):
    run_id: str
    brief: str
    topics: list[str]
    brand_profile: dict[str, Any]
    prompt_set: dict[str, Any]
    calendar: dict[str, Any]
    current_index: int
    articles: dict[str, dict[str, Any]]
    reports: dict[str, dict[str, Any]]
    research_reports: dict[str, dict[str, Any]]
    reject_counts: dict[str, int]
    revision_reasons: dict[str, str]
    failed_reasons: dict[str, str]
    auto_approve: bool


# ---------------------------------------------------------------------------
# Checkpointer: PostgresSaver (khi có kết nối Postgres) & FileCheckpointSaver
# ---------------------------------------------------------------------------


class FileCheckpointSaver(InMemorySaver):
    """Checkpointer lưu xuống đĩa cho test/eval offline nhiều tiến trình khi không có Postgres."""

    def __init__(self, path: Path | None = None):
        super().__init__()
        self.path = path
        if self.path is not None and self.path.is_file():
            self._load()

    def _load(self) -> None:
        if self.path is None or not self.path.is_file():
            return
        try:
            st, wr, bl = pickle.loads(self.path.read_bytes())
            for k, ns_map in st.items():
                for ns, v in ns_map.items():
                    self.storage[k][ns].update(v)
            self.writes.update(wr)
            self.blobs.update(bl)
        except Exception:
            pass

    def _save(self) -> None:
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            plain_storage = {
                k: {ns: dict(v) for ns, v in ns_map.items()}
                for k, ns_map in self.storage.items()
            }
            payload = pickle.dumps((plain_storage, dict(self.writes), dict(self.blobs)))
            tmp_path = self.path.with_name(f"{self.path.name}.tmp.{uuid4().hex[:8]}")
            tmp_path.write_bytes(payload)
            tmp_path.replace(self.path)
        except OSError:
            pass

    def put(self, config, checkpoint, metadata, new_versions):
        res = super().put(config, checkpoint, metadata, new_versions)
        self._save()
        return res

    def put_writes(self, config, writes, task_id, task_path=""):
        super().put_writes(config, writes, task_id, task_path)
        self._save()


_UNREACHABLE_DB_URLS: set[str] = set()


def make_checkpointer(
    conn: Any = None,
    *,
    run_id: str | None = None,
    traces_dir: Path | None = None,
) -> BaseCheckpointSaver:
    """Tạo PostgresSaver nếu có connection hoặc DATABASE_URL kết nối được; ngược lại dùng file."""
    if conn is not None:
        saver = PostgresSaver(conn)
        saver.setup()
        return saver

    if not os.getenv("PYTEST_CURRENT_TEST"):
        load_dotenv()
    db_url = os.getenv("DATABASE_URL", "").strip()
    if (
        db_url
        and db_url not in _UNREACHABLE_DB_URLS
        and not os.getenv("UC09_FORCE_FILE_CHECKPOINTER")
    ):
        try:
            from agent.db import connect, migrate

            pg_conn = connect({"DATABASE_URL": db_url})
            migrate(pg_conn)
            saver = PostgresSaver(pg_conn)
            saver.setup()
            return saver
        except Exception:
            _UNREACHABLE_DB_URLS.add(db_url)

    ckpt_dir = traces_dir or TRACES_DIR
    name = f"{run_id or 'uc09'}.ckpt"
    return FileCheckpointSaver(ckpt_dir / name)


# ---------------------------------------------------------------------------
# Helpers nội bộ cho các node của Graph
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _cached_miniweb_pages() -> dict[str, str]:
    return load_miniweb_pages()


@lru_cache(maxsize=1)
def _default_kb() -> MemoryKB:
    kb = MemoryKB()
    ingest_miniweb(kb)
    ingest_brand_kit(kb, BRAND_KIT_PATH)
    return kb


def _prompts_for_item(state: WorkflowState, item: dict[str, Any]) -> list[Prompt]:
    raw_prompts = state.get("prompt_set", {}).get("prompts", [])
    by_id = {p["id"]: Prompt.model_validate(p) for p in raw_prompts}
    picked = [by_id[pid] for pid in item.get("prompt_ids", []) if pid in by_id]
    if not picked and by_id:
        picked = list(by_id.values())[:2]
    if not picked:
        picked = [
            Prompt(
                id="p01",
                text=f"{item['title']} là gì?",
                intent="informational",
                topic=item["title"],
                persona="Khách hàng chung",
                keywords=[item["primary_keyword"]],
                mentions_brand=False,
            )
        ]
    return picked


def _load_article(data: dict[str, Any]) -> Article:
    return Article.model_validate(data)


def _mark_item_failed(
    state: WorkflowState,
    idx: int,
    item_id: str,
    reason_msg: str,
    tracer: Tracer,
) -> dict[str, Any]:
    items = [dict(it) for it in state["calendar"]["items"]]
    items[idx]["status"] = "failed"
    next_idx = idx + 1
    failed_reasons = {**state.get("failed_reasons", {}), item_id: reason_msg}
    if next_idx >= len(items):
        tracer.log(
            "output",
            uc="uc09",
            calendar={"items": items},
            articles=state.get("articles", {}),
        )
    return {
        "calendar": {"items": items},
        "current_index": next_idx,
        "failed_reasons": failed_reasons,
    }


# ---------------------------------------------------------------------------
# build_graph
# ---------------------------------------------------------------------------


def build_graph(
    checkpointer: BaseCheckpointSaver,
    *,
    tracer: Tracer,
    llm: LLM | None = None,
    kb: KB | None = None,
):
    """Dựng StateGraph của UC-09 với 6 node:
    prompt_set -> plan -> research -> write -> fact_check -> approve.
    """
    active_kb = kb if kb is not None else _default_kb()

    def get_llm() -> LLM:
        return llm if llm is not None else GeminiLLM()

    def node_prompt_set(state: WorkflowState) -> dict[str, Any]:
        tracer.log("node", name="prompt_set", status="start", item_id=None)
        if state.get("prompt_set"):
            tracer.log("node", name="prompt_set", status="end", item_id=None)
            return {}
        try:
            profile, pset = run_uc01(
                state.get("brief", ""),
                state.get("topics", []),
                llm=get_llm(),
                tracer=tracer,
            )
        except Exception as e:
            tracer.log(
                "node",
                name="prompt_set",
                status="error",
                item_id=None,
                reason=getattr(e, "reason", type(e).__name__),
                message=str(e),
            )
            raise
        tracer.log("node", name="prompt_set", status="end", item_id=None)
        return {
            "brand_profile": profile.model_dump(mode="json"),
            "prompt_set": pset.model_dump(mode="json"),
        }

    def node_plan(state: WorkflowState) -> dict[str, Any]:
        tracer.log("node", name="plan", status="start", item_id=None)
        if state.get("calendar"):
            tracer.log("node", name="plan", status="end", item_id=None)
            return {"current_index": state.get("current_index", 0)}
        try:
            raw_prompts = state["prompt_set"]["prompts"]
            pset = PromptSet.model_construct(
                prompts=[Prompt.model_validate(p) for p in raw_prompts]
            )
            cal = plan_calendar(pset, llm=get_llm(), tracer=tracer)
        except Exception as e:
            tracer.log(
                "node",
                name="plan",
                status="error",
                item_id=None,
                reason=getattr(e, "reason", type(e).__name__),
                message=str(e),
            )
            raise
        cal_dump = cal.model_dump(mode="json")
        tracer.log("node", name="plan", status="end", item_id=None, calendar=cal_dump)
        return {
            "calendar": cal_dump,
            "current_index": 0,
            "articles": {},
            "reports": {},
            "research_reports": {},
            "reject_counts": {},
            "revision_reasons": {},
            "failed_reasons": {},
        }

    def node_research(state: WorkflowState) -> dict[str, Any]:
        idx = state.get("current_index", 0)
        items = [dict(it) for it in state["calendar"]["items"]]
        if idx >= len(items):
            return {}
        item = items[idx]
        item_id = item["id"]

        tracer.log("node", name="research", status="start", item_id=item_id)
        active_llm = get_llm()
        if hasattr(active_llm, "on_item_step"):
            active_llm.on_item_step(item_id, "research")

        item_prompts = _prompts_for_item(state, item)
        questions = [p.text for p in item_prompts]
        try:
            report = run_uc02(
                item["title"],
                questions,
                prompts=item_prompts,
                kb=active_kb,
                llm=active_llm,
                tracer=tracer,
            )
        except AgentStopped as e:
            tracer.log(
                "node",
                name="research",
                status="error",
                item_id=item_id,
                reason=e.reason,
                message=str(e),
            )
            return _mark_item_failed(state, idx, item_id, str(e), tracer)
        except LLMError as e:
            tracer.log(
                "node",
                name="research",
                status="error",
                item_id=item_id,
                reason="llm_error",
                message=str(e),
            )
            raise

        items[idx]["status"] = "drafting"
        research_reports = {
            **state.get("research_reports", {}),
            item_id: report.model_dump(mode="json"),
        }
        tracer.log("node", name="research", status="end", item_id=item_id)
        return {
            "calendar": {"items": items},
            "research_reports": research_reports,
        }

    def node_write(state: WorkflowState) -> dict[str, Any]:
        idx = state.get("current_index", 0)
        items = [dict(it) for it in state["calendar"]["items"]]
        item = items[idx]
        item_id = item["id"]

        tracer.log("node", name="write", status="start", item_id=item_id)
        active_llm = get_llm()
        if hasattr(active_llm, "on_item_step"):
            active_llm.on_item_step(item_id, "write")

        rev_reason = state.get("revision_reasons", {}).get(item_id)
        existing_art = state.get("articles", {}).get(item_id)

        try:
            pages = _cached_miniweb_pages()
            if rev_reason and existing_art:
                article = revise_uc03(
                    _load_article(existing_art),
                    [rev_reason],
                    kb=active_kb,
                    llm=active_llm,
                    tracer=tracer,
                    pages=pages,
                )
            else:
                item_prompts = _prompts_for_item(state, item)
                article = run_uc03(
                    item["title"],
                    item_prompts,
                    kb=active_kb,
                    llm=active_llm,
                    tracer=tracer,
                    pages=pages,
                )
        except AgentStopped as e:
            tracer.log(
                "node",
                name="write",
                status="error",
                item_id=item_id,
                reason=e.reason,
                message=str(e),
            )
            return _mark_item_failed(state, idx, item_id, str(e), tracer)
        except LLMError as e:
            tracer.log(
                "node",
                name="write",
                status="error",
                item_id=item_id,
                reason="llm_error",
                message=str(e),
            )
            raise

        items[idx]["status"] = "drafting"
        articles = {
            **state.get("articles", {}),
            item_id: article.model_dump(mode="json"),
        }
        revision_reasons = {
            k: v for k, v in state.get("revision_reasons", {}).items() if k != item_id
        }
        tracer.log("node", name="write", status="end", item_id=item_id)
        return {
            "calendar": {"items": items},
            "articles": articles,
            "revision_reasons": revision_reasons,
        }

    def node_fact_check(state: WorkflowState) -> dict[str, Any]:
        idx = state.get("current_index", 0)
        items = [dict(it) for it in state["calendar"]["items"]]
        item = items[idx]
        item_id = item["id"]

        tracer.log("node", name="fact_check", status="start", item_id=item_id)
        active_llm = get_llm()
        if hasattr(active_llm, "on_item_step"):
            active_llm.on_item_step(item_id, "fact_check")

        current_art = _load_article(state["articles"][item_id])
        try:
            checked_art, report = fact_check_loop(
                current_art,
                kb=active_kb,
                llm=active_llm,
                tracer=tracer,
                max_rounds=2,
            )
        except AgentStopped as e:
            tracer.log(
                "node",
                name="fact_check",
                status="error",
                item_id=item_id,
                reason=e.reason,
                message=str(e),
            )
            return _mark_item_failed(state, idx, item_id, str(e), tracer)
        except LLMError as e:
            tracer.log(
                "node",
                name="fact_check",
                status="error",
                item_id=item_id,
                reason="llm_error",
                message=str(e),
            )
            raise

        items[idx]["status"] = "review"
        article_dump = checked_art.model_dump(mode="json")
        report_dump = report.model_dump(mode="json")
        articles = {
            **state.get("articles", {}),
            item_id: article_dump,
        }
        reports = {
            **state.get("reports", {}),
            item_id: report_dump,
        }
        blocked = [c.model_dump(mode="json") for c in blocking_claims(report)]
        tracer.log(
            "decision",
            action="await_approval",
            item_id=item_id,
            title=item["title"],
            blocking=len(blocked),
            blocking_claims=blocked,
            article=article_dump,
            claim_report=report_dump,
            calendar={"items": items},
        )
        tracer.log(
            "node",
            name="fact_check",
            status="end",
            item_id=item_id,
            calendar={"items": items},
        )
        return {
            "calendar": {"items": items},
            "articles": articles,
            "reports": reports,
        }

    def node_approve(state: WorkflowState) -> dict[str, Any]:
        idx = state.get("current_index", 0)
        items = [dict(it) for it in state["calendar"]["items"]]
        item = items[idx]
        item_id = item["id"]

        article_dict = state["articles"][item_id]
        report_dict = state["reports"][item_id]
        report_obj = ClaimReport.model_validate(report_dict)
        blocked = [c.model_dump(mode="json") for c in blocking_claims(report_obj)]

        # LƯU Ý D-15: Không đặt lời gọi LLM hay tracer.log trước interrupt()!
        if state.get("auto_approve") and not blocked:
            decision = ApprovalDecision(
                decision="approve",
                reason="auto_approve",
                reviewer="auto",
            )
        else:
            raw = interrupt({
                "item_id": item_id,
                "title": item["title"],
                "markdown": article_dict["markdown"],
                "claim_report": report_dict,
                "blocking": blocked,
            })
            decision = (
                raw
                if isinstance(raw, ApprovalDecision)
                else ApprovalDecision.model_validate(raw)
            )

        tracer.log("node", name="approve", status="start", item_id=item_id)

        if decision.decision == "approve":
            if blocked:
                tracer.log(
                    "node",
                    name="approve",
                    status="error",
                    item_id=item_id,
                    reason="blocked_by_claims",
                )
                raise ApprovalBlockedError(blocked)

            tracer.log(
                "decision",
                action="approval",
                item_id=item_id,
                reviewer=decision.reviewer,
                decision="approve",
                reason=decision.reason,
            )
            items[idx]["status"] = "approved"
            next_idx = idx + 1
            tracer.log("node", name="approve", status="end", item_id=item_id)
            if next_idx >= len(items):
                tracer.log(
                    "output",
                    uc="uc09",
                    calendar={"items": items},
                    articles=state.get("articles", {}),
                )
            return {
                "calendar": {"items": items},
                "current_index": next_idx,
            }

        # decision == "reject"
        tracer.log(
            "decision",
            action="approval",
            item_id=item_id,
            reviewer=decision.reviewer,
            decision="reject",
            reason=decision.reason,
        )
        count = state.get("reject_counts", {}).get(item_id, 0) + 1
        reject_counts = {**state.get("reject_counts", {}), item_id: count}

        if count >= 2:
            items[idx]["status"] = "failed"
            next_idx = idx + 1
            failed_reasons = {
                **state.get("failed_reasons", {}),
                item_id: f"Từ chối lần 2: {decision.reason}",
            }
            tracer.log("node", name="approve", status="end", item_id=item_id)
            if next_idx >= len(items):
                tracer.log(
                    "output",
                    uc="uc09",
                    calendar={"items": items},
                    articles=state.get("articles", {}),
                )
            return {
                "calendar": {"items": items},
                "current_index": next_idx,
                "reject_counts": reject_counts,
                "failed_reasons": failed_reasons,
            }

        # Từ chối lần 1 -> quay về write (revise_uc03) rồi fact_check
        items[idx]["status"] = "drafting"
        revision_reasons = {
            **state.get("revision_reasons", {}),
            item_id: decision.reason or "Người duyệt yêu cầu chỉnh sửa bài viết",
        }
        tracer.log("node", name="approve", status="end", item_id=item_id)
        return {
            "calendar": {"items": items},
            "reject_counts": reject_counts,
            "revision_reasons": revision_reasons,
        }

    # --- Routing ---

    def route_after_plan(state: WorkflowState) -> str:
        items = state.get("calendar", {}).get("items", [])
        idx = state.get("current_index", 0)
        return "research" if idx < len(items) else END

    def route_after_step(next_node: str):
        def _router(state: WorkflowState) -> str:
            items = state.get("calendar", {}).get("items", [])
            idx = state.get("current_index", 0)
            if idx >= len(items):
                return END
            # Nếu vừa bị đánh dấu failed thì current_index đã nhảy sang bài mới (status="todo")
            if items[idx]["status"] == "todo":
                return "research"
            return next_node

        return _router

    def route_after_approve(state: WorkflowState) -> str:
        items = state.get("calendar", {}).get("items", [])
        idx = state.get("current_index", 0)
        if idx >= len(items):
            return END
        # Nếu bài hiện tại bị từ chối lần 1, status là "drafting" và có revision_reasons
        current_item = items[idx]
        if (
            current_item["status"] == "drafting"
            and state.get("revision_reasons", {}).get(current_item["id"])
        ):
            return "write"
        return "research"

    builder = StateGraph(WorkflowState)
    builder.add_node("prompt_set", node_prompt_set)
    builder.add_node("plan", node_plan)
    builder.add_node("research", node_research)
    builder.add_node("write", node_write)
    builder.add_node("fact_check", node_fact_check)
    builder.add_node("approve", node_approve)

    builder.add_edge(START, "prompt_set")
    builder.add_edge("prompt_set", "plan")
    builder.add_conditional_edges("plan", route_after_plan, {"research": "research", END: END})
    builder.add_conditional_edges(
        "research", route_after_step("write"), {"write": "write", "research": "research", END: END}
    )
    builder.add_conditional_edges(
        "write",
        route_after_step("fact_check"),
        {"fact_check": "fact_check", "research": "research", END: END},
    )
    builder.add_conditional_edges(
        "fact_check",
        route_after_step("approve"),
        {"approve": "approve", "research": "research", END: END},
    )
    builder.add_conditional_edges(
        "approve",
        route_after_approve,
        {"write": "write", "research": "research", END: END},
    )

    return builder.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# Hàm điều khiển chạy / resume / approve trên Graph
# ---------------------------------------------------------------------------


def graph_config(run_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": run_id}, "recursion_limit": 250}


def start_graph(
    graph: Any,
    run_id: str,
    *,
    brief: str = "",
    topics: list[str] | None = None,
    prompt_set: PromptSet | None = None,
    calendar: ContentCalendar | None = None,
    auto_approve: bool = False,
) -> dict[str, Any]:
    """Khởi chạy một run UC-09 mới trên graph với thread_id = run_id."""
    init_state: WorkflowState = {
        "run_id": run_id,
        "brief": brief,
        "topics": topics or ["sơn chống nóng mái tôn"],
        "auto_approve": auto_approve,
    }
    if prompt_set is not None:
        init_state["prompt_set"] = prompt_set.model_dump(mode="json")
    if calendar is not None:
        init_state["calendar"] = calendar.model_dump(mode="json")
        init_state["current_index"] = 0
        init_state["articles"] = {}
        init_state["reports"] = {}
        init_state["research_reports"] = {}
        init_state["reject_counts"] = {}
        init_state["revision_reasons"] = {}
        init_state["failed_reasons"] = {}
    return graph.invoke(init_state, graph_config(run_id))


def resume_graph(
    graph: Any,
    run_id: str,
    *,
    auto_approve: bool | None = None,
) -> dict[str, Any]:
    """Chạy tiếp một run đang dở (sau khi sập tiến trình hoặc lỗi tạm thời) từ checkpoint."""
    cfg = graph_config(run_id)
    snap = graph.get_state(cfg)
    if not snap or not snap.values:
        raise ValueError(f"Không tìm thấy checkpoint cho run_id={run_id}")
    if auto_approve is not None and snap.values.get("auto_approve") != auto_approve:
        graph.update_state(cfg, {"auto_approve": auto_approve})
    if not snap.next:
        return dict(snap.values)
    return graph.invoke(None, cfg)


def validate_approval_state(
    graph: Any,
    run_id: str,
    decision: ApprovalDecision,
    *,
    item_id: str | None = None,
) -> None:
    """Kiểm tra run đang ở trạng thái chờ duyệt tại node approve và không bị claim số liệu chặn."""
    cfg = graph_config(run_id)
    snap = graph.get_state(cfg)
    if not snap or not snap.values or "approve" not in (snap.next or ()):
        raise ApprovalConflictError(f"Run {run_id} hiện không ở trạng thái chờ duyệt")

    values = snap.values
    idx = values.get("current_index", 0)
    items = values.get("calendar", {}).get("items", [])
    if idx >= len(items):
        raise ApprovalConflictError(f"Run {run_id} đã hoàn tất mọi bài trong lịch")

    current_item = items[idx]
    current_id = current_item["id"]
    if item_id is not None and item_id != current_id:
        raise ApprovalConflictError(
            f"Bài {item_id} không còn ở trạng thái chờ duyệt (bài hiện tại: {current_id})"
        )
    if current_item.get("status") != "review":
        raise ApprovalConflictError(
            f"Bài {current_id} đang ở trạng thái {current_item.get('status')}, không phải review"
        )

    if decision.decision == "approve":
        report_dict = values.get("reports", {}).get(current_id)
        if report_dict:
            report_obj = ClaimReport.model_validate(report_dict)
            blocked = [c.model_dump(mode="json") for c in blocking_claims(report_obj)]
            if blocked:
                raise ApprovalBlockedError(blocked)


def approve_graph(
    graph: Any,
    run_id: str,
    decision: ApprovalDecision,
    *,
    item_id: str | None = None,
) -> dict[str, Any]:
    """Gửi quyết định duyệt (approve / reject) cho bài đang dừng ở node approve.

    - Nếu run không chờ ở node approve (hoặc item_id đã được duyệt rồi) -> ApprovalConflictError.
    - Nếu decision == 'approve' nhưng bài còn blocking_claims -> ApprovalBlockedError.
    """
    validate_approval_state(graph, run_id, decision, item_id=item_id)
    return graph.invoke(Command(resume=decision.model_dump(mode="json")), graph_config(run_id))


def start_uc09(
    brief: str,
    topics: list[str],
    *,
    run_id: str | None = None,
    auto_approve: bool = False,
    llm: LLM | None = None,
    kb: KB | None = None,
    conn: Any = None,
    traces_dir: Path | None = None,
) -> dict[str, Any]:
    rid = run_id or uuid4().hex
    tracer = Tracer(rid, traces_dir=traces_dir)
    saver = make_checkpointer(conn, run_id=rid, traces_dir=traces_dir)
    graph = build_graph(saver, tracer=tracer, llm=llm, kb=kb)
    return start_graph(
        graph,
        rid,
        brief=brief,
        topics=topics,
        auto_approve=auto_approve,
    )


def resume_uc09(
    run_id: str,
    *,
    auto_approve: bool | None = None,
    llm: LLM | None = None,
    kb: KB | None = None,
    conn: Any = None,
    traces_dir: Path | None = None,
) -> dict[str, Any]:
    tracer = Tracer(run_id, traces_dir=traces_dir)
    saver = make_checkpointer(conn, run_id=run_id, traces_dir=traces_dir)
    graph = build_graph(saver, tracer=tracer, llm=llm, kb=kb)
    return resume_graph(graph, run_id, auto_approve=auto_approve)


def approve_uc09(
    run_id: str,
    decision: ApprovalDecision,
    *,
    item_id: str | None = None,
    llm: LLM | None = None,
    kb: KB | None = None,
    conn: Any = None,
    traces_dir: Path | None = None,
) -> dict[str, Any]:
    tracer = Tracer(run_id, traces_dir=traces_dir)
    saver = make_checkpointer(conn, run_id=run_id, traces_dir=traces_dir)
    graph = build_graph(saver, tracer=tracer, llm=llm, kb=kb)
    return approve_graph(graph, run_id, decision, item_id=item_id)


# ---------------------------------------------------------------------------
# ScriptedWorkflowLLM: FakeLLM cho test & eval offline của UC-09
# ---------------------------------------------------------------------------

_FILLER_SENTENCES = (
    "Lớp phủ sáng màu phản xạ ánh nắng nên mái hấp thụ ít nhiệt hơn vào buổi trưa.",
    "Trước khi làm, nên vệ sinh bề mặt mái và xử lý chỗ gỉ để lớp phủ bám chắc.",
    "Hiệu quả thực tế còn phụ thuộc hướng nhà, độ thông gió và màu sắc của mái.",
    "Kết hợp che nắng và thông gió thường cho cảm giác dễ chịu hơn so với chỉ làm một cách.",
    "Nên kiểm tra mái định kỳ sau mùa mưa để phát hiện sớm chỗ bong tróc.",
)


def _filler_block(k: int) -> str:
    return " ".join(_FILLER_SENTENCES[(k + i) % len(_FILLER_SENTENCES)] for i in range(3))


class ScriptedWorkflowLLM(FakeLLM):
    """FakeLLM trả lời tự động theo schema cho toàn bộ pipeline UC-01 -> UC-09.

    Hỗ trợ cài đặt lỗi giả lập tại bài cụ thể (crash_at_write_items, stop_at_write_items,
    llm_error_at_write_items) và ép input_tokens cao để kích hoạt compaction (compact_tokens).
    """

    def __init__(
        self,
        kb: MemoryKB,
        *,
        crash_at_write_items: set[str] | None = None,
        stop_at_write_items: set[str] | None = None,
        llm_error_at_write_items: set[str] | None = None,
        compact_tokens: int = 10,
    ):
        super().__init__()
        self.kb = kb
        self.crash_at_write_items = set(crash_at_write_items or ())
        self.stop_at_write_items = set(stop_at_write_items or ())
        self.llm_error_at_write_items = set(llm_error_at_write_items or ())
        self.compact_tokens = compact_tokens
        self.current_item_id: str | None = None
        self.current_step: str | None = None
        self.touched_items: list[str] = []
        self._query = "QCVN 09:2017"
        self._chunk, self._quote = self._pick_tier_a_chunk()

    def _pick_tier_a_chunk(self) -> tuple[Chunk, str]:
        kit = load_brand(BRAND_KIT_PATH)
        banned = voice_rules(kit)["banned_words"]
        avoid = [phrase_pattern(w) for w in [*banned, *READER_TERMS]]
        for q in (self._query, "cool roof", "TCVN", "heat", "roof", "nhiệt độ bề mặt mái"):
            hits = self.kb.search(q, k=10)
            if not hits:
                continue
            for hit in hits:
                if hit.trust_tier != "A":
                    continue
                for sentence in re.split(r"(?<=[.!?])\s+|\n+", hit.text):
                    sentence = sentence.strip().rstrip(".:")
                    if (
                        has_number(sentence)
                        and 30 <= len(sentence) <= 200
                        and "[" not in sentence
                        and len(split_sentences(sentence)) == 1
                        and not any(p.search(sentence) for p in avoid)
                    ):
                        self._query = q
                        return hit, sentence

        chunks_all = getattr(self.kb, "_chunks", {}).values() if hasattr(self.kb, "_chunks") else []
        for c in chunks_all:
            if getattr(c, "trust_tier", None) != "A" or getattr(c, "suspicious", False):
                continue
            for sentence in re.split(r"(?<=[.!?])\s+|\n+", c.text):
                sentence = sentence.strip().rstrip(".:")
                if (
                    has_number(sentence)
                    and 30 <= len(sentence) <= 200
                    and "[" not in sentence
                    and len(split_sentences(sentence)) == 1
                    and not any(p.search(sentence) for p in avoid)
                ):
                    return c, sentence

        raise RuntimeError("Không tìm thấy chunk tier A trong MemoryKB")

    def on_item_step(self, item_id: str, step: str) -> None:
        self.current_item_id = item_id
        self.current_step = step
        if item_id not in self.touched_items:
            self.touched_items.append(item_id)
        if step == "write":
            if item_id in self.crash_at_write_items:
                self.crash_at_write_items.remove(item_id)
                raise RuntimeError(f"Simulated crash at write {item_id}")
            if item_id in self.llm_error_at_write_items:
                self.llm_error_at_write_items.remove(item_id)
                raise LLMError(f"Gemini quota 429 at write {item_id}")

    def generate(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        tools: list[Tool] | None = None,
        schema: type | None = None,
    ) -> LLMResponse:
        self.calls.append({
            "messages": list(messages),
            "system": system,
            "tools": tools,
            "schema": schema,
            "item_id": self.current_item_id,
            "step": self.current_step,
        })

        if self.current_step == "write" and self.current_item_id in self.stop_at_write_items:
            return LLMResponse(text='{"bad_json": true}')

        # 1. Pha hành động (schema is None)
        if schema is None:
            tool_names = {t.name for t in (tools or [])}
            has_tool_msg = any(m.role == "tool" for m in messages)
            already_compacted = any(CHECKPOINT_HEADER in (m.text or "") for m in messages)
            if "kb_search" in tool_names and not has_tool_msg and not already_compacted:
                return LLMResponse(
                    tool_calls=[
                        ToolCall(
                            id="tc-kb",
                            name="kb_search",
                            args={"query": self._query, "k": 10},
                        )
                    ],
                    input_tokens=self.compact_tokens,
                    output_tokens=20,
                )
            return LLMResponse(text="Đã đủ thông tin.", input_tokens=10, output_tokens=10)

        schema_name = getattr(schema, "__name__", "")

        # 2. Checkpoint compaction
        if schema is Checkpoint or schema_name == "Checkpoint":
            ckpt = {
                "goal": "Hoàn thành nghiên cứu và viết bài chuẩn GEO có trích dẫn xác thực",
                "constraints": [
                    "Mọi câu chứa số liệu đều phải có trích dẫn [n] từ kho tri thức",
                    "Trùng lặp 8-gram không vượt quá 5%",
                ],
                "completed_steps": ["Đã gọi kb_search lấy đoạn trích nguồn Tier A"],
                "current_state": f"Đang xử lý bài {self.current_item_id or 'art-01'}",
                "findings": [f"Tìm thấy nguồn {self._chunk.url}"],
                "failed_attempts": [],
                "files": [self._chunk.id],
                "open_risks": ["Cần kiểm tra mật độ từ khoá chính dưới 3%"],
                "next_action": "Chốt kết quả JSON theo đúng schema đầu ra",
            }
            return LLMResponse(
                text=json.dumps(ckpt, ensure_ascii=False),
                input_tokens=20,
                output_tokens=60,
            )

        first_user = messages[0].text if messages else ""

        # 3. UC-01: BrandProfile
        if schema is BrandProfile or schema_name == "BrandProfile":
            m = re.search(r"<brief>\s*(.*?)\s*</brief>", first_user, re.DOTALL)
            brief_text = (m.group(1).strip() if m else "Skyveil")
            quote_word = brief_text.split()[0] if brief_text.split() else "Skyveil"
            profile = {
                "name": "Skyveil",
                "missing_info": ["danh mục sản phẩm chi tiết"],
                "clarifying_questions": ["Thương hiệu có những dòng sản phẩm cụ thể nào?"],
                "sources": {"name": quote_word},
            }
            return LLMResponse(text=json.dumps(profile, ensure_ascii=False),
                               input_tokens=20, output_tokens=40)

        # 4. UC-01: PromptSet
        if schema is PromptSet or schema_name == "PromptSet":
            topic = "sơn chống nóng mái tôn"
            cm = re.search(r"Chủ đề:\s*(\[.*?\])", first_user)
            if cm:
                try:
                    parsed_topics = json.loads(cm.group(1))
                    if parsed_topics:
                        topic = str(parsed_topics[0])
                except Exception:
                    pass
            else:
                tm = re.search(r"<topics>\s*-\s*(.+?)\s*</topics>", first_user, re.DOTALL)
                if tm:
                    topic = tm.group(1).splitlines()[0].strip()
            intents = ("informational", "navigational", "commercial", "transactional")
            prompts = [
                {
                    "id": f"p{i:02d}",
                    "text": f"Câu hỏi thực tế số {i} về giải pháp chống nóng cho mái nhà?",
                    "intent": intents[i % 4],
                    "topic": topic,
                    "persona": "Khách hàng chung",
                    "keywords": [f"chống nóng {i}"],
                    "mentions_brand": False,
                }
                for i in range(1, 33)
            ]
            return LLMResponse(text=json.dumps({"prompts": prompts}, ensure_ascii=False),
                               input_tokens=30, output_tokens=100)

        # 5. UC-09: ContentCalendar
        if schema is ContentCalendar or schema_name == "ContentCalendar":
            items = []
            for i in range(1, 9):
                other1 = f"art-{(i % 8) + 1:02d}"
                other2 = f"art-{((i + 1) % 8) + 1:02d}"
                items.append({
                    "id": f"art-{i:02d}",
                    "week": ((i - 1) % 4) + 1,
                    "title": f"Giải pháp chống nóng mái nhà chuyên đề {i}",
                    "primary_keyword": f"giải pháp chống nóng chuyên đề {i}",
                    "prompt_ids": [f"p{i:02d}", f"p{i + 8:02d}"],
                    "internal_links": [other1, other2],
                    "status": "todo",
                })
            return LLMResponse(text=json.dumps({"items": items}, ensure_ascii=False),
                               input_tokens=30, output_tokens=80)

        # 6. UC-02: ResearchReport
        if schema is ResearchReport or schema_name == "ResearchReport":
            qm = re.search(
                r"<research_questions>\s*(.*?)\s*</research_questions>", first_user, re.DOTALL
            )
            q_lines = [
                line.lstrip("- ").strip()
                for line in (qm.group(1).splitlines() if qm else ["Câu hỏi 1?"])
                if line.strip()
            ]
            rep = {
                "topic": "Chống nóng mái nhà",
                "queries": [
                    "quy chuẩn chống nóng mái",
                    "vật liệu phản xạ nhiệt",
                    "cách nhiệt mái tôn mùa hè",
                ],
                "answers": [
                    {
                        "question": q,
                        "answer": (
                            "Hiện không đủ nguồn dữ liệu trực tiếp trong kho cho câu hỏi này."
                        ),
                        "citations": [],
                        "insufficient": True,
                    }
                    for q in q_lines
                ],
            }
            return LLMResponse(text=json.dumps(rep, ensure_ascii=False),
                               input_tokens=25, output_tokens=50)

        # 7. UC-03 Bước 1: OutlinePlan
        if schema_name == "OutlinePlan":
            pm = re.search(r"<prompts>\s*(.*?)\s*</prompts>", first_user, re.DOTALL)
            pids = re.findall(r'"id":\s*"([^"]+)"', pm.group(1)) if pm else ["p01", "p09"]
            if not pids:
                pids = ["p01"]
            outline = {
                "title": "Giải pháp chống nóng mái tôn hiệu quả và cách chọn",
                "meta_description": "Nguyên lý chống nóng mái tôn và bảng đối chiếu phương án.",
                "primary_keyword": "chống nóng mái tôn",
                "secondary_keywords": ["sơn phản xạ nhiệt", "vật liệu cách nhiệt"],
                "target_prompts": pids,
                "sections": [
                    {
                        "heading": "Nguyên lý giảm nhiệt cho mái nhà",
                        "level": 2,
                        "format": "paragraph",
                        "needs_citation": True,
                        "answer_first": (
                            "Lớp phủ sáng màu phản xạ phần lớn ánh nắng nên mái hấp thụ ít nhiệt "
                            "hơn vào buổi trưa."
                        ),
                        "points": ["nguyên lý phản xạ", "điều kiện áp dụng"],
                        "prompt_ids": pids,
                    },
                    {
                        "heading": "So sánh các phương án thực tế",
                        "level": 2,
                        "format": "table",
                        "needs_citation": False,
                        "answer_first": (
                            "Mỗi cách có ưu nhược điểm riêng, nên chọn theo loại mái và ngân sách."
                        ),
                        "points": ["sơn phản xạ", "che nắng"],
                        "prompt_ids": pids,
                    },
                    {
                        "heading": "Câu hỏi thường gặp",
                        "level": 2,
                        "format": "list",
                        "needs_citation": False,
                        "answer_first": "Một số câu hỏi hay gặp khi xử lý mái nhà.",
                        "points": [],
                        "prompt_ids": [],
                    },
                ],
                "faq": [
                    {
                        "question": "Khi nào nên làm lại lớp phủ?",
                        "answer": "Xem hướng dẫn của nhà sản xuất.",
                        "prompt_ids": pids,
                    },
                    {
                        "question": "Có cần sơn lót không?",
                        "answer": "Xem hướng dẫn của nhà sản xuất.",
                        "prompt_ids": [],
                    },
                    {
                        "question": "Làm vào mùa mưa được không?",
                        "answer": "Xem hướng dẫn của nhà sản xuất.",
                        "prompt_ids": [],
                    },
                    {
                        "question": "Có tự làm được không?",
                        "answer": "Xem hướng dẫn của nhà sản xuất.",
                        "prompt_ids": [],
                    },
                ],
            }
            return LLMResponse(text=json.dumps(outline, ensure_ascii=False),
                               input_tokens=30, output_tokens=90)

        # 8. UC-03 Bước 2: ArticleDraft
        if schema_name == "ArticleDraft":
            om = re.search(r"<outline>\s*(.*?)\s*</outline>", first_user, re.DOTALL)
            outline_data = json.loads(om.group(1)) if om else {
                "title": "Giải pháp chống nóng mái tôn hiệu quả và cách chọn",
                "sections": [
                    {"heading": "Nguyên lý giảm nhiệt cho mái nhà", "format": "paragraph"},
                    {"heading": "So sánh các phương án thực tế", "format": "table"},
                    {"heading": "Câu hỏi thường gặp", "format": "list"},
                ],
                "faq": [
                    {
                        "question": "Khi nào nên làm lại lớp phủ?",
                        "answer": "Xem hướng dẫn của nhà sản xuất.",
                    },
                    {
                        "question": "Có cần sơn lót không?",
                        "answer": "Xem hướng dẫn của nhà sản xuất.",
                    },
                    {
                        "question": "Làm vào mùa mưa được không?",
                        "answer": "Xem hướng dẫn của nhà sản xuất.",
                    },
                    {
                        "question": "Có tự làm được không?",
                        "answer": "Xem hướng dẫn của nhà sản xuất.",
                    },
                ],
            }
            reader = "anh/chị"
            parts = [
                f"# {outline_data['title']}",
                f"Bài này giúp {reader} hiểu rõ cách xử lý mái nhà mùa nắng.",
            ]
            k = 0
            for i, s in enumerate(outline_data["sections"]):
                parts.append(f"## {s['heading']}")
                opener = (
                    f"Câu trả lời ngắn cho {reader}: có cách làm phù hợp, tuỳ điều kiện của mái."
                )
                if i == 0:
                    opener = f"Có. Một nguồn ghi nhận: {self._quote} [1]."
                parts.append(opener)
                if s.get("format") == "table":
                    parts.append(
                        "| Cách làm | Ưu điểm | Lưu ý |\n|---|---|---|\n"
                        "| Sơn phản xạ | Thi công nhanh | Vệ sinh mái kỹ |\n"
                        "| Che nắng | Dễ tự làm | Chọn vật liệu bền |"
                    )
                for _ in range(4):
                    parts.append(_filler_block(k))
                    k += 1
                if s["heading"] == "Câu hỏi thường gặp":
                    for f in outline_data["faq"]:
                        parts += [f"### {f['question']}", f"{f['answer']} {_filler_block(k)}"]
                        k += 1
            markdown = "\n\n".join(parts)
            draft = {
                "markdown": markdown,
                "citations": [
                    {
                        "n": 1,
                        "chunk_id": self._chunk.id,
                        "url": self._chunk.url,
                        "quote": self._quote,
                    }
                ],
                "notes": [],
            }
            return LLMResponse(text=json.dumps(draft, ensure_ascii=False),
                               input_tokens=40, output_tokens=200)

        # 9. UC-04 Bước 1: ClaimExtractionResult
        if schema_name == "ClaimExtractionResult":
            am = re.search(r"<article>\s*(.*?)\s*</article>", first_user, re.DOTALL)
            art_md = am.group(1) if am else ""
            sents = content_sentences(art_md)
            num_sents = [s for s in sents if has_number(s.text)]
            claims = [
                {
                    "claim": s.text,
                    "heading": s.heading,
                    "paragraph": s.paragraph,
                    "has_number": True,
                }
                for s in num_sents
            ]
            if not claims:
                claims.append({
                    "claim": "Lớp phủ phản xạ nhiệt giúp giảm hấp thụ bức xạ mặt trời.",
                    "heading": "Nguyên lý giảm nhiệt cho mái nhà",
                    "paragraph": 0,
                    "has_number": False,
                })
            return LLMResponse(text=json.dumps({"claims": claims}, ensure_ascii=False),
                               input_tokens=25, output_tokens=60)

        # 10. UC-04 Bước 2: EvidenceGatheringResult
        if schema_name == "EvidenceGatheringResult":
            cm = re.search(r"<claims>\s*(.*?)\s*</claims>", first_user, re.DOTALL)
            parsed_claims = json.loads(cm.group(1)) if cm else [{"index": 0}]
            ev_list = [
                {
                    "claim_index": c["index"],
                    "chunk_id": self._chunk.id,
                    "url": self._chunk.url,
                    "quote": self._quote,
                    "trust_tier": "A",
                    "stance": "supports",
                }
                for c in parsed_claims
            ]
            return LLMResponse(text=json.dumps({"evidence": ev_list}, ensure_ascii=False),
                               input_tokens=25, output_tokens=60)

        raise AssertionError(f"ScriptedWorkflowLLM chưa hỗ trợ schema: {schema}")
