"""Test vòng lặp agent bằng LLM giả: không gọi mạng."""

import pytest
from pydantic import BaseModel, Field

from agent.llm import FakeLLM, LLMResponse, ToolCall
from agent.loop import AgentStopped, run_agent
from agent.tools import Tool
from agent.trace import Tracer


class Answer(BaseModel):
    value: int = Field(gt=0)


class EchoArgs(BaseModel):
    n: int


ECHO = Tool("echo", "Trả lại số n", EchoArgs, lambda a: {"n": a.n})


def text(value: str) -> LLMResponse:
    return LLMResponse(text=value)


def tool_call(name: str = "echo", n: int = 1) -> LLMResponse:
    return LLMResponse(tool_calls=[ToolCall(id=f"c{n}", name=name, args={"n": n})])


def run(llm, tracer=None, **kwargs):
    return run_agent(llm, system="hệ thống", task="nhiệm vụ", output_model=Answer,
                     tracer=tracer or Tracer("test"), **kwargs)


def test_returns_valid_output_without_repair():
    result = run(FakeLLM(text('{"value": 3}')))
    assert result.output == Answer(value=3)
    assert result.repairs == 0


def test_repairs_invalid_output():
    llm = FakeLLM(text('{"value": -1}'), text('{"value": 2}'))
    tracer = Tracer("test")
    result = run(llm, tracer)

    assert result.output == Answer(value=2)
    assert result.repairs == 1
    repair_request = llm.calls[1]["messages"][-1].text
    assert "value" in repair_request
    assert "greater than 0" in repair_request
    assert [e["action"] for e in tracer.events if e["event"] == "decision"] == ["repair"]


def test_gives_up_after_two_repairs():
    llm = FakeLLM(text("không phải JSON"))
    tracer = Tracer("test")
    with pytest.raises(AgentStopped, match="2 lần sửa") as exc:
        run(llm, tracer)

    assert exc.value.reason == "repair_failed"
    assert len(llm.calls) == 3  # 1 lần đầu + 2 lần sửa
    assert tracer.events[-1]["event"] == "error"


def test_stops_at_max_iterations():
    llm = FakeLLM(*[tool_call(n=i) for i in range(10)])  # đối số khác nhau: không bị coi là lặp
    tracer = Tracer("test")
    with pytest.raises(AgentStopped) as exc:
        run(llm, tracer, tools=[ECHO], max_iterations=4)

    assert exc.value.reason == "max_iterations"
    assert len(llm.calls) == 4
    last = tracer.events[-1]
    assert (last["event"], last["reason"]) == ("error", "max_iterations")


def test_detects_repeated_tool_call():
    llm = FakeLLM(tool_call(n=7))  # luôn gọi echo(7)
    with pytest.raises(AgentStopped) as exc:
        run(llm, tools=[ECHO], max_iterations=8)

    assert exc.value.reason == "loop_detected"
    assert len(llm.calls) == 3


def test_tool_result_is_fed_back_then_finalizes():
    llm = FakeLLM(tool_call(n=5), text("xong"), text('{"value": 5}'))
    tracer = Tracer("test")
    result = run(llm, tracer, tools=[ECHO])

    assert result.output == Answer(value=5)
    assert result.iterations == 2
    tool_message = llm.calls[1]["messages"][-1]
    assert tool_message.role == "tool"
    assert tool_message.result["data"] == {"n": 5}
    assert llm.calls[2]["schema"] is Answer
    assert llm.calls[2]["tools"] is None

    tool_event = next(e for e in tracer.events if e["event"] == "tool_call")
    assert tool_event["name"] == "echo"
    assert "duration_ms" in tool_event


def test_unknown_tool_becomes_observation_not_crash():
    llm = FakeLLM(tool_call(name="khong_ton_tai"), text("xong"), text('{"value": 1}'))
    result = run(llm, tools=[ECHO])

    assert result.output == Answer(value=1)
    error = llm.calls[1]["messages"][-1].result["error"]
    assert "không có tool khong_ton_tai" in error


def test_skips_action_phase_when_no_tools():
    llm = FakeLLM(text('{"value": 1}'))
    result = run(llm)

    assert result.iterations == 0
    assert len(llm.calls) == 1
