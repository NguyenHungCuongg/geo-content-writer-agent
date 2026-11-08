"""Eval UC-09: 6 case trong evals/cases/uc09/, chấm bằng code, ghi report JSON vào evals/results/.

Hai chế độ:
- offline (`--offline`): ScriptedWorkflowLLM + MemoryKB + FileCheckpointSaver. Kiểm tra đầy đủ
  harness LangGraph: lập lịch 8 bài, ngắt tiến trình thật (kill subprocess) khi trace vừa ghi
  node write start rồi resume từ checkpoint, nén ngữ cảnh (compaction 5 mục), và cổng duyệt
  của người (approve / reject 2 lần).
- live: Gemini thật qua workflow LangGraph.

Chạy:
    python -m evals.uc09 --all --offline
    python -m evals.uc09 --all
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from agent.claims import ClaimReport, blocking_claims
from agent.graph import (
    FileCheckpointSaver,
    ScriptedWorkflowLLM,
    approve_graph,
    build_graph,
    graph_config,
    resume_graph,
    start_graph,
)
from agent.kb import BRAND_KIT_PATH, MemoryKB, ingest_brand_kit, ingest_miniweb
from agent.llm import LLMError
from agent.loop import AgentStopped, check_checkpoint
from agent.schemas import Prompt, PromptSet
from agent.tools import dedupe
from agent.trace import Tracer
from agent.uc09 import ApprovalDecision, ContentCalendar

ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = ROOT / "evals" / "cases" / "uc09"
RESULTS_DIR = ROOT / "evals" / "results"
REQUIRED = {"id", "topic", "scenario", "expect"}


@lru_cache(maxsize=1)
def _shared_kb() -> MemoryKB:
    kb = MemoryKB()
    ingest_miniweb(kb)
    ingest_brand_kit(kb, BRAND_KIT_PATH)
    return kb


def offline_embedder(texts: list[str]) -> list[list[float]]:
    unique = list(dict.fromkeys(texts))
    return [[float(text == item) for item in unique] for text in texts]


@contextmanager
def configured_embedder(live: bool):
    original = dedupe.default_gemini_embedder
    if not live:
        dedupe.default_gemini_embedder = offline_embedder
    try:
        yield
    finally:
        dedupe.default_gemini_embedder = original


def load_cases() -> list[dict[str, Any]]:
    paths = sorted(CASES_DIR.glob("*.yaml"))
    cases = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in paths]
    if not cases:
        raise ValueError(f"Không tìm thấy eval case trong {CASES_DIR}")
    for case in cases:
        if not isinstance(case, dict) or not REQUIRED.issubset(case):
            raise ValueError(f"Eval case UC-09 phải có các trường {sorted(REQUIRED)}")
    ids = [c["id"] for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("ID eval case UC-09 bị trùng")
    return cases


class _PausingWorkflowLLM(ScriptedWorkflowLLM):
    """ScriptedWorkflowLLM tạm dừng ở bước write của bài chỉ định để tiến trình cha kịp kill."""

    def __init__(self, kb: MemoryKB, *, pause_at_write_item: str | None = None, **kwargs: Any):
        super().__init__(kb, **kwargs)
        self.pause_at_write_item = pause_at_write_item

    def on_item_step(self, item_id: str, step: str) -> None:
        super().on_item_step(item_id, step)
        if step == "write" and self.pause_at_write_item == item_id:
            # Lúc này node_write đã ghi {"event": "node", "name": "write", "status": "start"}
            # vào traces/<run_id>.jsonl. Chờ tiến trình cha đọc trace và gọi proc.kill().
            time.sleep(10.0)


def _run_worker(
    run_id: str,
    action: str,
    traces_dir: Path,
    topic: str,
    pause_item: str | None,
) -> int:
    with configured_embedder(live=False):
        kb = _shared_kb()
        tracer = Tracer(run_id, traces_dir=traces_dir)
        saver = FileCheckpointSaver(traces_dir / f"{run_id}.ckpt")
        llm = _PausingWorkflowLLM(kb, pause_at_write_item=pause_item)
        graph = build_graph(saver, tracer=tracer, llm=llm, kb=kb)
        if action == "start":
            start_graph(
                graph,
                run_id,
                brief="Thương hiệu Skyveil chuyên sơn và vật liệu chống nóng mái nhà tại Việt Nam.",
                topics=[topic],
                auto_approve=True,
            )
        else:
            resume_graph(graph, run_id, auto_approve=True)
    return 0


def _spawn_and_kill_at_write(
    run_id: str,
    action: str,
    traces_dir: Path,
    topic: str,
    target_item_id: str,
    timeout: float = 45.0,
) -> bool:
    """Chạy tiến trình con và kill ngay khi trace ghi node write start của target_item_id."""
    trace_file = traces_dir / f"{run_id}.jsonl"
    existing_count = 0
    if trace_file.is_file():
        existing_count = len(trace_file.read_text(encoding="utf-8").splitlines())

    cmd = [
        sys.executable,
        "-m",
        "evals.uc09",
        "--worker-run-id",
        run_id,
        "--worker-action",
        action,
        "--worker-traces-dir",
        str(traces_dir),
        "--worker-topic",
        topic,
        "--worker-pause-item",
        target_item_id,
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + timeout
    killed = False
    try:
        while time.monotonic() < deadline:
            if trace_file.is_file():
                lines = trace_file.read_text(encoding="utf-8").splitlines()
                for line in lines[existing_count:]:
                    if not line.strip():
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if (
                        ev.get("event") == "node"
                        and ev.get("name") == "write"
                        and ev.get("status") == "start"
                        and ev.get("item_id") == target_item_id
                    ):
                        proc.kill()
                        proc.wait(timeout=5)
                        killed = True
                        break
            if killed or proc.poll() is not None:
                break
            time.sleep(0.02)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
    return killed


def _validate_calendar_state(state: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    try:
        raw_prompts = state.get("prompt_set", {}).get("prompts", [])
        pset = PromptSet.model_construct(
            prompts=[Prompt.model_validate(p) for p in raw_prompts]
        )
        ContentCalendar.model_validate(state.get("calendar", {}), context={"prompt_set": pset})
    except Exception as e:
        errors.append(str(e))
    return errors


def _read_trace_events(trace_path: Path) -> list[dict[str, Any]]:
    if not trace_path.is_file():
        return []
    return [
        json.loads(line)
        for line in trace_file_lines(trace_path)
        if line.strip()
    ]


def trace_file_lines(trace_path: Path) -> list[str]:
    return trace_path.read_text(encoding="utf-8").splitlines()


def _run_scenario_full_calendar(
    case: dict[str, Any],
    run_id: str,
    traces_dir: Path,
    *,
    live: bool,
) -> dict[str, bool | str]:
    kb = _shared_kb()
    tracer = Tracer(run_id, traces_dir=traces_dir)
    saver = FileCheckpointSaver(traces_dir / f"{run_id}.ckpt")
    llm = None if live else ScriptedWorkflowLLM(kb)
    graph = build_graph(saver, tracer=tracer, llm=llm, kb=kb)

    state = start_graph(
        graph,
        run_id,
        brief="Thương hiệu Skyveil chuyên sơn chống nóng mái tôn.",
        topics=[case["topic"]],
        auto_approve=True,
    )
    checks: dict[str, bool | str] = {}
    cal_errors = _validate_calendar_state(state)
    checks["calendar_rules"] = True if not cal_errors else "; ".join(cal_errors)

    items = state.get("calendar", {}).get("items", [])
    expect = case["expect"]
    if "min_items" in expect:
        ok = len(items) >= expect["min_items"]
        checks["min_items"] = ok or f"chỉ có {len(items)} bài"
    if "weeks_covered" in expect:
        weeks = {it["week"] for it in items}
        req_weeks = set(expect["weeks_covered"])
        checks["weeks_covered"] = req_weeks.issubset(weeks) or f"thiếu tuần: {req_weeks - weeks}"
    if expect.get("all_approved"):
        not_app = [it["id"] for it in items if it.get("status") != "approved"]
        checks["all_approved"] = not not_app or f"bài chưa approved: {not_app}"

    # Kiểm không còn claim số liệu chưa supported ở các bài approved
    bad_reports = []
    for it in items:
        if it.get("status") == "approved":
            rep = ClaimReport.model_validate(state["reports"][it["id"]])
            if blocking_claims(rep):
                bad_reports.append(it["id"])
    checks["no_blocking_claims"] = not bad_reports or f"bài còn claim chặn: {bad_reports}"
    return checks


def _run_scenario_interrupt(
    case: dict[str, Any],
    run_id: str,
    traces_dir: Path,
    *,
    live: bool,
) -> dict[str, bool | str]:
    checks: dict[str, bool | str] = {}
    kill_targets: list[str] = list(case.get("kill_at_items", ["art-03"]))

    for i, target_id in enumerate(kill_targets):
        action = "start" if i == 0 else "resume"
        killed = _spawn_and_kill_at_write(
            run_id,
            action,
            traces_dir,
            case["topic"],
            target_id,
        )
        checks[f"killed_at_{target_id}"] = killed or f"không kill được tại {target_id}"

    # Resume hoàn tất từ checkpoint đã lưu
    kb = _shared_kb()
    tracer = Tracer(run_id, traces_dir=traces_dir)
    saver = FileCheckpointSaver(traces_dir / f"{run_id}.ckpt")
    llm = None if live else ScriptedWorkflowLLM(kb)
    graph = build_graph(saver, tracer=tracer, llm=llm, kb=kb)
    final_state = resume_graph(graph, run_id, auto_approve=True)

    items = final_state.get("calendar", {}).get("items", [])
    expect = case["expect"]
    if "min_items" in expect:
        checks["min_items"] = len(items) >= expect["min_items"] or f"chỉ có {len(items)} bài"
    if expect.get("no_duplicate_completed_items"):
        ids = [it["id"] for it in items]
        checks["no_duplicate_completed_items"] = (
            len(ids) == len(set(ids)) or f"trùng ID bài: {ids}"
        )
    if "not_rerun_items" in expect:
        # Bài trong not_rerun_items không được gọi LLM trong lần resume cuối
        if llm is not None:
            rerun = [iid for iid in expect["not_rerun_items"] if iid in llm.touched_items]
            checks["not_rerun_items"] = (
                not rerun or f"bài đã xong nhưng bị chạy lại ở lần resume cuối: {rerun}"
            )
        else:
            checks["not_rerun_items"] = True
    if expect.get("all_approved"):
        not_app = [it["id"] for it in items if it.get("status") != "approved"]
        checks["all_approved"] = not not_app or f"bài chưa approved: {not_app}"
    return checks


def _run_scenario_compaction(
    case: dict[str, Any],
    run_id: str,
    traces_dir: Path,
    *,
    live: bool,
) -> dict[str, bool | str]:
    kb = _shared_kb()
    tracer = Tracer(run_id, traces_dir=traces_dir)
    saver = FileCheckpointSaver(traces_dir / f"{run_id}.ckpt")
    threshold = int(case.get("compact_at_tokens", 50))
    old_val = os.environ.get("COMPACT_AT_TOKENS")
    os.environ["COMPACT_AT_TOKENS"] = str(threshold)
    try:
        llm = None if live else ScriptedWorkflowLLM(kb, compact_tokens=threshold * 2)
        graph = build_graph(saver, tracer=tracer, llm=llm, kb=kb)
        state = start_graph(
            graph,
            run_id,
            brief="Thương hiệu Skyveil chuyên sơn chống nóng mái tôn.",
            topics=[case["topic"]],
            auto_approve=True,
        )
    finally:
        if old_val is None:
            os.environ.pop("COMPACT_AT_TOKENS", None)
        else:
            os.environ["COMPACT_AT_TOKENS"] = old_val

    checks: dict[str, bool | str] = {}
    compact_events = [
        e for e in tracer.events if e.get("event") == "decision" and e.get("action") == "compact"
    ]
    min_comp = case["expect"].get("min_compactions", 1)
    checks["min_compactions"] = (
        len(compact_events) >= min_comp
        or f"chỉ có {len(compact_events)} lần compact (cần >= {min_comp})"
    )

    if case["expect"].get("checkpoint_sections_complete"):
        bad_ckpts = []
        for idx, ev in enumerate(compact_events):
            missing = check_checkpoint(ev.get("checkpoint", {}))
            if missing:
                bad_ckpts.append(f"compact[{idx}] thiếu {missing}")
        checks["checkpoint_sections_complete"] = (
            (bool(compact_events) and not bad_ckpts)
            or "; ".join(bad_ckpts or ["không có checkpoint nào"])
        )

    items = state.get("calendar", {}).get("items", [])
    if case["expect"].get("all_approved"):
        not_app = [it["id"] for it in items if it.get("status") != "approved"]
        checks["all_approved"] = not not_app or f"bài chưa approved: {not_app}"
    return checks


def _run_scenario_human_approval(
    case: dict[str, Any],
    run_id: str,
    traces_dir: Path,
    *,
    live: bool,
) -> dict[str, bool | str]:
    kb = _shared_kb()
    tracer = Tracer(run_id, traces_dir=traces_dir)
    saver = FileCheckpointSaver(traces_dir / f"{run_id}.ckpt")
    llm = None if live else ScriptedWorkflowLLM(kb)
    graph = build_graph(saver, tracer=tracer, llm=llm, kb=kb)

    state = start_graph(
        graph,
        run_id,
        brief="Thương hiệu Skyveil chuyên sơn chống nóng mái tôn.",
        topics=[case["topic"]],
        auto_approve=False,
    )
    snap = graph.get_state(graph_config(run_id))
    first_item = state["calendar"]["items"][0]
    waits = (
        first_item["status"] == "review"
        and "approve" in (snap.next or ())
        and any(
            e.get("event") == "decision" and e.get("action") == "await_approval"
            for e in tracer.events
        )
    )
    checks: dict[str, bool | str] = {
        "waits_in_review": waits or f"status={first_item['status']}, next={snap.next}",
    }

    state_after = approve_graph(
        graph,
        run_id,
        ApprovalDecision(decision="approve", reason="Đồng ý xuất bản", reviewer="eval_reviewer"),
        item_id="art-01",
    )
    approved_ok = (
        state_after["calendar"]["items"][0]["status"] == "approved"
        and any(
            e.get("event") == "decision"
            and e.get("action") == "approval"
            and e.get("decision") == "approve"
            and e.get("item_id") == "art-01"
            for e in tracer.events
        )
    )
    checks["approved_after_decision"] = (
        approved_ok or f"status sau approve={state_after['calendar']['items'][0]['status']}"
    )
    return checks


def _run_scenario_human_rejection(
    case: dict[str, Any],
    run_id: str,
    traces_dir: Path,
    *,
    live: bool,
) -> dict[str, bool | str]:
    kb = _shared_kb()
    tracer = Tracer(run_id, traces_dir=traces_dir)
    saver = FileCheckpointSaver(traces_dir / f"{run_id}.ckpt")
    llm = None if live else ScriptedWorkflowLLM(kb)
    graph = build_graph(saver, tracer=tracer, llm=llm, kb=kb)

    state = start_graph(
        graph,
        run_id,
        brief="Thương hiệu Skyveil chuyên sơn chống nóng mái tôn.",
        topics=[case["topic"]],
        auto_approve=False,
    )
    checks: dict[str, bool | str] = {
        "waits_in_review": (
            state["calendar"]["items"][0]["status"] == "review"
            or f"status={state['calendar']['items'][0]['status']}"
        )
    }

    # Từ chối lần 1 -> quay về write (revise_uc03) + fact_check -> dừng lại ở review
    reason = case.get("rejection_reason", "Cần bổ sung bảng so sánh chi phí")
    state_r1 = approve_graph(
        graph,
        run_id,
        ApprovalDecision(decision="reject", reason=reason, reviewer="eval_reviewer"),
        item_id="art-01",
    )
    write_starts_art1 = [
        e
        for e in tracer.events
        if e.get("event") == "node"
        and e.get("name") == "write"
        and e.get("status") == "start"
        and e.get("item_id") == "art-01"
    ]
    revises_ok = (
        state_r1["calendar"]["items"][0]["status"] == "review"
        and state_r1["current_index"] == 0
        and len(write_starts_art1) == 2
    )
    checks["revises_on_first_reject"] = (
        revises_ok
        or f"status={state_r1['calendar']['items'][0]['status']}, writes={len(write_starts_art1)}"
    )

    # Từ chối lần 2 -> đánh dấu failed và chuyển sang art-02
    state_r2 = approve_graph(
        graph,
        run_id,
        ApprovalDecision(decision="reject", reason="Vẫn chưa đạt", reviewer="eval_reviewer"),
        item_id="art-01",
    )
    fails_ok = (
        state_r2["calendar"]["items"][0]["status"] == "failed"
        and state_r2["current_index"] == 1
        and state_r2["calendar"]["items"][1]["status"] == "review"
    )
    checks["fails_on_second_reject"] = (
        fails_ok
        or (
            f"art-01={state_r2['calendar']['items'][0]['status']}, "
            f"idx={state_r2['current_index']}"
        )
    )
    return checks


def run_case(case: dict[str, Any], *, live: bool, traces_dir: Path | None = None) -> dict[str, Any]:
    run_id = uuid4().hex
    started = time.perf_counter()
    result: dict[str, Any] = {
        "case_id": case["id"],
        "run_id": run_id,
        "scenario": case["scenario"],
        "passed": False,
        "checks": {},
        "error": None,
    }

    with tempfile.TemporaryDirectory(prefix="eval_uc09_") as tmp, configured_embedder(live):
        tdir = traces_dir or Path(tmp)
        try:
            scenario = case["scenario"]
            if scenario == "full_calendar":
                checks = _run_scenario_full_calendar(case, run_id, tdir, live=live)
            elif scenario in ("interrupt_and_resume", "interrupt_twice"):
                checks = _run_scenario_interrupt(case, run_id, tdir, live=live)
            elif scenario == "long_session_compaction":
                checks = _run_scenario_compaction(case, run_id, tdir, live=live)
            elif scenario == "human_approval":
                checks = _run_scenario_human_approval(case, run_id, tdir, live=live)
            elif scenario == "human_rejection":
                checks = _run_scenario_human_rejection(case, run_id, tdir, live=live)
            else:
                raise ValueError(f"Scenario không hỗ trợ: {scenario}")

            result["checks"] = checks
            result["passed"] = bool(checks) and all(v is True for v in checks.values())
        except (AgentStopped, LLMError, Exception) as e:
            result["error"] = f"{type(e).__name__}: {e}"

        events = _read_trace_events(tdir / f"{run_id}.jsonl")
        llm_calls = [e for e in events if e.get("event") == "llm_call"]
        result["repairs"] = sum(
            1
            for e in events
            if e.get("event") == "decision" and e.get("action") == "repair"
        )
        result["compactions"] = sum(
            1
            for e in events
            if e.get("event") == "decision" and e.get("action") == "compact"
        )
        result["tokens"] = {
            "input": sum(e.get("input_tokens", 0) for e in llm_calls),
            "output": sum(e.get("output_tokens", 0) for e in llm_calls),
        }

    result["duration_seconds"] = round(time.perf_counter() - started, 3)
    return result


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(results) or 1
    passed = sum(1 for r in results if r["passed"])
    return {
        "total_cases": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": round(passed / n, 4),
        "avg_repairs": round(sum(r.get("repairs", 0) for r in results) / n, 2),
        "avg_tokens_per_case": {
            key: round(sum(r["tokens"][key] for r in results) / n, 1)
            for key in ("input", "output")
        },
        "avg_runtime_seconds": round(sum(r["duration_seconds"] for r in results) / n, 3),
    }


def run_evaluation(
    *,
    live: bool,
    output_dir: Path = RESULTS_DIR,
    case_ids: list[str] | None = None,
) -> dict[str, Any]:
    cases = [c for c in load_cases() if not case_ids or c["id"] in case_ids]
    results = [run_case(case, live=live) for case in cases]
    report = {
        "uc": "uc09",
        "mode": "live" if live else "offline_fixture",
        "created_at": datetime.now(UTC).isoformat(),
        "summary": summarize(results),
        "results": results,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"uc09-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}.json"
    report["result_file"] = str(out)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Chạy eval UC-09")
    parser.add_argument("--all", action="store_true", help="chạy mọi case UC-09")
    parser.add_argument("--case", action="append", default=[], help="chỉ chạy case có id này")
    parser.add_argument("--offline", action="store_true", help="dùng FakeLLM, không gọi Gemini")
    # Tham số nội bộ cho worker subprocess của case interrupt/resume
    parser.add_argument("--worker-run-id", help=argparse.SUPPRESS)
    parser.add_argument("--worker-action", choices=["start", "resume"], help=argparse.SUPPRESS)
    parser.add_argument("--worker-traces-dir", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--worker-topic", default="chống nóng mái nhà", help=argparse.SUPPRESS)
    parser.add_argument("--worker-pause-item", help=argparse.SUPPRESS)

    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    if args.worker_run_id:
        return _run_worker(
            args.worker_run_id,
            args.worker_action or "start",
            args.worker_traces_dir,
            args.worker_topic,
            args.worker_pause_item,
        )

    if not args.all and not args.case:
        parser.error("cần --all hoặc --case <id>")

    report = run_evaluation(live=not args.offline, case_ids=args.case or None)
    s = report["summary"]
    for r in report["results"]:
        status = "PASS" if r["passed"] else "FAIL"
        failed = {k: v for k, v in r["checks"].items() if v is not True}
        print(f"[{status}] {r['case_id']} {r['error'] or failed or ''}")
    print(
        f"{s['passed']}/{s['total_cases']} passed; mode={report['mode']}; "
        f"tokens={s['avg_tokens_per_case']}; avg={s['avg_runtime_seconds']}s/case; "
        f"result={report['result_file']}"
    )
    return 0 if s["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
