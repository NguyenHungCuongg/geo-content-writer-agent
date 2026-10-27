"""Test nén context (Buổi 7) trong vòng lặp agent, bằng LLM giả: không gọi mạng."""

import json

from pydantic import BaseModel, ValidationInfo, model_validator

from agent.llm import FakeLLM, LLMError, LLMResponse, ToolCall
from agent.loop import Checkpoint, run_agent
from agent.tools import Tool
from agent.trace import Tracer


class Answer(BaseModel):
    value: int


class Seen(BaseModel):
    """Chỉ hợp lệ khi validator thấy đúng một kết quả tool từ trước khi compact."""

    value: int

    @model_validator(mode="after")
    def one_observation(self, info: ValidationInfo) -> "Seen":
        if len(info.context["observations"]) != 1:
            raise ValueError("mất observations")
        return self


class EchoArgs(BaseModel):
    n: int


ECHO = Tool("echo", "Trả lại số n", EchoArgs, lambda a: {"n": a.n})

CHECKPOINT = json.dumps({
    "goal": "tìm lỗi X",
    "constraints": ["không đổi API"],
    "current_state": "đã đọc file A",
    "findings": ["lỗi xảy ra ở bước 2"],
    "failed_attempts": [],
    "files": ["A"],
    "open_risks": [],
    "next_action": "đọc file Y",
}, ensure_ascii=False)


def text(value: str) -> LLMResponse:
    return LLMResponse(text=value)


def tool_call(n: int, tokens: int) -> LLMResponse:
    return LLMResponse(tool_calls=[ToolCall(id=f"c{n}", name="echo", args={"n": n})],
                       input_tokens=tokens)


def run(llm, tracer=None, output_model=Answer, **kwargs):
    return run_agent(llm, system="hệ thống", task="nhiệm vụ", output_model=output_model,
                     tracer=tracer or Tracer("test"), **kwargs)


class CompactFails(FakeLLM):
    def generate(self, messages, *, system=None, tools=None, schema=None):
        if schema is Checkpoint:
            raise LLMError("Gemini lỗi 503")
        return super().generate(messages, system=system, tools=tools, schema=schema)


def test_compacts_when_input_tokens_reach_threshold():
    llm = FakeLLM(tool_call(1, tokens=500), text(CHECKPOINT), text("xong"), text('{"value": 3}'))
    tracer = Tracer("test")
    result = run(llm, tracer, tools=[ECHO], compact_at_tokens=500)

    assert result.output == Answer(value=3)
    assert llm.calls[1]["schema"] is Checkpoint
    after = llm.calls[2]["messages"]
    assert len(after) == 1 and after[0].role == "user"
    assert after[0].text.startswith("nhiệm vụ")  # task gốc nguyên văn, đứng đầu
    assert "tìm lỗi X" in after[0].text and "đọc file Y" in after[0].text
    compact = [e for e in tracer.events if e.get("action") == "compact"]
    assert compact[0]["input_tokens_before"] == 500 and compact[0]["messages_after"] == 1
    assert compact[0]["checkpoint"]["goal"] == "tìm lỗi X"
    purposes = [e.get("purpose") for e in tracer.events if e["event"] == "llm_call"]
    assert purposes.count("compact") == 1


def test_no_compaction_below_threshold_or_when_disabled():
    for kwargs in ({"compact_at_tokens": 501}, {}):
        llm = FakeLLM(tool_call(1, tokens=500), text("xong"), text('{"value": 3}'))
        run(llm, tools=[ECHO], **kwargs)
        assert all(c["schema"] is not Checkpoint for c in llm.calls)


def test_observations_survive_compaction():
    llm = FakeLLM(tool_call(1, tokens=500), text(CHECKPOINT), text("xong"), text('{"value": 3}'))
    result = run(llm, output_model=Seen, tools=[ECHO], compact_at_tokens=500)
    assert result.output.value == 3 and result.repairs == 0


def test_failed_compaction_keeps_history():
    llm = FakeLLM(tool_call(1, tokens=500), text('{"goal": ""}'), text("xong"),
                  text('{"value": 3}'))
    tracer = Tracer("test")
    run(llm, tracer, tools=[ECHO], compact_at_tokens=500)
    assert len(llm.calls[2]["messages"]) == 3  # task, lượt model, kết quả tool: không đổi
    assert any(e.get("reason") == "compaction_failed" for e in tracer.events)


def test_llm_error_during_compaction_keeps_history():
    llm = CompactFails(tool_call(1, tokens=500), text("xong"), text('{"value": 3}'))
    tracer = Tracer("test")
    result = run(llm, tracer, tools=[ECHO], compact_at_tokens=500)
    assert result.output.value == 3
    assert any(e.get("reason") == "compaction_failed" for e in tracer.events)
    assert len(llm.calls[1]["messages"]) == 3


def test_rereading_after_compaction_is_not_a_loop():
    # echo(1) 2 lần trước compact, 2 lần sau: không bị coi là lặp (LOOP_REPEAT_LIMIT = 3)
    llm = FakeLLM(tool_call(1, 10), tool_call(1, 500), text(CHECKPOINT),
                  tool_call(1, 10), tool_call(1, 10), text("xong"), text('{"value": 3}'))
    assert run(llm, tools=[ECHO], compact_at_tokens=500, max_iterations=10).output.value == 3
