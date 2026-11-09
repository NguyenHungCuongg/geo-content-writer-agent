"""UC-01 eval cases and the labeled intent-classification evaluation."""

import json
import re
import time
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import yaml

from agent import uc01
from agent.llm import FakeLLM, LLMResponse
from agent.schemas import DEFAULT_PERSONA, INTENTS, BrandProfile, Intent
from agent.tools import dedupe
from agent.trace import Tracer
from evals.checks import evaluate_case, fixture_prompt_set

ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = ROOT / "evals" / "cases" / "uc01"
INTENT_LABELS_PATH = ROOT / "evals" / "data" / "intent_labels.jsonl"
CLAIM_PATTERN = re.compile(
    r"[^\n.!?]*\b(?:số\s*1\s*Việt\s*Nam|hàng\s*đầu|tốt\s*nhất)\b[^\n.!?]*",
    re.I,
)
BRAND_PATTERN = re.compile(r"\w+")
PRODUCT_PATTERN = re.compile(r"(?m)^Sản phẩm:\s*(.+)$")
PERSONA_PATTERN = re.compile(r"(?m)^Khách hàng:\s*(.+)$")
INTENT_ACCURACY_THRESHOLD = 0.8


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
    return cases


def load_intent_labels() -> list[dict]:
    if not INTENT_LABELS_PATH.is_file():
        raise FileNotFoundError(f"Không tìm thấy file: {INTENT_LABELS_PATH}")
    labels = [
        json.loads(line)
        for line in INTENT_LABELS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    required = {"id", "prompt", "intent"}
    if any(not isinstance(item, dict) or not required.issubset(item) for item in labels):
        raise ValueError("Mỗi nhãn intent cần có id, prompt và intent")
    if len(labels) != 40:
        raise ValueError(f"Cần đúng 40 prompt intent, hiện có {len(labels)}")
    if len({item["id"] for item in labels}) != len(labels):
        raise ValueError("ID prompt intent bị trùng")
    counts = Counter(item["intent"] for item in labels)
    if set(counts) != set(INTENTS) or any(counts[intent] != 10 for intent in INTENTS):
        raise ValueError("Bộ intent phải có đúng 10 prompt cho mỗi nhãn")
    if any(not item["prompt"].strip() for item in labels):
        raise ValueError("Prompt intent không được rỗng")
    return labels


def score_intents(labels: list[dict], predictions: list[Intent]) -> dict:
    if len(labels) != len(predictions):
        raise ValueError(f"Cần {len(labels)} dự đoán intent, nhận được {len(predictions)}")
    correct_by_intent = Counter(
        item["intent"] for item, prediction in zip(labels, predictions, strict=True)
        if item["intent"] == prediction
    )
    total_by_intent = Counter(item["intent"] for item in labels)
    correct = sum(correct_by_intent.values())
    total = len(labels)
    return {
        "intent_accuracy": round(correct / total, 4) if total else 0.0,
        "intent_correct": correct,
        "intent_total": total,
        "intent_accuracy_threshold": INTENT_ACCURACY_THRESHOLD,
        "intent_accuracy_by_label": {
            intent: round(correct_by_intent[intent] / total_by_intent[intent], 4)
            for intent in INTENTS
        },
        "intent_classification_passed": bool(total)
        and correct / total >= INTENT_ACCURACY_THRESHOLD,
    }


def evaluate_intent_labels(*, llm=None, tracer: Tracer | None = None) -> dict:
    labels = load_intent_labels()
    tracer = tracer or Tracer(f"eval-uc01-intents-{uuid4().hex[:8]}")
    predictions = uc01.classify_intents(
        [item["prompt"] for item in labels], llm=llm, tracer=tracer
    )
    result = score_intents(labels, predictions)
    result["run_id"] = tracer.run_id
    result["model"] = next(
        (event["model"] for event in tracer.events if event["event"] == "llm_call"),
        "unknown",
    )
    result["tokens"] = {
        key: sum(
            event.get(f"{key}_tokens", 0)
            for event in tracer.events
            if event["event"] == "llm_call"
        )
        for key in ("input", "output")
    }
    result["tokens"]["total"] = result["tokens"]["input"] + result["tokens"]["output"]
    return result


def offline_llm(case: dict) -> FakeLLM:
    """Fixture answers from the brief; this checks the harness, not live model quality."""
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
    """Stable exact-match vectors for an offline harness smoke run."""
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
                checks = [
                    event for event in tracer.events
                    if event["event"] == "decision" and event.get("action") == "check_duplicates"
                ]
                if not checks:
                    raise RuntimeError("trace không có check_duplicates")
                if checks[-1]["error"]:
                    raise RuntimeError(checks[-1]["error"])
                return checks[-1]["dropped"]

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
    llm_calls = [event for event in tracer.events if event["event"] == "llm_call"]
    result["tokens"] = {
        "input": sum(event.get("input_tokens", 0) for event in llm_calls),
        "output": sum(event.get("output_tokens", 0) for event in llm_calls),
    }
    result["tokens"]["total"] = result["tokens"]["input"] + result["tokens"]["output"]
    result["repairs"] = sum(
        event["event"] == "decision" and event.get("action") == "repair"
        for event in tracer.events
    )
    result["model"] = next((event["model"] for event in llm_calls), "fake")
    result["passed"] = bool(result.get("passed")) and not result["errors"]
    return result


def summarize(results: list[dict]) -> dict:
    count = len(results)
    divisor = count or 1
    passed = sum(result["passed"] for result in results)
    token_totals = {
        key: sum(result.get("tokens", {}).get(key, 0) for result in results)
        for key in ("input", "output", "total")
    }
    return {
        "total_cases": count,
        "passed": passed,
        "failed": count - passed,
        "pass_rate": round(passed / divisor, 4),
        "schema_valid_rate": round(sum(
            result.get("checks", {}).get("schema_valid", {}).get("passed", False)
            for result in results
        ) / divisor, 4),
        "avg_repairs_per_case": round(
            sum(result.get("repairs", 0) for result in results) / divisor, 2
        ),
        "avg_runtime_seconds": round(
            sum(result.get("duration_seconds", 0) for result in results) / divisor, 4
        ),
        "avg_tokens_per_case": {
            key: round(value / divisor, 2) for key, value in token_totals.items()
        },
        "token_totals": token_totals,
    }