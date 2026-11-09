"""Run selected UC evaluation modules and write one timestamped report."""

import argparse
import importlib
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from pkgutil import iter_modules

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
EVALS_DIR = ROOT / "evals"
RESULTS_DIR = EVALS_DIR / "results"


def discover_ucs() -> list[str]:
    return sorted(
        name for _, name, is_package in iter_modules([str(EVALS_DIR)])
        if not is_package and re.fullmatch(r"uc\d{2}", name)
    )


def load_cases() -> list[dict]:
    """Backward-compatible shortcut for the UC-01 case loader."""
    from evals.uc01 import load_cases as load_uc01_cases

    return load_uc01_cases()


def _average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def _case_token(result: dict, key: str) -> float | None:
    tokens = result.get("tokens") or {}
    if (value := tokens.get(key)) is not None:
        return value
    if key == "total" and tokens.get("input") is not None and tokens.get("output") is not None:
        return tokens["input"] + tokens["output"]
    return None


def _summarize_results(results: list[dict]) -> dict:
    total = len(results)
    passed = sum(bool(result.get("passed")) for result in results)
    tokens = {
        key: _average([
            value
            for result in results
            if (value := _case_token(result, key)) is not None
        ])
        for key in ("input", "output", "total")
    }
    return {
        "total_cases": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "avg_repairs_per_case": _average([
            result["repairs"] for result in results if result.get("repairs") is not None
        ]),
        "avg_tokens_per_case": tokens,
        "avg_runtime_seconds": _average([
            result.get("duration_seconds", result.get("runtime_seconds"))
            for result in results
            if result.get("duration_seconds", result.get("runtime_seconds")) is not None
        ]),
    }


def _normalize_summary(module_summary: dict, results: list[dict]) -> dict:
    summary = dict(module_summary)
    common = _summarize_results(results)
    aliases = {
        "total_cases": "total_cases",
        "passed": "passed",
        "failed": "failed",
        "pass_rate": "pass_rate",
        "avg_repairs_per_case": "avg_repairs",
        "avg_runtime_seconds": "avg_duration",
    }
    for key, alias in aliases.items():
        if key not in summary:
            summary[key] = summary.get(alias, common[key])

    if "avg_tokens_per_case" not in summary:
        summary["avg_tokens_per_case"] = common["avg_tokens_per_case"]
    else:
        token_summary = dict(summary["avg_tokens_per_case"])
        input_tokens = token_summary.get("input")
        output_tokens = token_summary.get("output")
        token_summary.setdefault(
            "total",
            round(input_tokens + output_tokens, 3)
            if input_tokens is not None and output_tokens is not None
            else None,
        )
        summary["avg_tokens_per_case"] = token_summary
    return summary


def _load_plugin(uc_name: str):
    try:
        module = importlib.import_module(f"evals.{uc_name}")
    except ModuleNotFoundError as error:
        if error.name != f"evals.{uc_name}":
            raise
        return None, f"{uc_name}: chưa có module eval ({error.name}), bỏ qua"

    load = getattr(module, "load_cases", None)
    if not callable(load):
        return None, f"{uc_name}: chưa có load_cases(), bỏ qua"
    try:
        cases = load()
    except (FileNotFoundError, ValueError) as error:
        case_dir = EVALS_DIR / "cases" / uc_name
        has_cases = any(
            path.is_file()
            for pattern in ("*.yaml", "*.yml", "*.json", "*.jsonl")
            for path in case_dir.glob(pattern)
        )
        if has_cases:
            raise
        return None, f"{uc_name}: chưa có case chạy được ({error}), bỏ qua"
    if not cases:
        return None, f"{uc_name}: chưa có case, bỏ qua"

    run_case = getattr(module, "run_case", None)
    summarize = getattr(module, "summarize", None)
    extra_summary = {}

    if uc_name == "uc02" and callable(getattr(module, "run_single_case", None)):
        from agent.kb import MemoryKB, ingest_miniweb

        kb = MemoryKB()
        ingest_miniweb(kb)

        def run_case(case: dict, *, live: bool) -> dict:
            tracers = []
            original_run_uc02 = module.run_uc02

            def capture_tracer(*args, **kwargs):
                if kwargs.get("tracer") is not None:
                    tracers.append(kwargs["tracer"])
                return original_run_uc02(*args, **kwargs)

            module.run_uc02 = capture_tracer
            try:
                result = module.run_single_case(case, live=live, kb=kb)
            finally:
                module.run_uc02 = original_run_uc02

            events = tracers[-1].events if tracers else []
            llm_calls = [event for event in events if event["event"] == "llm_call"]
            result["repairs"] = sum(
                event["event"] == "decision" and event.get("action") == "repair"
                for event in events
            )
            result["tokens"] = {
                key: sum(event.get(f"{key}_tokens", 0) for event in llm_calls)
                for key in ("input", "output")
            }
            result["tokens"]["total"] = (
                result["tokens"]["input"] + result["tokens"]["output"]
            )
            return result

        extra_summary = {"_memory_kb": kb}
        summarize = _summarize_results

    if not callable(run_case) or not callable(summarize):
        return None, f"{uc_name}: eval chưa hỗ trợ contract load_cases/run_case/summarize, bỏ qua"
    return (module, cases, run_case, summarize, extra_summary), None


def _prepare_live_kb():
    from agent.db import connect, migrate
    from agent.kb import PgKB, ingest_miniweb

    load_dotenv(ROOT / ".env")
    conn = connect()
    try:
        migrate(conn, "eval")
        chunks = ingest_miniweb(PgKB(conn))
    except Exception:
        conn.close()
        raise
    return conn, chunks


def _configured_model(live: bool, results: list[dict]) -> str:
    if not live:
        return "fake"
    load_dotenv(ROOT / ".env")
    configured = os.getenv("GEMINI_MODEL")
    if configured:
        return configured
    models = sorted({result["model"] for result in results if result.get("model")})
    return models[0] if len(models) == 1 else "unknown"


def run_evaluation(
    *,
    live: bool = True,
    output_dir: Path = RESULTS_DIR,
    ucs: list[str] | None = None,
) -> dict:
    selected = [name.lower() for name in ucs] if ucs else discover_ucs()
    warnings: list[str] = []
    by_uc = {}
    all_results = []
    loaded_plugins = []
    conn = None
    ingested_chunks = None

    for uc_name in selected:
        if not re.fullmatch(r"uc\d{2}", uc_name):
            warnings.append(f"{uc_name}: tên UC không hợp lệ, bỏ qua")
            continue
        plugin, warning = _load_plugin(uc_name)
        if warning:
            warnings.append(warning)
            continue
        loaded_plugins.append((uc_name, plugin))

    if live and any(uc_name != "uc01" for uc_name, _ in loaded_plugins):
        conn, ingested_chunks = _prepare_live_kb()

    try:
        for uc_name, plugin in loaded_plugins:
            module, cases, run_case, summarize, extra_summary = plugin
            results = []
            for case in cases:
                try:
                    result = run_case(case, live=live)
                except Exception as error:
                    result = {
                        "case_id": case.get("id", "unknown"),
                        "passed": False,
                        "error": f"{type(error).__name__}: {error}",
                        "repairs": 0,
                        "tokens": {"input": 0, "output": 0, "total": 0},
                        "duration_seconds": 0.0,
                    }
                if isinstance(result.get("tokens"), dict):
                    t = result["tokens"]
                    if "total" not in t and "input" in t and "output" in t:
                        t["total"] = t["input"] + t["output"]
                results.append(result)

            summary = _normalize_summary(summarize(results), results)
            mem_kb = extra_summary.get("_memory_kb")
            summary.update({k: v for k, v in extra_summary.items() if not k.startswith("_")})
            if uc_name == "uc02" and callable(getattr(module, "evaluate_recall", None)):
                if live and conn is not None:
                    from agent.kb import PgKB

                    hybrid_rec = module.evaluate_recall(PgKB(conn, mode="hybrid"))
                    vector_rec = module.evaluate_recall(PgKB(conn, mode="vector"))
                    summary.update({
                        "recall_at_5": hybrid_rec["recall_at_5"],
                        "recall_hits": hybrid_rec["hits"],
                        "recall_questions": hybrid_rec["total"],
                        "recall_by_mode": {
                            "hybrid": hybrid_rec["recall_at_5"],
                            "vector": vector_rec["recall_at_5"],
                        },
                        "recall_passed": (
                            hybrid_rec["recall_at_5"] >= 0.75
                            and vector_rec["recall_at_5"] >= 0.75
                        ),
                    })
                elif mem_kb is not None:
                    recall = module.evaluate_recall(mem_kb)
                    summary.update({
                        "recall_at_5": recall["recall_at_5"],
                        "recall_hits": recall["hits"],
                        "recall_questions": recall["total"],
                        "recall_passed": recall["recall_at_5"] >= 0.75,
                    })
            if uc_name == "uc01":
                if live:
                    try:
                        intent_result = module.evaluate_intent_labels()
                    except Exception as error:
                        intent_result = {
                            "intent_accuracy": None,
                            "intent_total": 40,
                            "intent_classification_passed": False,
                            "intent_classification_error": f"{type(error).__name__}: {error}",
                        }
                    summary.update(intent_result)
                else:
                    summary.update({
                        "intent_accuracy": None,
                        "intent_total": 40,
                        "intent_classification_passed": None,
                        "intent_classification_note": (
                            "Bỏ qua ở offline mode; độ chính xác chỉ đo bằng LLM live."
                        ),
                    })

            by_uc[uc_name] = {"summary": summary, "results": results}
            all_results.extend(results)
    finally:
        if conn is not None:
            conn.close()

    summary = _summarize_results(all_results)
    summary["total_ucs"] = len(by_uc)
    summary["failed_ucs"] = sum(
        1 for value in by_uc.values()
        if value["summary"].get("failed", 0)
        or value["summary"].get("recall_passed") is False
        or value["summary"].get("intent_classification_passed") is False
    )
    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "mode": "live" if live else "offline_fixture",
        "model": _configured_model(live, all_results),
        "summary": summary,
        "by_uc": by_uc,
        "warnings": warnings,
    }
    if ingested_chunks is not None:
        report["knowledge_base"] = {"schema": "eval", "ingested_chunks": ingested_chunks}

    output_dir.mkdir(parents=True, exist_ok=True)
    filename = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + ".json"
    result_path = output_dir / filename
    report["result_file"] = str(result_path)
    result_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run selected UC evaluations")
    parser.add_argument("--all", action="store_true", help="run all available UC eval modules")
    parser.add_argument(
        "--uc", action="append", nargs="+", default=[], metavar="UC",
        help="run only these UC modules, for example --uc uc01 uc02",
    )
    parser.add_argument(
        "--offline", action="store_true",
        help="use deterministic fixtures; does not measure live intent accuracy",
    )
    parser.add_argument("--output-dir", type=Path, default=RESULTS_DIR, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    selected = [name for group in args.uc for name in group]
    if not args.all and not selected:
        parser.error("cần --all hoặc --uc <uc01 ...>")

    sys.stdout.reconfigure(encoding="utf-8")
    try:
        report = run_evaluation(
            live=not args.offline,
            output_dir=args.output_dir,
            ucs=selected or None,
        )
    except Exception as error:
        print(f"Eval lỗi: {type(error).__name__}: {error}", file=sys.stderr)
        return 1

    for warning in report["warnings"]:
        print(f"Cảnh báo: {warning}", file=sys.stderr)
    for uc_name, value in report["by_uc"].items():
        summary = value["summary"]
        print(
            f"{uc_name}: {summary['passed']}/{summary['total_cases']} passed, "
            f"avg={summary['avg_runtime_seconds']}s/case"
        )
    print(
        f"Tổng: {report['summary']['passed']}/{report['summary']['total_cases']} passed; "
        f"mode={report['mode']}; result={report['result_file']}"
    )
    return 1 if report["summary"]["failed_ucs"] else 0


if __name__ == "__main__":
    raise SystemExit(main())