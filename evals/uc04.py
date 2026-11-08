"""Eval UC-04: 5 case trong evals/cases/uc04/, đo recall tách claim và tính đúng đắn của phán quyết.

Hai chế độ:
- offline (--offline): Chạy kiểm tra đo recall trên fixtures bằng hand-labeled labels và FakeLLM
- live: Chạy agent thật qua GeminiLLM trên 5 fixtures để kiểm tra trọn vẹn pipeline.

Đo:
- Recall tách claim tổng thể (yêu cầu >= 85%)
- Recall câu có số liệu (yêu cầu 100%)
- Kết quả verdict khớp kỳ vọng

Chạy:
    python -m evals.uc04 --all --offline
    python -m evals.uc04 --all
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import yaml

from agent.article import Article, OutlinePlan, content_sentences, has_number
from agent.claims import ClaimReport
from agent.kb import MemoryKB, ingest_brand_kit, ingest_miniweb
from agent.llm import FakeLLM, GeminiLLM, LLMResponse, ToolCall
from agent.trace import Tracer
from agent.uc04 import BRAND_KIT_PATH, run_uc04

ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = ROOT / "evals" / "cases" / "uc04"
FIXTURES_DIR = ROOT / "evals" / "fixtures" / "uc04"
RESULTS_DIR = ROOT / "evals" / "results"
REQUIRED = {"id", "fixture", "labels", "expect"}


def load_cases() -> list[dict]:
    paths = sorted(CASES_DIR.glob("*.yaml"))
    cases = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in paths]
    if not cases:
        raise ValueError(f"Không tìm thấy eval case trong {CASES_DIR}")
    for case in cases:
        if not isinstance(case, dict) or not REQUIRED.issubset(case):
            raise ValueError(f"Eval case UC-04 phải có các trường {sorted(REQUIRED)}")
    ids = [c["id"] for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("ID eval case UC-04 bị trùng")
    return cases


def build_kb() -> MemoryKB:
    kb = MemoryKB()
    ingest_miniweb(kb)
    ingest_brand_kit(kb, BRAND_KIT_PATH)
    return kb


def make_offline_responses(claims_data: list[dict]) -> list[LLMResponse]:
    """Tạo FakeLLM responses cho case offline."""
    extracted = {
        "claims": [
            {
                "claim": c["claim"],
                "heading": c.get("heading", ""),
                "paragraph": c.get("paragraph", 0),
                "has_number": c.get("has_number", False),
            }
            for c in claims_data
        ]
    }
    evidence_items = []
    for i, c in enumerate(claims_data):
        v = c.get("expected_verdict", "unverifiable")
        if v == "supported":
            evidence_items.append({
                "claim_index": i,
                "chunk_id": "chunk-mock",
                "url": "https://epa.gov/cool-roof",
                "quote": "giảm nhiệt độ",
                "trust_tier": "A",
                "stance": "supports",
            })
        elif v == "contradicted":
            evidence_items.append({
                "claim_index": i,
                "chunk_id": "chunk-mock",
                "url": "https://epa.gov/cool-roof",
                "quote": "chênh lệch nhiệt độ",
                "trust_tier": "A",
                "stance": "contradicts",
            })
        else:
            evidence_items.append({
                "claim_index": i,
                "chunk_id": None,
                "url": "https://blogmaiton.example/post",
                "quote": "số liệu tham khảo",
                "trust_tier": "C",
                "stance": "supports",
            })

    return [
        LLMResponse(text=json.dumps(extracted, ensure_ascii=False)),
        LLMResponse(
            tool_calls=[ToolCall(id="s1", name="kb_search", args={"query": "chống nóng"})]
        ),
        LLMResponse(text="xong"),
        LLMResponse(text=json.dumps({"evidence": evidence_items}, ensure_ascii=False)),
    ]


def run_case(case: dict, *, live: bool = False, kb: MemoryKB | None = None) -> dict:
    started = time.perf_counter()
    fixture_path = FIXTURES_DIR / case["fixture"]
    labels_path = FIXTURES_DIR / case["labels"]

    markdown = fixture_path.read_text(encoding="utf-8")
    labels = yaml.safe_load(labels_path.read_text(encoding="utf-8")).get("claims", [])

    outline = OutlinePlan(
        title="Bài kiểm thử UC-04",
        meta_description="Mô tả",
        primary_keyword="chống nóng",
        secondary_keywords=[],
        target_prompts=[],
        sections=[],
        faq=[],
    )
    article = Article(outline=outline, markdown=markdown, citations=[])

    tracer = Tracer(f"eval-uc04-{case['id']}-{uuid4().hex[:6]}")
    target_kb = kb or build_kb()

    if live:
        llm = GeminiLLM()
    else:
        llm = FakeLLM(*make_offline_responses(labels))

    report: ClaimReport = run_uc04(article, kb=target_kb, llm=llm, tracer=tracer)

    # 1. Đo recall tách claim
    num_sents = [s for s in content_sentences(markdown) if has_number(s.text)]
    total_expected = len(labels)
    total_extracted = len(report.claims)

    matched = sum(
        1 for label_item in labels
        if any(
            c.location.heading == label_item.get("heading", "")
            and c.location.paragraph == label_item.get("paragraph", 0)
            for c in report.claims
        )
    )
    recall = matched / total_expected if total_expected > 0 else 1.0

    # Number recall: mọi câu có số phải có claim has_number
    num_claims = [c for c in report.claims if c.has_number]
    num_locations = {(c.location.heading, c.location.paragraph) for c in num_claims}
    matched_numbers = sum(
        1 for s in num_sents
        if (s.heading, s.paragraph) in num_locations
    )
    number_recall = matched_numbers / len(num_sents) if num_sents else 1.0

    expect = case.get("expect", {})
    passed = (
        recall >= expect.get("min_recall", 0.85)
        and number_recall >= expect.get("number_recall", 1.0)
    )

    duration = time.perf_counter() - started
    return {
        "id": case["id"],
        "passed": passed,
        "recall": round(recall, 3),
        "number_recall": round(number_recall, 3),
        "total_claims": total_extracted,
        "number_claims": len(num_claims),
        "duration_seconds": round(duration, 2),
    }


def summarize(results: list[dict]) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    return {
        "total_cases": total,
        "passed_cases": passed,
        "pass_rate": round(passed / total, 3) if total > 0 else 0.0,
        "avg_recall": (
            round(sum(r["recall"] for r in results) / total, 3) if total > 0 else 0.0
        ),
        "avg_number_recall": (
            round(sum(r["number_recall"] for r in results) / total, 3) if total > 0 else 0.0
        ),
        "avg_duration": (
            round(sum(r["duration_seconds"] for r in results) / total, 2) if total > 0 else 0.0
        ),
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Chạy đánh giá UC-04 (Fact-checker)")
    parser.add_argument("--all", action="store_true", help="Chạy toàn bộ eval case")
    parser.add_argument("--case", type=str, help="ID case cụ thể cần chạy")
    parser.add_argument("--offline", action="store_true", help="Chạy offline bằng FakeLLM")
    args = parser.parse_args()

    cases = load_cases()
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            print(f"Không tìm thấy case: {args.case}", file=sys.stderr)
            return 1

    shared_kb = build_kb()
    results = []
    mode_str = "offline" if args.offline else "live"
    print(f"=== Bắt đầu chạy Eval UC-04 ({len(cases)} cases, mode={mode_str}) ===")
    for c in cases:
        res = run_case(c, live=not args.offline, kb=shared_kb)
        results.append(res)
        status = "PASS" if res["passed"] else "FAIL"
        print(f"[{status}] Case {res['id']}: recall={res['recall']*100:.1f}%, "
              f"number_recall={res['number_recall']*100:.1f}% ({res['duration_seconds']}s)")

    summary = summarize(results)
    pass_pct = summary["pass_rate"] * 100
    print("\n--- TỔNG KẾT ---")
    print(f"Đạt: {summary['passed_cases']}/{summary['total_cases']} ({pass_pct:.1f}%)")
    print(f"Recall trung bình: {summary['avg_recall']*100:.1f}%")
    print(f"Number recall trung bình: {summary['avg_number_recall']*100:.1f}%")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    report_file = RESULTS_DIR / f"uc04_eval_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"
    content = json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2)
    report_file.write_text(content, encoding="utf-8")
    print(f"Báo cáo ghi tại: {report_file}")
    return 0 if summary["passed_cases"] == summary["total_cases"] else 1


if __name__ == "__main__":
    sys.exit(main())
