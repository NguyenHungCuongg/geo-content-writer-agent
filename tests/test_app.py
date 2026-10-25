"""Test backend FastAPI bằng FakeLLM: không gọi mạng."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from test_uc01 import BRIEF, PROFILE, TOPIC, prompt_set, reply

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
    r = client.post("/runs", json={"brief": brief, "topics": list(topics)})
    assert r.status_code == 200
    return r.json()["run_id"]


def events(run_id: str) -> list[dict]:
    with client.stream("GET", f"/runs/{run_id}/events") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        return [json.loads(line.removeprefix("data: "))
                for line in r.iter_lines() if line.startswith("data: ")]


def test_run_streams_events_until_output(use_llm):
    use_llm(FakeLLM(reply(PROFILE), reply(prompt_set())))
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
    use_llm(FakeLLM(reply(PROFILE), reply({"prompts": []})))  # sai luật mãi -> repair_failed
    got = events(start())

    errors = [e for e in got if e["event"] == "error"]
    assert len(errors) == 1
    assert errors[0]["reason"] == "repair_failed"


def test_unknown_run_returns_404():
    assert client.get(f"/runs/{'0' * 32}/events").status_code == 404


def test_rejects_oversized_brief():
    body = {"brief": "a" * (main.MAX_BRIEF_CHARS + 1), "topics": [TOPIC]}
    assert client.post("/runs", json=body).status_code == 422


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

    assert asyncio.run(consume()) == ["input", "output"]
