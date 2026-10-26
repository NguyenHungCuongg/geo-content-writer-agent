import json

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
    result_path = tmp_path / report["result_file"].split("/")[-1]
    saved_report = json.loads(result_path.read_text(encoding="utf-8"))
    assert len(saved_report["results"]) == len(cases)
    assert all(result["passed"] for result in saved_report["results"])