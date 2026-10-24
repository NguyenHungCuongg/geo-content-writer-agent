"""Vòng lặp agent (Buổi 3): model chọn bước tiếp theo, harness thực thi và quyết định khi nào dừng.

Pha 1, hành động: model được gọi tool tự do. Harness chạy tool, đưa kết quả trở lại làm quan sát,
lặp cho tới khi model thôi gọi tool.
Pha 2, chốt kết quả: gọi model kèm schema, validate bằng Pydantic. Sai thì gửi lỗi lại cho model
sửa, tối đa `max_repairs` lần.

Điều kiện dừng:
- đạt mục tiêu: output qua validator -> trả AgentResult
- hết ngân sách: chạm `max_iterations` -> AgentStopped("max_iterations")
- phát hiện lặp: cùng tool, cùng đối số gọi LOOP_REPEAT_LIMIT lần -> AgentStopped("loop_detected")
- hết lượt sửa: vẫn sai schema sau `max_repairs` lần sửa -> AgentStopped("repair_failed")
"""

import json
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from agent.llm import LLM, LLMError, LLMResponse, Message, ToolCall
from agent.tools import Tool, ToolResult
from agent.trace import Tracer

LOOP_REPEAT_LIMIT = 3

FINALIZE_PROMPT = "Đã đủ thông tin. Trả kết quả cuối cùng dưới dạng JSON đúng schema được yêu cầu."
REPAIR_PROMPT = "Kết quả chưa hợp lệ: {error}. Sửa các lỗi trên và trả lại TOÀN BỘ JSON."


class AgentStopped(Exception):
    """Agent dừng bất thường. `reason` là max_iterations, loop_detected hoặc repair_failed."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


@dataclass
class AgentResult:
    output: BaseModel
    iterations: int  # số vòng ở pha hành động
    repairs: int     # số lần model phải sửa output


def run_agent(
    llm: LLM,
    *,
    system: str,
    task: str,
    output_model: type[BaseModel],
    tools: Sequence[Tool] = (),
    validation_context: dict | None = None,
    tracer: Tracer | None = None,
    max_iterations: int = 8,
    max_repairs: int = 2,
) -> AgentResult:
    tracer = tracer or Tracer(uuid4().hex)
    history = [Message.user(task)]
    try:
        iterations = act(llm, history, system, tools, tracer, max_iterations)
        output, repairs = finalize(
            llm, history, system, output_model, validation_context, tracer, max_repairs
        )
    except LLMError as e:
        tracer.log("error", reason="llm_error", message=str(e))
        raise
    return AgentResult(output=output, iterations=iterations, repairs=repairs)


# ------------------------------------------------------------ pha hành động


def act(llm, history, system, tools, tracer, max_iterations) -> int:
    """Cho model gọi tool cho tới khi nó thôi gọi. Trả về số vòng đã chạy."""
    if not tools:
        return 0  # không có tool thì không cần pha này

    tools_by_name = {t.name: t for t in tools}
    call_counts = Counter()

    for iteration in range(1, max_iterations + 1):
        response = call_llm(llm, history, tracer, system=system, tools=list(tools))
        history.append(Message.model(response))
        if not response.tool_calls:
            return iteration

        for call in response.tool_calls:
            key = (call.name, json.dumps(call.args, sort_keys=True, ensure_ascii=False))
            call_counts[key] += 1
            if call_counts[key] >= LOOP_REPEAT_LIMIT:
                stop(tracer, "loop_detected",
                     f"Agent gọi {call.name} với cùng đối số {LOOP_REPEAT_LIMIT} lần, dừng lại")

            result = run_tool(tools_by_name, call, tracer)
            history.append(Message.tool(call, result.model_dump()))

    stop(tracer, "max_iterations", f"Agent chưa xong sau {max_iterations} vòng, dừng theo giới hạn")


def run_tool(tools_by_name: dict[str, Tool], call: ToolCall, tracer: Tracer) -> ToolResult:
    """Chạy tool model yêu cầu. Lỗi (kể cả tool không tồn tại) trả về làm quan sát cho model."""
    started = time.perf_counter()
    tool = tools_by_name.get(call.name)
    if tool is None:
        error = f"không có tool {call.name}, chỉ có {sorted(tools_by_name)}"
        result = ToolResult(ok=False, error=error)
    else:
        result = tool.run(call.args)

    tracer.log(
        "tool_call",
        name=call.name,
        args=call.args,
        ok=result.ok,
        data=result.data,
        error=result.error,
        duration_ms=round((time.perf_counter() - started) * 1000),
    )
    return result


# ------------------------------------------------------------ pha chốt kết quả


def finalize(llm, history, system, output_model, context, tracer, max_repairs):
    """Ép model trả JSON đúng schema; sai thì gửi lỗi lại cho sửa. Trả về (output, số lần sửa)."""
    history.append(Message.user(FINALIZE_PROMPT))

    for repairs in range(max_repairs + 1):
        response = call_llm(llm, history, tracer, system=system, schema=output_model)
        history.append(Message.model(response))
        try:
            return output_model.model_validate_json(response.text or "", context=context), repairs
        except ValidationError as e:
            error = describe(e)

        if repairs < max_repairs:
            tracer.log("decision", action="repair", attempt=repairs + 1, error=error)
            history.append(Message.user(REPAIR_PROMPT.format(error=error)))

    stop(tracer, "repair_failed", f"Output vẫn sai schema sau {max_repairs} lần sửa: {error}")


def describe(error: ValidationError) -> str:
    """Gom lỗi validation thành một dòng dễ đọc để gửi lại cho model."""
    messages = []
    for e in error.errors():
        location = ".".join(str(part) for part in e["loc"])
        message = e["msg"].removeprefix("Value error, ")
        messages.append(f"{location}: {message}" if location else message)
    return "; ".join(messages)


# ------------------------------------------------------------ dùng chung


def call_llm(llm: LLM, history: list[Message], tracer: Tracer, **kwargs) -> LLMResponse:
    response = llm.generate(history, **kwargs)
    tracer.log(
        "llm_call",
        model=llm.model,
        structured=kwargs.get("schema") is not None,
        tool_calls=[c.name for c in response.tool_calls],
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
    )
    return response


def stop(tracer: Tracer, reason: str, message: str):
    """Dừng bất thường thì phải ghi trace rồi báo lỗi, không được im lặng (Buổi 3)."""
    tracer.log("error", reason=reason, message=message)
    raise AgentStopped(reason, message)
