import json
from pathlib import Path

from agent.llm import FakeLLM, LLMResponse
from agent.schemas import BrandProfile
from agent.trace import Tracer
from agent.uc01 import classify_intents
from evals.checks import evaluate_case, fixture_prompt_set
from evals.run import run_evaluation
from evals.uc01 import load_cases, load_intent_labels, score_intents


def test_classify_intents_repairs_wrong_count_and_preserves_order(tmp_path):
    llm = FakeLLM(
        LLMResponse(text='{"intents":["commercial"]}'),
        LLMResponse(text='{"intents":["informational","transactional"]}'),
    )
    tracer = Tracer("classify-intents", traces_dir=tmp_path)

    intents = classify_intents(
        ["Vì sao mái nhà nóng?", "Đặt lịch khảo sát mái nhà"], llm=llm, tracer=tracer
    )

    assert intents == ["informational", "transactional"]
    assert sum(e.get("action") == "repair" for e in tracer.events) == 1
    assert any(e["event"] == "output" for e in tracer.events)


def test_uc01_cases_and_offline_runner_write_report(tmp_path):
    cases = load_cases()
    assert len(cases) >= 10
    assert {"full-brief", "missing-products", "overclaim", "narrow-industry", "injection"} <= {
        case["id"] for case in cases
    }

    report = run_evaluation(live=False, output_dir=tmp_path, ucs=["uc01"])

    uc01_report = report["by_uc"]["uc01"]
    assert uc01_report["summary"]["total_cases"] == 10
    assert uc01_report["summary"]["passed"] == 10
    assert uc01_report["summary"]["failed"] == 0
    assert report["mode"] == "offline_fixture"
    assert uc01_report["summary"]["avg_runtime_seconds"] >= 0
    assert uc01_report["summary"]["avg_tokens_per_case"]["total"] == 0
    assert uc01_report["summary"]["schema_valid_rate"] == 1
    assert uc01_report["summary"]["intent_accuracy"] is None
    assert uc01_report["summary"]["avg_repairs_per_case"] >= 0
    assert {"timestamp", "mode", "model", "summary", "by_uc"} <= set(report)
    saved_report = json.loads(Path(report["result_file"]).read_text(encoding="utf-8"))
    results = saved_report["by_uc"]["uc01"]["results"]
    assert len(results) == len(cases)
    assert all(result["passed"] for result in results)
    assert len({result["run_id"] for result in results}) == len(cases)


def test_intent_labels_have_balanced_counts_and_score_accuracy():
    labels = load_intent_labels()
    counts = {intent: sum(item["intent"] == intent for item in labels)
              for intent in {item["intent"] for item in labels}}
    predictions = [item["intent"] for item in labels]

    assert len(labels) == 40
    assert set(counts.values()) == {10}
    assert score_intents(labels, predictions)["intent_accuracy"] == 1.0


def test_runner_warns_and_skips_uc_without_cases(tmp_path):
    report = run_evaluation(live=False, output_dir=tmp_path, ucs=["uc05"])

    assert report["by_uc"] == {}
    assert report["warnings"]
    assert "uc05" in report["warnings"][0]


def test_runner_skips_unavailable_live_uc_before_database_setup(tmp_path, monkeypatch):
    def fail_if_called():
        raise AssertionError("unavailable UC must be skipped before DB setup")

    monkeypatch.setattr("evals.run._prepare_live_kb", fail_if_called)
    report = run_evaluation(live=True, output_dir=tmp_path, ucs=["uc05"])

    assert report["by_uc"] == {}
    assert "chưa có module eval" in report["warnings"][0]


def test_uc02_legacy_adapter_reports_trace_metrics(tmp_path):
    report = run_evaluation(live=False, output_dir=tmp_path, ucs=["uc02"])
    summary = report["by_uc"]["uc02"]["summary"]

    assert summary["passed"] == 6
    assert summary["avg_repairs_per_case"] is not None
    assert summary["avg_tokens_per_case"]["total"] == 0
    assert summary["recall_at_5"] >= 0.75


def test_live_setup_migrates_eval_schema_before_ingesting(monkeypatch):
    from agent import db, kb
    from evals.run import _prepare_live_kb

    connection = object()
    calls = []
    monkeypatch.setattr(db, "connect", lambda: connection)
    monkeypatch.setattr(db, "migrate", lambda conn, schema: calls.append(("migrate", conn, schema)))
    monkeypatch.setattr(kb, "PgKB", lambda conn: ("pgkb", conn))
    monkeypatch.setattr(
        kb,
        "ingest_miniweb",
        lambda store: calls.append(("ingest", store)) or 12,
    )

    actual_connection, chunks = _prepare_live_kb()

    assert actual_connection is connection
    assert chunks == 12
    assert calls == [
        ("migrate", connection, "eval"),
        ("ingest", ("pgkb", connection)),
    ]


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


def test_uc02_cases_and_offline_runner_write_report(tmp_path):
    from evals.uc02 import load_cases as load_uc02_cases
    from evals.uc02 import run_evaluations as run_uc02_evaluations

    cases = load_uc02_cases()
    assert len(cases) == 6
    assert {
        "01-single-source",
        "02-synthesize-two-sources",
        "03-no-source-allowlist",
        "04-injection-trap",
        "05-redirect-outside",
        "06-timeout-handling",
    } <= {c["id"] for c in cases}

    report = run_uc02_evaluations(live=False, output_dir=tmp_path)
    assert report["cases_summary"]["total_cases"] == 6
    assert report["cases_summary"]["passed"] == 6
    assert report["recall_evaluation"]["recall_at_5"] >= 0.75
    assert Path(report["result_file"]).is_file()
