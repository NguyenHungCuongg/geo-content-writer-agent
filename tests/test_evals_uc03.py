"""Eval UC-03 chạy offline từ đầu đến cuối và bộ chấm bắt được bài sai luật."""

import json
from pathlib import Path

from agent.article import Article
from agent.kb import BRAND_KIT_PATH
from agent.uc03 import load_brand
from evals.uc03 import build_kb, grade, load_cases, run_evaluation
from tests.uc03_fixture import CITATION, article_markdown, outline

CASE_IDS = {"01-informational", "02-commercial-competitors", "03-no-data", "04-brand-voice-b",
            "05-keyword-stuffing"}


def test_five_cases_cover_spec():
    assert {c["id"] for c in load_cases()} == CASE_IDS


def test_offline_eval_passes_and_writes_report(tmp_path):
    report = run_evaluation(live=False, output_dir=tmp_path)
    summary = report["summary"]
    assert summary["total_cases"] == 5
    assert summary["failed"] == 0, [r for r in report["results"] if not r["passed"]]
    saved = json.loads(Path(report["result_file"]).read_text(encoding="utf-8"))
    assert {r["case_id"] for r in saved["results"]} == CASE_IDS
    assert "avg_repairs" in saved["summary"]


def test_grade_catches_wrong_reader_for_brand_kit_b():
    case = next(c for c in load_cases() if c["id"] == "04-brand-voice-b")
    kit = load_brand(Path(__file__).resolve().parents[1] / case["brand_kit"])
    article = Article(outline=outline(), markdown=article_markdown(), citations=[CITATION])
    checks = grade(case, article, kit, build_kb(BRAND_KIT_PATH))
    assert checks["reader"] is not True  # bài gọi "anh/chị" trong khi Mát Hiên gọi "bạn"
    assert checks["forbidden_reader"] is not True
