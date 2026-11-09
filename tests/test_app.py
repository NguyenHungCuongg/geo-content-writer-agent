"""Test backend FastAPI bằng FakeLLM: không gọi mạng."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from test_uc01 import BRIEF, NO_TOOL, PROFILE, TOPIC, prompt_set, reply

from agent.llm import FakeLLM
from agent.trace import Tracer
from app.backend import main

client = TestClient(main.app)


@pytest.fixture
def use_llm():
    def use(llm):
        main.app.dependency_overrides[main.get_llm] = lambda: llm
    yield use
    main.app.dependency_overrides.clear()


def start(brief: str = BRIEF, topics: tuple[str, ...] = (TOPIC,)) -> str:
    r = client.post("/runs/uc01", json={"brief": brief, "topics": list(topics)})
    assert r.status_code == 200
    return r.json()["run_id"]


def events(run_id: str) -> list[dict]:
    with client.stream("GET", f"/runs/{run_id}/events") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        return [json.loads(line.removeprefix("data: "))
                for line in r.iter_lines() if line.startswith("data: ")]


def test_run_streams_events_until_output(use_llm):
    use_llm(FakeLLM(NO_TOOL, reply(PROFILE), NO_TOOL, reply(prompt_set())))
    run_id = start()
    got = events(run_id)

    assert len(run_id) == 32
    assert got[0]["event"] == "input"
    assert got[-1]["event"] == "output"
    assert len(got[-1]["prompt_set"]["prompts"]) == 32
    assert {e["run_id"] for e in got} == {run_id}


def test_bad_input_streams_error_without_calling_llm(use_llm):
    llm = FakeLLM(reply(PROFILE))
    use_llm(llm)
    got = events(start(brief="   "))

    assert [e["event"] for e in got] == ["input", "error"]
    assert got[-1]["reason"] == "InputError"
    assert llm.calls == []


class BrokenLLM:
    model = "broken"

    def generate(self, *args, **kwargs):
        raise RuntimeError("boom")


def test_unexpected_exception_ends_stream_with_error(use_llm):
    use_llm(BrokenLLM())
    got = events(start())

    assert got[-1]["event"] == "error"
    assert got[-1]["reason"] == "internal_error"
    assert "RuntimeError: boom" in got[-1]["message"]


def test_agent_stop_has_single_error_event(use_llm):
    # sai luật mãi -> repair_failed
    use_llm(FakeLLM(NO_TOOL, reply(PROFILE), NO_TOOL, reply({"prompts": []})))
    got = events(start())

    errors = [e for e in got if e["event"] == "error"]
    assert len(errors) == 1
    assert errors[0]["reason"] == "repair_failed"


def test_unknown_run_returns_404():
    assert client.get(f"/runs/{'0' * 32}/events").status_code == 404


def test_rejects_oversized_brief():
    body = {"brief": "a" * (main.MAX_BRIEF_CHARS + 1), "topics": [TOPIC]}
    assert client.post("/runs/uc01", json=body).status_code == 422


def test_follow_yields_events_logged_later():
    tracer = Tracer("r1")
    tracer.log("input", brief=BRIEF, topics=[TOPIC])

    async def consume() -> list[str]:
        async def finish_later():
            await asyncio.sleep(0.05)
            tracer.log("output", brand_profile={}, prompt_set={})

        task = asyncio.create_task(finish_later())
        got = [e["event"] async for e in main.follow(tracer.events)]
        await task
        return got

    # follow hỏng thì fail sau 2 giây, không treo cả bộ test
    assert asyncio.run(asyncio.wait_for(consume(), 2)) == ["input", "output"]


def write_trace(directory, run_id: str, lines: list[dict]) -> None:
    text = "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines)
    (directory / f"{run_id}.jsonl").write_text(text, encoding="utf-8")


def test_replays_finished_run_from_trace_file(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "TRACES_DIR", tmp_path)
    run_id = "a" * 32
    lines = [
        {"ts": "t0", "run_id": run_id, "event": "input",
         "brief": "Sơn chống nóng mái tôn Skyveil", "topics": [TOPIC]},
        {"ts": "t1", "run_id": run_id, "event": "error", "reason": "llm_error", "message": "x"},
    ]
    write_trace(tmp_path, run_id, lines)

    assert events(run_id) == lines


def test_trace_file_without_terminal_event_ends_stream(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "TRACES_DIR", tmp_path)
    run_id = "b" * 32
    lines = [{"ts": "t0", "run_id": run_id, "event": "input", "brief": BRIEF, "topics": [TOPIC]}]
    write_trace(tmp_path, run_id, lines)

    assert events(run_id) == lines  # trả về được, không chờ mãi


@pytest.mark.parametrize("run_id", ["..%5C..%5C.env", "abc", "A" * 32])
def test_malformed_run_id_rejected(run_id):
    assert client.get(f"/runs/{run_id}/events").status_code == 422


def test_replay_skips_truncated_last_line(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "TRACES_DIR", tmp_path)
    run_id = "c" * 32
    lines = [{"ts": "t0", "run_id": run_id, "event": "input", "brief": BRIEF, "topics": [TOPIC]}]
    write_trace(tmp_path, run_id, lines)
    with (tmp_path / f"{run_id}.jsonl").open("a", encoding="utf-8") as f:
        f.write('{"ts": "t1", "run_id": "' + run_id + '", "event": "outp')  # tắt giữa lúc ghi

    assert events(run_id) == lines


def test_known_errors_are_not_logged_as_exceptions(use_llm, caplog):
    use_llm(FakeLLM(reply(PROFILE)))
    events(start(brief="   "))
    assert not [r for r in caplog.records if r.exc_info]

    use_llm(BrokenLLM())
    events(start())
    assert [r for r in caplog.records if r.exc_info]


def test_run_uc02_streams_events_until_output(use_llm):
    from agent.llm import LLMResponse
    from agent.uc02 import ResearchAnswer, ResearchReport

    report = ResearchReport(
        topic="sơn chống nóng",
        queries=["q1", "q2", "q3"],
        answers=[
            ResearchAnswer(
                question="Câu hỏi 1?",
                answer="Hiện không đủ nguồn thông tin.",
                citations=[],
                insufficient=True,
            )
        ],
    )
    use_llm(FakeLLM(NO_TOOL, LLMResponse(text=report.model_dump_json())))

    r = client.post("/runs/uc02", json={"topic": "sơn chống nóng", "questions": ["Câu hỏi 1?"]})
    assert r.status_code == 200
    run_id = r.json()["run_id"]
    assert len(run_id) == 32

    got = events(run_id)
    assert got[0]["event"] == "input"
    assert got[0]["topic"] == "sơn chống nóng"
    assert got[-1]["event"] == "output"
    assert "report" in got[-1]
    assert got[-1]["report"]["topic"] == "sơn chống nóng"


def test_rejects_empty_uc02_topic():
    r = client.post("/runs/uc02", json={"topic": "", "questions": ["Câu 1?"]})
    assert r.status_code == 422


# ------------------------------------------------------------------- UC-03


@pytest.fixture
def use_uc03_kb():
    from tests.uc03_fixture import kb

    main.app.dependency_overrides[main.get_uc03_kb] = kb
    yield
    main.app.dependency_overrides.pop(main.get_uc03_kb, None)


def test_run_uc03_streams_article(use_llm, use_uc03_kb):
    from tests.test_uc03 import happy_path
    from tests.uc03_fixture import PROMPTS, TOPIC

    use_llm(FakeLLM(*happy_path()))
    r = client.post("/runs/uc03", json={
        "topic": TOPIC, "prompts": [p.model_dump() for p in PROMPTS],
    })
    assert r.status_code == 200
    got = events(r.json()["run_id"])
    assert got[0]["event"] == "input"
    assert got[-1]["event"] == "output"
    article = got[-1]["article"]
    assert article["citations"][0]["n"] == 1
    assert [s["level"] for s in article["outline"]["sections"]] == [2, 2, 2]


def test_run_uc03_duplicate_prompt_ids_end_with_input_error(use_llm, use_uc03_kb):
    from tests.uc03_fixture import PROMPTS, TOPIC

    use_llm(FakeLLM(NO_TOOL))
    prompts = [p.model_dump() for p in PROMPTS + PROMPTS]
    got = events(client.post("/runs/uc03", json={"topic": TOPIC, "prompts": prompts})
                 .json()["run_id"])
    assert got[-1]["event"] == "error"
    assert got[-1]["reason"] == "InputError"


def test_rejects_uc03_without_prompts():
    r = client.post("/runs/uc03", json={"topic": "sơn chống nóng", "prompts": []})
    assert r.status_code == 422


# ------------------------------------------------------------------- UC-04


def test_run_uc04_streams_report(use_llm, use_uc03_kb):
    from tests.test_uc04 import SAMPLE_ARTICLE, uc04_responses_supported

    use_llm(FakeLLM(*uc04_responses_supported()))
    r = client.post("/runs/uc04", json={"article": SAMPLE_ARTICLE.model_dump()})
    assert r.status_code == 200
    got = events(r.json()["run_id"])
    assert got[0]["event"] == "input"
    assert got[-1]["event"] == "output"
    assert got[-1]["report"]["claims"][0]["verdict"] == "supported"


# ---------------------------------------------------- Task 8: History, UC-09, Approval & Resume


def test_runs_listed_after_restart(use_llm):
    use_llm(FakeLLM(NO_TOOL, reply(PROFILE), NO_TOOL, reply(prompt_set())))
    run_id_1 = start()

    use_llm(FakeLLM(NO_TOOL, reply(PROFILE), NO_TOOL, reply(prompt_set())))
    run_id_2 = start()

    # Giả lập server khởi động lại: xoá sạch RUNS trong RAM
    main.RUNS.clear()

    r = client.get("/runs")
    assert r.status_code == 200
    listed = r.json()
    by_id = {item["run_id"]: item for item in listed}
    assert run_id_1 in by_id
    assert run_id_2 in by_id
    assert by_id[run_id_1]["uc"] == "uc01"
    assert by_id[run_id_1]["status"] == "done"
    assert by_id[run_id_1]["created_at"]

    # Mới nhất đứng trước
    idx_1 = next(i for i, item in enumerate(listed) if item["run_id"] == run_id_1)
    idx_2 = next(i for i, item in enumerate(listed) if item["run_id"] == run_id_2)
    assert idx_2 < idx_1


def test_run_output_reads_ram_and_trace_file(use_llm):
    use_llm(FakeLLM(NO_TOOL, reply(PROFILE), NO_TOOL, reply(prompt_set())))
    run_id = start()

    out_ram = main.run_output(run_id)
    assert out_ram is not None
    assert out_ram["event"] == "output"
    assert len(out_ram["prompt_set"]["prompts"]) == 32

    main.RUNS.clear()
    out_disk = main.run_output(run_id)
    assert out_disk is not None
    assert out_disk["event"] == "output"
    assert len(out_disk["prompt_set"]["prompts"]) == 32
    assert main.run_output("0" * 32) is None


def test_approval_conflict_when_not_waiting(use_llm):
    use_llm(FakeLLM(NO_TOOL, reply(PROFILE), NO_TOOL, reply(prompt_set())))
    run_id = start()

    r = client.post(
        f"/runs/{run_id}/approval",
        json={"decision": "approve", "reason": "OK", "reviewer": "admin"},
    )
    assert r.status_code == 409

    r_missing = client.post(
        f"/runs/{'0' * 32}/approval",
        json={"decision": "approve", "reason": "OK", "reviewer": "admin"},
    )
    assert r_missing.status_code == 409


def test_approve_blocked_by_claims(use_llm, use_uc03_kb, monkeypatch):
    import agent.graph as graph_mod
    from agent.claims import ClaimReport, ClaimVerdict, Evidence, Location
    from agent.graph import ScriptedWorkflowLLM
    from tests.uc03_fixture import kb

    def fake_fact_check_with_blocking(article, **kwargs):
        unverifiable = ClaimVerdict(
            claim="Sơn giúp giảm 99% hoá đơn tiền điện mỗi tháng.",
            location=Location(heading="Hiệu quả", paragraph=0),
            has_number=True,
            verdict="unverifiable",
            evidence=[
                Evidence(
                    chunk_id=None,
                    url="https://blogmaiton.example/x",
                    quote="giảm 99%",
                    trust_tier="C",
                    stance="supports",
                )
            ],
            action="rewrite",
        )
        return article, ClaimReport(claims=[unverifiable], round=2)

    monkeypatch.setattr(graph_mod, "fact_check_loop", fake_fact_check_with_blocking)
    use_llm(ScriptedWorkflowLLM(kb()))

    r_start = client.post(
        "/runs/uc09",
        json={"brief": BRIEF, "topics": [TOPIC], "auto_approve": False},
    )
    assert r_start.status_code == 200
    run_id = r_start.json()["run_id"]

    r_app = client.post(
        f"/runs/{run_id}/approval",
        json={"decision": "approve", "reason": "Cố duyệt", "reviewer": "admin"},
    )
    assert r_app.status_code == 409
    detail = r_app.json()["detail"]
    blocked_list = detail.get("blocking_claims") or detail.get("claims") or []
    assert len(blocked_list) == 1
    assert "99%" in blocked_list[0]["claim"]


def test_uc09_approval_and_resume_routes(use_llm, use_uc03_kb):
    from agent.graph import ScriptedWorkflowLLM
    from tests.uc03_fixture import kb

    use_llm(ScriptedWorkflowLLM(kb()))
    r_start = client.post(
        "/runs/uc09",
        json={"brief": BRIEF, "topics": [TOPIC], "auto_approve": False},
    )
    assert r_start.status_code == 200
    run_id = r_start.json()["run_id"]

    # Stream dừng khi run đang tạm dừng chờ duyệt (await_approval), kèm dữ liệu bài & claim_report
    got = events(run_id)
    await_ev = next(
        (e for e in got if e["event"] == "decision" and e.get("action") == "await_approval"),
        None,
    )
    assert await_ev is not None
    assert await_ev["item_id"] == "art-01"
    assert "article" in await_ev
    assert "claim_report" in await_ev

    # Duyệt bài 1 -> trả 202 và chuyển bài 1 sang approved, dừng ở bài 2
    use_llm(ScriptedWorkflowLLM(kb()))
    r_approve = client.post(
        f"/runs/{run_id}/approval",
        json={"decision": "approve", "reason": "Đồng ý", "reviewer": "editor"},
    )
    assert r_approve.status_code == 202

    # Resume từ checkpoint (kể cả sau khi xoá RUNS trong RAM) -> trả 202
    main.RUNS.clear()
    use_llm(ScriptedWorkflowLLM(kb()))
    r_resume = client.post(f"/runs/{run_id}/resume")
    assert r_resume.status_code == 202
