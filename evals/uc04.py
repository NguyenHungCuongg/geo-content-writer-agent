"""Eval UC-04: 5 case trong evals/cases/uc04/, đo recall tách claim và tính đúng đắn của phán quyết.

Hai chế độ:
- offline (--offline): Chạy kiểm tra đo recall và phán quyết trên fixtures bằng FakeLLM + MemoryKB.
- live: Chạy agent thật qua GeminiLLM trên 5 fixtures để kiểm tra trọn vẹn pipeline.

Đo:
- Recall tách claim tổng thể (yêu cầu >= 85%)
- Recall câu có số liệu (yêu cầu 100%)
- Kết quả verdict khớp kỳ vọng (expected_supported / expected_contradicted / expected_unverifiable)

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
from agent.claims import ClaimReport, blocking_claims
from agent.kb import Chunk, MemoryKB, ingest_brand_kit, ingest_miniweb
from agent.llm import FakeLLM, GeminiLLM, LLMError, LLMResponse, ToolCall
from agent.loop import AgentStopped
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


def _find_chunk(kb: MemoryKB, url_substr: str, quote_substr: str) -> tuple[Chunk, str]:
    for chunk in kb._chunks.values():
        if url_substr in chunk.url and quote_substr in chunk.text and not chunk.suspicious:
            return chunk, quote_substr
    raise RuntimeError(f"Không tìm thấy chunk ({url_substr}, {quote_substr}) trong mini-web KB")


def make_offline_responses(claims_data: list[dict], kb: MemoryKB) -> list[LLMResponse]:
    """Tạo FakeLLM responses cho case offline từ chunk có thật trong MemoryKB."""
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
    epa_chunk, epa_quote = _find_chunk(
        kb,
        "using-cool-roofs-reduce-heat-islands",
        "cool roofs can lower maximum indoor temperatures by 1.2–3.3°C (2.2 to 5.9°F).",
    )
    trap_chunk, trap_quote = _find_chunk(
        kb,
        "thong-ke-mai-ton-viet-nam",
        "90% mái tôn nhà ở tại Việt Nam chưa được xử lý chống nóng",
    )

    evidence_items = []
    for i, c in enumerate(claims_data):
        v = c.get("expected_verdict", "unverifiable")
        if v == "supported":
            evidence_items.append({
                "claim_index": i,
                "chunk_id": epa_chunk.id,
                "url": epa_chunk.url,
                "quote": epa_quote,
                "trust_tier": "A",
                "stance": "supports",
            })
        elif v == "contradicted":
            evidence_items.append({
                "claim_index": i,
                "chunk_id": epa_chunk.id,
                "url": epa_chunk.url,
                "quote": epa_quote,
                "trust_tier": "A",
                "stance": "contradicts",
            })
        else:
            evidence_items.append({
                "claim_index": i,
                "chunk_id": trap_chunk.id,
                "url": trap_chunk.url,
                "quote": trap_quote,
                "trust_tier": "C",
                "stance": "supports",
            })

    return [
        LLMResponse(text=json.dumps(extracted, ensure_ascii=False)),
        LLMResponse(
            tool_calls=[ToolCall(id="s1", name="kb_search", args={"query": "cool roofs EPA"})]
        ),
        LLMResponse(text="xong"),
        LLMResponse(text=json.dumps({"evidence": evidence_items}, ensure_ascii=False)),
    ]


def _match_labels(labels: list[dict], claims: list) -> int:
    """Đếm số label khớp 1-1 với claim tách ra theo (heading, paragraph, has_number)."""
    used: set[int] = set()
    matched = 0
    for label_item in labels:
        l_head = label_item.get("heading", "").lstrip("#").strip().lower()
        l_para = label_item.get("paragraph", 0)
        l_num = label_item.get("has_number", False)
        for idx, c in enumerate(claims):
            if idx in used:
                continue
            c_head = c.location.heading.lstrip("#").strip().lower()
            head_ok = (not l_head) or (c_head == l_head or l_head in c_head or c_head in l_head)
            if head_ok and c.location.paragraph == l_para and c.has_number == l_num:
                used.add(idx)
                matched += 1
                break
    return matched


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

    result: dict = {
        "id": case["id"],
        "case_id": case["id"],
        "run_id": tracer.run_id,
        "passed": False,
        "checks": {},
        "error": None,
    }

    try:
        llm = GeminiLLM() if live else FakeLLM(*make_offline_responses(labels, target_kb))
        report: ClaimReport = run_uc04(article, kb=target_kb, llm=llm, tracer=tracer)

        # 1. Đo recall tách claim
        num_sents = [s for s in content_sentences(markdown) if has_number(s.text)]
        total_expected = len(labels)
        matched = _match_labels(labels, report.claims)
        recall = matched / total_expected if total_expected > 0 else 1.0

        # 2. Number recall: mọi câu có số phải có claim has_number
        num_claims = [c for c in report.claims if c.has_number]

        def _sent_matched(s) -> bool:
            s_head = s.heading.lstrip("#").strip().lower()
            for c in num_claims:
                if c.location.paragraph != s.paragraph:
                    continue
                c_head = c.location.heading.lstrip("#").strip().lower()
                head_ok = c_head and (s_head == c_head or s_head in c_head or c_head in s_head)
                if not s_head or head_ok:
                    return True
            return False

        matched_numbers = sum(1 for s in num_sents if _sent_matched(s))
        number_recall = matched_numbers / len(num_sents) if num_sents else 1.0

        # 3. Kiểm tra verdict theo expect
        expect = case.get("expect", {})
        checks: dict[str, bool | str] = {
            "recall": (
                True
                if recall >= expect.get("min_recall", 0.85)
                else f"recall {recall:.2f} < {expect.get('min_recall', 0.85)}"
            ),
            "number_recall": (
                True
                if number_recall >= expect.get("number_recall", 1.0)
                else f"number_recall {number_recall:.2f} < {expect.get('number_recall', 1.0)}"
            ),
        }

        supported_count = sum(1 for c in report.claims if c.verdict == "supported")
        contradicted_count = sum(1 for c in report.claims if c.verdict == "contradicted")
        unverifiable_num_count = sum(
            1 for c in report.claims if c.has_number and c.verdict == "unverifiable"
        )

        if "expected_supported" in expect:
            need = expect["expected_supported"]
            blocked = blocking_claims(report)
            ok = supported_count >= need and len(blocked) == 0
            checks["expected_supported"] = (
                True
                if ok
                else f"supported={supported_count} (cần >={need}), blocking={len(blocked)}"
            )
        if "expected_contradicted" in expect:
            need = expect["expected_contradicted"]
            ok = contradicted_count >= need
            checks["expected_contradicted"] = (
                True if ok else f"contradicted={contradicted_count} (cần >={need})"
            )
        if "expected_unverifiable" in expect:
            need = expect["expected_unverifiable"]
            ok = unverifiable_num_count >= need
            checks["expected_unverifiable"] = (
                True
                if ok
                else f"unverifiable_numbers={unverifiable_num_count} (cần >={need})"
            )

        result["checks"] = checks
        result["passed"] = all(v is True for v in checks.values())
        result["recall"] = round(recall, 3)
        result["number_recall"] = round(number_recall, 3)
        result["total_claims"] = len(report.claims)
        result["number_claims"] = len(num_claims)
    except (AgentStopped, LLMError, ValueError) as e:
        result["error"] = f"{type(e).__name__}: {e}"
        result["recall"] = 0.0
        result["number_recall"] = 0.0
        result["total_claims"] = 0
        result["number_claims"] = 0

    llm_calls = [e for e in tracer.events if e.get("event") == "llm_call"]
    result["repairs"] = sum(
        1 for e in tracer.events if e.get("event") == "decision" and e.get("action") == "repair"
    )
    result["tokens"] = {
        "input": sum(e.get("input_tokens", 0) for e in llm_calls),
        "output": sum(e.get("output_tokens", 0) for e in llm_calls),
    }
    result["duration_seconds"] = round(time.perf_counter() - started, 3)
    return result


def summarize(results: list[dict]) -> dict:
    total = len(results)
    n = total or 1
    passed = sum(1 for r in results if r["passed"])
    return {
        "total_cases": total,
        "passed": passed,
        "passed_cases": passed,
        "failed": total - passed,
        "pass_rate": round(passed / n, 4) if total > 0 else 0.0,
        "avg_recall": (
            round(sum(r.get("recall", 0.0) for r in results) / n, 3) if total > 0 else 0.0
        ),
        "avg_number_recall": (
            round(sum(r.get("number_recall", 0.0) for r in results) / n, 3) if total > 0 else 0.0
        ),
        "avg_repairs": round(sum(r.get("repairs", 0) for r in results) / n, 2),
        "avg_tokens_per_case": {
            key: round(sum(r.get("tokens", {}).get(key, 0) for r in results) / n, 1)
            for key in ("input", "output")
        },
        "avg_runtime_seconds": round(sum(r.get("duration_seconds", 0.0) for r in results) / n, 3),
        "avg_duration": round(sum(r.get("duration_seconds", 0.0) for r in results) / n, 2),
    }


def run_evaluation(
    *, live: bool = False, output_dir: Path = RESULTS_DIR, case_ids: list[str] | None = None
) -> dict:
    shared_kb = build_kb()
    cases = [c for c in load_cases() if not case_ids or c["id"] in case_ids]
    results = [run_case(c, live=live, kb=shared_kb) for c in cases]
    report = {
        "uc": "uc04",
        "mode": "live" if live else "offline_fixture",
        "created_at": datetime.now(UTC).isoformat(),
        "summary": summarize(results),
        "results": results,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    report_file = output_dir / f"uc04_eval_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"
    report["result_file"] = str(report_file)
    report_file.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Chạy đánh giá UC-04 (Fact-checker)")
    parser.add_argument("--all", action="store_true", help="Chạy toàn bộ eval case")
    parser.add_argument("--case", type=str, help="ID case cụ thể cần chạy")
    parser.add_argument("--offline", action="store_true", help="Chạy offline bằng FakeLLM")
    args = parser.parse_args()

    case_ids = [args.case] if args.case else None
    if args.case:
        all_ids = {c["id"] for c in load_cases()}
        if args.case not in all_ids:
            print(f"Không tìm thấy case: {args.case}", file=sys.stderr)
            return 1

    mode_str = "offline" if args.offline else "live"
    report = run_evaluation(live=not args.offline, case_ids=case_ids)
    results = report["results"]
    summary = report["summary"]

    print(f"=== Kết quả Eval UC-04 ({len(results)} cases, mode={mode_str}) ===")
    for res in results:
        status = "PASS" if res["passed"] else "FAIL"
        failed = {k: v for k, v in res.get("checks", {}).items() if v is not True}
        print(
            f"[{status}] Case {res['id']}: recall={res['recall']*100:.1f}%, "
            f"number_recall={res['number_recall']*100:.1f}% "
            f"({res['duration_seconds']}s) {res.get('error') or failed or ''}"
        )

    pass_pct = summary["pass_rate"] * 100
    print("\n--- TỔNG KẾT ---")
    print(f"Đạt: {summary['passed_cases']}/{summary['total_cases']} ({pass_pct:.1f}%)")
    print(f"Recall trung bình: {summary['avg_recall']*100:.1f}%")
    print(f"Number recall trung bình: {summary['avg_number_recall']*100:.1f}%")
    print(f"Báo cáo ghi tại: {report['result_file']}")
    return 0 if summary["passed_cases"] == summary["total_cases"] else 1


if __name__ == "__main__":
    sys.exit(main())
