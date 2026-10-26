"""Run all UC-01 evaluation cases and write a timestamped JSON report."""

import argparse
import json
import re
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import yaml

from agent import uc01
from agent.llm import FakeLLM, LLMResponse
from agent.schemas import DEFAULT_PERSONA, BrandProfile
from agent.tools import dedupe
from agent.tools.dedupe import dedupe_prompts
from agent.trace import Tracer
from evals.checks import evaluate_case, fixture_prompt_set

ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = ROOT / "evals" / "cases" / "uc01"
RESULTS_DIR = ROOT / "evals" / "results"
CLAIM_PATTERN = re.compile(
    r"[^\n.!?]*\b(?:số\s*1\s*Việt\s*Nam|hàng\s*đầu|tốt\s*nhất)\b[^\n.!?]*",
    re.I,
)
BRAND_PATTERN = re.compile(r"\w+")
PRODUCT_PATTERN = re.compile(r"(?m)^Sản phẩm:\s*(.+)$")
PERSONA_PATTERN = re.compile(r"(?m)^Khách hàng:\s*(.+)$")


def load_cases() -> list[dict]:
    cases = [
        yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in sorted(CASES_DIR.glob("*.yaml"))
    ]
    required = {"id", "brief", "topics", "expect"}
    for case in cases:
        if not isinstance(case, dict) or not required.issubset(case):
            raise ValueError(f"Eval case phải có các trường {sorted(required)}")
        if not isinstance(case["topics"], list) or not case["topics"]:
            raise ValueError(f"Case {case.get('id')} phải có ít nhất một topic")
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("ID eval case bị trùng")
    if not cases:
        raise ValueError(f"Không tìm thấy eval case trong {CASES_DIR}")
    return cases


def offline_llm(case: dict) -> FakeLLM:
    """Fixture tự dựng đáp án từ brief bằng regex: chỉ kiểm harness chạy được, không đo agent."""
    brief = case["brief"]
    first_line = brief.splitlines()[0].strip()
    brand_name = BRAND_PATTERN.match(brief).group()

    profile_data = {"name": brand_name, "about": first_line, "sources": {
        "name": brand_name, "about": first_line,
    }}
    products_match = PRODUCT_PATTERN.search(brief)
    if products_match:
        product_quote = products_match.group(1).strip()
        profile_data["products"] = [{"name": product_quote, "attributes": []}]
        profile_data["sources"]["products"] = product_quote
    else:
        profile_data["missing_info"] = ["danh mục sản phẩm"]
        profile_data["clarifying_questions"] = [f"{brand_name} hiện có những sản phẩm nào?"]

    persona_match = PERSONA_PATTERN.search(brief)
    if persona_match:
        persona = persona_match.group(1).strip()
        profile_data["personas"] = [persona]
        profile_data["sources"]["personas"] = persona
    else:
        profile_data.setdefault("missing_info", []).append("nhóm khách hàng")
        profile_data.setdefault("clarifying_questions", []).append(
            f"Nhóm khách hàng chính của {brand_name} là ai?"
        )

    claims = CLAIM_PATTERN.findall(brief)
    if claims:
        profile_data["unverified_claims"] = [claim.strip() for claim in claims]

    profile = BrandProfile.model_validate(profile_data)
    prompt_set = fixture_prompt_set(
        case["topics"], profile.personas or [DEFAULT_PERSONA], brand_name
    )
    return FakeLLM(
        LLMResponse(text="fixtures loaded"),
        LLMResponse(text=profile.model_dump_json()),
        LLMResponse(text="fixtures loaded"),
        LLMResponse(text=prompt_set.model_dump_json()),
    )


def offline_embedder(texts: list[str]) -> list[list[float]]:
    """Stable exact-match vectors for an offline harness smoke run, not semantic embeddings."""
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


def run_case(case: dict, *, live: bool) -> dict:
    # Mỗi lần chạy một run ID riêng, để từ report tra được về traces/<run_id>.jsonl.
    tracer = Tracer(f"eval-{case['id']}-{uuid4().hex[:8]}")
    llm = None if live else offline_llm(case)
    started = time.perf_counter()
    result = {
        "case_id": case["id"], "run_id": tracer.run_id, "passed": False, "checks": {}, "errors": [],
    }
    try:
        with configured_embedder(live):
            profile, prompt_set = uc01.run_uc01(
                case["brief"], case["topics"], llm=llm, tracer=tracer
            )
            observations = [
                {"tool": event["name"], "data": event["data"]}
                for event in tracer.events
                if event["event"] == "tool_call" and event.get("ok") and event.get("data")
            ]

            def find_duplicates(texts: list[str]) -> list:
                tool_result = dedupe_prompts.run({"prompts": texts})
                if not tool_result.ok:
                    raise RuntimeError(tool_result.error)
                return tool_result.data["dropped"]

            result.update(evaluate_case(
                case,
                profile,
                prompt_set,
                observations=observations,
                find_duplicates=find_duplicates,
            ))
    except Exception as error:
        result["errors"] = [f"{type(error).__name__}: {error}"]
    result["duration_seconds"] = round(time.perf_counter() - started, 4)
    result["tokens"] = {
        "input": sum(event.get("input_tokens", 0) for event in tracer.events
                     if event["event"] == "llm_call"),
        "output": sum(event.get("output_tokens", 0) for event in tracer.events
                      if event["event"] == "llm_call"),
    }
    result["tokens"]["total"] = result["tokens"]["input"] + result["tokens"]["output"]
    result["repairs"] = sum(
        event["event"] == "decision" and event.get("action") == "repair" for event in tracer.events
    )
    result["model"] = next(
        (event["model"] for event in tracer.events if event["event"] == "llm_call"),
        "fake",
    )
    result["passed"] = bool(result.get("passed")) and not result["errors"]
    return result


def run_evaluation(*, live: bool = True, output_dir: Path = RESULTS_DIR) -> dict:
    cases = load_cases()
    results = [run_case(case, live=live) for case in cases]
    token_totals = {
        key: sum(result["tokens"][key] for result in results)
        for key in ("input", "output", "total")
    }
    passed = sum(result["passed"] for result in results)
    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "mode": "live" if live else "offline_fixture",
        "model": results[0]["model"] if results else "unknown",
        "summary": {
            "total_cases": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            # Case dừng giữa chừng (AgentStopped) không có output, tính là không hợp lệ.
            "schema_valid_rate": round(sum(
                result["checks"].get("schema_valid", {}).get("passed", False)
                for result in results
            ) / len(results), 4),
            "avg_repairs_per_case": round(
                sum(result["repairs"] for result in results) / len(results), 2
            ),
            "avg_runtime_seconds": round(
                sum(result["duration_seconds"] for result in results) / len(results), 4
            ),
            "avg_tokens_per_case": {
                key: round(value / len(results), 2) for key, value in token_totals.items()
            },
            "token_totals": token_totals,
        },
        "results": results,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + ".json"
    report["result_file"] = str(output_dir / filename)
    (output_dir / filename).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the UC-01 evaluation suite")
    parser.add_argument("--all", action="store_true", help="run every UC-01 case")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="use deterministic FakeLLM fixtures and local exact-match dedupe",
    )
    args = parser.parse_args()
    if not args.all:
        parser.error("--all is required")

    sys.stdout.reconfigure(encoding="utf-8")
    try:
        report = run_evaluation(live=not args.offline)
    except Exception as error:
        print(f"Eval lỗi: {error}", file=sys.stderr)
        return 1
    summary = report["summary"]
    print(
        f"{summary['passed']}/{summary['total_cases']} passed, "
        f"{summary['failed']} failed; mode={report['mode']}; "
        f"avg={summary['avg_runtime_seconds']}s/case; "
        f"tokens={summary['token_totals']}; result={report['result_file']}"
    )
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
