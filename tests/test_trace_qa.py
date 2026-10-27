"""Test trace analyst (Challenge B) bằng LLM giả: không gọi mạng."""

import json

import pytest

from agent.llm import FakeLLM, LLMResponse, ToolCall
from agent.loop import AgentStopped
from agent.trace import Tracer
from agent.trace_qa import report, run_trace_qa, trace_qa_llm


def text(value: str, tokens: int = 0) -> LLMResponse:
    return LLMResponse(text=value, input_tokens=tokens)


def call(name: str, args: dict, tokens: int = 0) -> LLMResponse:
    return LLMResponse(tool_calls=[ToolCall(id="c", name=name, args=args)], input_tokens=tokens)


@pytest.fixture
def traces(tmp_path):
    events = [{"run_id": "eval-a", "event": e} for e in ("input", "decision", "output")]
    (tmp_path / "eval-a.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    (tmp_path / "eval-b.jsonl").write_text('{"run_id": "eval-b"}\n', encoding="utf-8")
    return tmp_path


def test_native_mode_reads_traces_and_answers(traces):
    llm = FakeLLM(call("read_trace", {"name": "eval-a"}), text("xong"),
                  text('{"answer": "a có 1 repair", "evidence": ["eval-a"]}'))
    assert run_trace_qa("?", "native", traces_dir=traces, llm=llm).evidence == ["eval-a"]
    assert "eval-a" in str(llm.calls[1]["messages"][-1].result)  # raw log vào context


def test_code_mode_only_stdout_reaches_model(traces):
    code = "print(len(tools.read_trace('eval-a')))"
    llm = FakeLLM(call("run_code", {"code": code}), text("xong"),
                  text('{"answer": "3 event", "evidence": ["eval-a"]}'))
    run_trace_qa("?", "code", traces_dir=traces, llm=llm)
    assert llm.calls[1]["messages"][-1].result["data"]["stdout"].strip() == "3"
    assert [t.name for t in llm.calls[0]["tools"]] == ["run_code"]


def test_evidence_must_exist(traces):
    llm = FakeLLM(text("xong"), text('{"answer": "x", "evidence": ["eval-zzz"]}'))
    with pytest.raises(AgentStopped) as exc:
        run_trace_qa("?", "native", traces_dir=traces, llm=llm)
    assert exc.value.reason == "repair_failed"


def test_evidence_accepts_jsonl_suffix(traces):
    llm = FakeLLM(text("xong"), text('{"answer": "x", "evidence": ["eval-a.jsonl"]}'))
    assert run_trace_qa("?", "native", traces_dir=traces, llm=llm).evidence == ["eval-a"]


def test_native_compacts_past_threshold(traces):
    checkpoint = json.dumps({"goal": "g", "current_state": "s", "next_action": "n"})
    llm = FakeLLM(call("read_trace", {"name": "eval-a"}, tokens=50), text(checkpoint),
                  text("xong"), text('{"answer": "x", "evidence": ["eval-a"]}'))
    tracer = Tracer("test")
    run_trace_qa("?", "native", traces_dir=traces, compact_at=50, llm=llm, tracer=tracer)
    assert any(e.get("action") == "compact" for e in tracer.events)


def test_report_shows_tokens_and_compaction():
    events = [
        {"event": "llm_call", "tool_calls": ["read_trace"], "input_tokens": 500,
         "output_tokens": 10},
        {"event": "llm_call", "purpose": "compact", "tool_calls": [], "input_tokens": 520,
         "output_tokens": 80},
        {"event": "decision", "action": "compact", "input_tokens_before": 500,
         "checkpoint": {"goal": "tìm lỗi"}},
        {"event": "llm_call", "tool_calls": [], "input_tokens": 120, "output_tokens": 5},
    ]
    out = report(events)
    assert "[compact] 500 → 120" in out and "tìm lỗi" in out
    assert "1140" in out and "95" in out  # tổng input, tổng output


def test_trace_qa_model_override(monkeypatch):
    monkeypatch.setenv("TRACE_QA_MODEL", "m2")
    monkeypatch.setenv("GEMINI_MODEL", "m1")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert trace_qa_llm().model == "m2"


@pytest.mark.parametrize("sub", ["missing", "empty"])
def test_rejects_missing_or_empty_traces_dir(tmp_path, sub):
    if sub == "empty":
        (tmp_path / sub).mkdir()
    llm = FakeLLM(text("xong"))
    with pytest.raises(ValueError):
        run_trace_qa("?", "native", traces_dir=tmp_path / sub, llm=llm)
    assert len(llm.calls) == 0
