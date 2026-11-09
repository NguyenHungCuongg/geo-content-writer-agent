"""Eval UC-09 chạy offline đủ 6 case từ đầu đến cuối (gồm cả kill subprocess & resume)."""

from __future__ import annotations

import json
from pathlib import Path

from evals.uc09 import load_cases, run_evaluation, summarize

CASE_IDS = {
    "uc09-01-full-calendar",
    "uc09-02-interrupt-and-resume",
    "uc09-03-interrupt-twice",
    "uc09-04-long-session-compaction",
    "uc09-05-human-approval",
    "uc09-06-human-rejection",
}


def test_six_cases_cover_spec():
    cases = load_cases()
    assert len(cases) == 6
    assert {c["id"] for c in cases} == CASE_IDS


def test_offline_eval_uc09_passes_all_six_cases(tmp_path):
    report = run_evaluation(live=False, output_dir=tmp_path)
    summary = report["summary"]
    assert summary["total_cases"] == 6
    failed_cases = [
        f"[{r['case_id']}] err={r.get('error')}, "
        f"checks={ {k: v for k, v in r.get('checks', {}).items() if v is not True} }"
        for r in report["results"]
        if not r["passed"]
    ]
    assert summary["failed"] == 0, "\n".join(failed_cases)
    assert summarize(report["results"]) == summary

    saved = json.loads(Path(report["result_file"]).read_text(encoding="utf-8"))
    assert {r["case_id"] for r in saved["results"]} == CASE_IDS
    assert saved["summary"]["pass_rate"] == 1.0
