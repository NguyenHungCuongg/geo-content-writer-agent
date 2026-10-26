import json
from pathlib import Path

from agent.schemas import BrandProfile
from evals.checks import evaluate_case, fixture_prompt_set
from evals.run import load_cases, run_evaluation


def test_uc01_cases_and_offline_runner_write_report(tmp_path):
    cases = load_cases()
    assert len(cases) >= 10
    assert {"full-brief", "missing-products", "overclaim", "narrow-industry", "injection"} <= {
        case["id"] for case in cases
    }

    report = run_evaluation(live=False, output_dir=tmp_path)

    assert report["summary"]["total_cases"] >= 10
    assert report["summary"]["failed"] == 0
    assert report["mode"] == "offline_fixture"
    assert report["summary"]["avg_runtime_seconds"] >= 0
    assert report["summary"]["avg_tokens_per_case"]["total"] == 0
    assert report["summary"]["schema_valid_rate"] == 1
    saved_report = json.loads(Path(report["result_file"]).read_text(encoding="utf-8"))
    assert len(saved_report["results"]) == len(cases)
    assert all(result["passed"] for result in saved_report["results"])
    assert len({result["run_id"] for result in saved_report["results"]}) == len(cases)


def test_checks_catch_leaked_claim_filled_field_and_invented_price():
    brief = "Nimbara là thương hiệu sơn số 1 Việt Nam."
    case = {
        "id": "bad", "brief": brief, "topics": ["sơn cách nhiệt"],
        "expect": {"unverified_claims": ["số 1 Việt Nam"], "empty_fields": ["products"]},
    }
    profile = BrandProfile.model_validate({
        "name": "Nimbara",
        "about": brief,
        "products": [{"name": "Nimbara", "price": "100.000 đ"}],
        "sources": {"name": "Nimbara", "about": brief, "products": "Nimbara"},
    })
    prompt_set = fixture_prompt_set(case["topics"], ["Khách hàng chung"], "Nimbara")

    checks = evaluate_case(
        case, profile, prompt_set, observations=[], find_duplicates=lambda texts: []
    )["checks"]

    failed = {name for name, result in checks.items() if not result["passed"]}
    assert failed == {
        "expected_fields_left_empty",
        "expected_claims_are_unverified",
        "unverified_claims_not_in_content_fields",
        "prices_are_literal_quotes",
    }
