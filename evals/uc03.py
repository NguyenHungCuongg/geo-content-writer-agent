"""Eval UC-03: 5 case trong evals/cases/uc03/, chấm bằng code, ghi report JSON vào evals/results/.

Hai chế độ:
- offline (`--offline`): FakeLLM soạn sẵn dàn ý và bài từ chunk thật trong kho. Chỉ kiểm harness
  chạy đúng từ đầu đến cuối (validator, trích dẫn, trace), không đo chất lượng model.
- live: Gemini thật qua run_uc03, kho offline (snapshot mini-web + brand kit, tìm theo từ khoá).

Mọi case đều chấm lại bài cuối bằng `check_outline`/`check_article` (không tin kết quả của run),
cộng điều kiện riêng trong `expect` của case. Report có tỉ lệ pass, số lần sửa, token và thời
gian trung bình mỗi case (đặc tả 6.2).

Chạy:
    python -m evals.uc03 --all --offline
    python -m evals.uc03 --all            # live, cần GEMINI_API_KEY, GEMINI_MODEL
"""

import argparse
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import yaml

from agent.article import (
    MAX_KEYWORD_DENSITY,
    READER_TERMS,
    Article,
    check_article,
    check_outline,
    has_number,
    keyword_density,
    phrase_pattern,
    plain_text,
    split_sentences,
)
from agent.kb import BRAND_KIT_PATH, Citation, MemoryKB, ingest_brand_kit, ingest_miniweb
from agent.llm import FakeLLM, LLMError, LLMResponse, ToolCall
from agent.loop import AgentStopped
from agent.schemas import Prompt
from agent.tools.similarity import load_miniweb_pages, max_overlap
from agent.trace import Tracer
from agent.uc03 import InputError, load_brand, run_uc03, voice_rules

ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = ROOT / "evals" / "cases" / "uc03"
RESULTS_DIR = ROOT / "evals" / "results"
REQUIRED = {"id", "topic", "keyword", "prompts", "expect"}


def load_cases() -> list[dict]:
    paths = sorted(CASES_DIR.glob("*.yaml"))
    cases = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in paths]
    if not cases:
        raise ValueError(f"Không tìm thấy eval case trong {CASES_DIR}")
    for case in cases:
        if not isinstance(case, dict) or not REQUIRED.issubset(case):
            raise ValueError(f"Eval case UC-03 phải có các trường {sorted(REQUIRED)}")
    ids = [c["id"] for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("ID eval case UC-03 bị trùng")
    return cases


def brand_path(case: dict) -> Path:
    return ROOT / case["brand_kit"] if case.get("brand_kit") else BRAND_KIT_PATH


def prompts_of(case: dict) -> list[Prompt]:
    return [
        Prompt(id=p["id"], text=p["text"], intent=p["intent"], topic=case["topic"],
               persona="Khách hàng chung", keywords=[case["keyword"]], mentions_brand=False)
        for p in case["prompts"]
    ]


def build_kb(path: Path) -> MemoryKB:
    kb = MemoryKB()
    ingest_miniweb(kb)
    ingest_brand_kit(kb, path)
    return kb


# ------------------------------------------------------------- fixture offline

FILLERS = [
    "Lớp phủ sáng màu phản xạ ánh nắng nên mái hấp thụ ít nhiệt hơn vào buổi trưa.",
    "Trước khi làm, nên vệ sinh bề mặt mái và xử lý chỗ gỉ để lớp phủ bám chắc.",
    "Hiệu quả thực tế còn phụ thuộc hướng nhà, độ thông gió và màu sắc của mái.",
    "Kết hợp che nắng và thông gió thường cho cảm giác dễ chịu hơn so với chỉ làm một cách.",
    "Nên kiểm tra mái định kỳ sau mùa mưa để phát hiện sớm chỗ bong tróc.",
]


def filler(k: int) -> str:
    return " ".join(FILLERS[(k + i) % len(FILLERS)] for i in range(3))


def number_quote(kb: MemoryKB, query: str | None, banned: list[str]) -> tuple[str, Citation] | None:
    """Câu có số liệu trong một chunk thật (tier A/B), dùng làm trích dẫn cho bài offline."""
    if not query:
        return None
    avoid = [phrase_pattern(w) for w in [*banned, *READER_TERMS]]
    for hit in kb.search(query, k=10):
        if hit.trust_tier not in ("A", "B"):
            continue
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", hit.text):
            sentence = sentence.strip().rstrip(".:")
            if (has_number(sentence) and 30 <= len(sentence) <= 200 and "[" not in sentence
                    and len(split_sentences(sentence)) == 1
                    and not any(p.search(sentence) for p in avoid)):
                return sentence, Citation(n=1, chunk_id=hit.id, url=hit.url, quote=sentence)
    return None


def offline_outline(case: dict) -> dict:
    sections = [
        {"heading": p["text"], "level": 2, "format": "table" if i == 0 else "paragraph",
         "answer_first": "Câu trả lời ngắn gọn nằm ngay dưới đây, kèm điều kiện áp dụng.",
         "points": ["nguyên lý", "cách làm"], "needs_citation": i == 0, "prompt_ids": [p["id"]]}
        for i, p in enumerate(case["prompts"])
    ]
    sections.append({"heading": "Câu hỏi thường gặp", "level": 2, "format": "list",
                     "answer_first": "Một số câu hỏi hay gặp.", "points": [],
                     "needs_citation": False, "prompt_ids": []})
    faq = [{"question": q, "answer": "Xem hướng dẫn của nhà sản xuất."} for q in (
        "Khi nào nên làm lại lớp phủ?", "Có cần sơn lót không?",
        "Làm vào mùa mưa được không?", "Có tự làm được không?",
    )]
    return {"title": case["topic"][:60], "meta_description": case["topic"][:150],
            "primary_keyword": case["keyword"], "secondary_keywords": [],
            "target_prompts": [p["id"] for p in case["prompts"]], "sections": sections, "faq": faq}


def offline_markdown(case: dict, outline: dict, reader: str, cited: str | None) -> str:
    parts = [f"# {outline['title']}", f"Bài này giúp {reader} hiểu rõ {case['keyword']}."]
    k = 0
    for i, s in enumerate(outline["sections"]):
        parts.append(f"## {s['heading']}")
        opener = f"Câu trả lời ngắn cho {reader}: có cách làm phù hợp, tuỳ điều kiện của mái."
        if i == 0 and cited:
            opener = f"Có. Một nguồn ghi nhận: {cited} [1]."
        parts.append(opener)
        if s["format"] == "table":
            parts.append("| Cách làm | Ưu điểm | Lưu ý |\n|---|---|---|\n"
                         "| Sơn phản xạ | Thi công nhanh | Vệ sinh mái kỹ |\n"
                         "| Che nắng | Dễ tự làm | Chọn vật liệu bền |")
        competitor = case.get("offline", {}).get("competitor")
        if competitor and i == 0:
            parts.append(f"Sản phẩm của {competitor} cũng là một lựa chọn, so theo nhu cầu.")
        for _ in range(4):
            parts.append(filler(k))
            k += 1
        if s["heading"] == "Câu hỏi thường gặp":
            for f in outline["faq"]:
                parts += [f"### {f['question']}", f"{f['answer']} {filler(k)}"]
                k += 1
    return "\n\n".join(parts)


def offline_llm(case: dict, kb: MemoryKB, kit: dict) -> FakeLLM:
    rules = voice_rules(kit)
    found = number_quote(kb, case.get("offline", {}).get("query"), rules["banned_words"])
    outline = offline_outline(case)
    markdown = offline_markdown(case, outline, rules["reader"], found[0] if found else None)
    notes = []
    if not found:
        notes.append("Kho không có số liệu cho chủ đề này nên bài viết định tính, không có con số.")
    if case["expect"].get("notes_required"):
        notes.append("Không lặp từ khoá theo yêu cầu: mật độ trên 3% làm bài khó đọc và vi phạm "
                     "luật UC-03.")
    draft = {"markdown": markdown, "citations": [found[1].model_dump()] if found else [],
             "notes": notes}
    query = case.get("offline", {}).get("query") or case["keyword"]
    search = LLMResponse(tool_calls=[ToolCall("s1", "kb_search", {"query": query, "k": 10})])
    return FakeLLM(
        search, LLMResponse(text="xong"), LLMResponse(text=json.dumps(outline, ensure_ascii=False)),
        LLMResponse(text="xong"), LLMResponse(text=json.dumps(draft, ensure_ascii=False)),
    )


# ------------------------------------------------------------------- chấm điểm


def grade(case: dict, article: Article, kit: dict, kb: MemoryKB) -> dict[str, bool | str]:
    """Chấm lại bài bằng code; mỗi điều kiện một khoá, giá trị True hoặc chuỗi lỗi."""
    rules = voice_rules(kit)
    pages = load_miniweb_pages()
    expect = case["expect"]
    checks: dict[str, bool | str] = {}

    outline_errors = check_outline(article.outline, [p["id"] for p in case["prompts"]])
    checks["outline_rules"] = True if not outline_errors else "; ".join(outline_errors)
    article_errors = check_article(
        article.outline, article.markdown, article.citations, **rules, kb=kb,
        similarity=lambda text: max_overlap(text, pages),
    )
    checks["article_rules"] = True if not article_errors else "; ".join(article_errors)

    if "min_citations" in expect:
        ok = len(article.citations) >= expect["min_citations"]
        checks["min_citations"] = ok or f"chỉ có {len(article.citations)} trích dẫn"
    if "mentions_any" in expect:
        text = plain_text(article.markdown)
        ok = any(phrase_pattern(name).search(text) for name in expect["mentions_any"])
        names = expect["mentions_any"]
        checks["mentions_competitor"] = ok or f"không nhắc đối thủ nào trong {names}"
    if expect.get("no_uncited_numbers"):
        bad = [s.text for s in split_sentences(article.markdown)
               if has_number(s.text) and not re.search(r"\[\d+\]", s.text)]
        checks["no_uncited_numbers"] = not bad or f"câu có số không trích dẫn: {bad[:3]}"
    if "reader" in expect:
        ok = rules["reader"] == expect["reader"] and bool(
            phrase_pattern(expect["reader"]).search(plain_text(article.markdown)))
        checks["reader"] = ok or f'không gọi người đọc là "{expect["reader"]}"'
    if "forbidden_reader" in expect:
        found = [t for t in expect["forbidden_reader"]
                 if phrase_pattern(t).search(plain_text(article.markdown))]
        checks["forbidden_reader"] = not found or f"dùng cách gọi bị cấm: {found}"
    if "max_keyword_density" in expect:
        density = keyword_density(article.markdown, article.outline.primary_keyword)
        limit = min(expect["max_keyword_density"], MAX_KEYWORD_DENSITY)
        checks["keyword_density"] = density <= limit or f"mật độ {density:.1%} > {limit:.0%}"
    if expect.get("notes_required"):
        checks["notes"] = bool(article.notes) or "không giải thích trong notes"
    return checks


def run_case(case: dict, *, live: bool) -> dict:
    tracer = Tracer(f"eval-uc03-{case['id']}-{uuid4().hex[:8]}")
    path = brand_path(case)
    kit = load_brand(path)
    kb = build_kb(path)
    started = time.perf_counter()
    result = {"case_id": case["id"], "run_id": tracer.run_id, "passed": False, "checks": {},
              "error": None}
    try:
        llm = None if live else offline_llm(case, kb, kit)
        article = run_uc03(case["topic"], prompts_of(case), brand_kit_path=path, kb=kb, llm=llm,
                           tracer=tracer)
        result["checks"] = grade(case, article, kit, kb)
        result["passed"] = all(v is True for v in result["checks"].values())
        result["citations"] = len(article.citations)
        result["notes"] = article.notes
    except (AgentStopped, InputError, LLMError) as e:
        result["error"] = f"{type(e).__name__}: {e}"

    llm_calls = [e for e in tracer.events if e["event"] == "llm_call"]
    result["repairs"] = sum(
        1 for e in tracer.events if e["event"] == "decision" and e.get("action") == "repair"
    )
    result["tokens"] = {
        "input": sum(e.get("input_tokens", 0) for e in llm_calls),
        "output": sum(e.get("output_tokens", 0) for e in llm_calls),
    }
    result["duration_seconds"] = round(time.perf_counter() - started, 3)
    return result


def run_evaluation(*, live: bool, output_dir: Path = RESULTS_DIR,
                   case_ids: list[str] | None = None) -> dict:
    cases = [c for c in load_cases() if not case_ids or c["id"] in case_ids]
    results = [run_case(case, live=live) for case in cases]
    n = len(results) or 1
    passed = sum(r["passed"] for r in results)
    report = {
        "uc": "uc03",
        "mode": "live" if live else "offline_fixture",
        "created_at": datetime.now(UTC).isoformat(),
        "summary": {
            "total_cases": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "pass_rate": round(passed / n, 4),
            "avg_repairs": round(sum(r["repairs"] for r in results) / n, 2),
            "avg_tokens_per_case": {
                key: round(sum(r["tokens"][key] for r in results) / n, 1)
                for key in ("input", "output")
            },
            "avg_runtime_seconds": round(sum(r["duration_seconds"] for r in results) / n, 3),
        },
        "results": results,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"uc03-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}.json"
    report["result_file"] = str(out)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Chạy eval UC-03")
    parser.add_argument("--all", action="store_true", help="chạy mọi case UC-03")
    parser.add_argument("--case", action="append", default=[], help="chỉ chạy case có id này")
    parser.add_argument("--offline", action="store_true", help="dùng FakeLLM, không gọi Gemini")
    args = parser.parse_args()
    if not args.all and not args.case:
        parser.error("cần --all hoặc --case <id>")
    sys.stdout.reconfigure(encoding="utf-8")

    report = run_evaluation(live=not args.offline, case_ids=args.case or None)
    s = report["summary"]
    for r in report["results"]:
        status = "PASS" if r["passed"] else "FAIL"
        failed = {k: v for k, v in r["checks"].items() if v is not True}
        print(f"[{status}] {r['case_id']} repairs={r['repairs']} {r['error'] or failed or ''}")
    print(f"{s['passed']}/{s['total_cases']} passed; mode={report['mode']}; "
          f"avg_repairs={s['avg_repairs']}; tokens={s['avg_tokens_per_case']}; "
          f"avg={s['avg_runtime_seconds']}s/case; result={report['result_file']}")
    return 0 if s["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
