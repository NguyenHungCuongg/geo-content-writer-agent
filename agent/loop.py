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

Nén context (Buổi 7, D-12): bật bằng `compact_at_tokens`. Sau một vòng có gọi tool, nếu lượt LLM
vừa rồi nhận từ `compact_at_tokens` input token trở lên, harness nhờ model viết một `Checkpoint`
rồi thay cả lịch sử bằng một message: task gốc nguyên văn + checkpoint. `observations` không bị
nén. Nén hỏng thì giữ lịch sử cũ, ghi trace và chạy tiếp.
"""

import json
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import NoReturn
from uuid import uuid4

import yaml
from pydantic import BaseModel, Field, ValidationError

from agent.llm import LLM, LLMError, LLMResponse, Message, ToolCall
from agent.tools import Tool, ToolResult
from agent.trace import Tracer

LOOP_REPEAT_LIMIT = 3

FINALIZE_PROMPT = "Đã đủ thông tin. Trả kết quả cuối cùng dưới dạng JSON đúng schema được yêu cầu."
REPAIR_PROMPT = "Kết quả chưa hợp lệ: {error}. Sửa các lỗi trên và trả lại TOÀN BỘ JSON."

COMPACT_PROMPT = """Context sắp đầy. Ghi lại một checkpoint để tiếp tục công việc sau khi lịch sử \
hội thoại bị xoá. Đây là checkpoint cho bước tiếp theo, không phải bản tóm tắt cuộc trò chuyện.
- GIỮ nguyên: quyết định đã chốt, lỗi chưa giải quyết, yêu cầu và ràng buộc bắt buộc của task.
- RÚT GỌN: output dài của tool chỉ còn vài dòng chính, kèm con số cụ thể nếu có.
- BỎ: log trùng lặp; thử nghiệm đã có kết luận (ghi một dòng vào failed_attempts); dữ liệu đọc \
lại được (ghi tên file hoặc nguồn vào files).
Trả JSON đúng schema."""

CHECKPOINT_HEADER = ("[Checkpoint: lịch sử trước đã được nén. Tiếp tục từ next_action, không làm "
                     "lại các bước đã xong.]")


class Checkpoint(BaseModel):
    """Trạng thái đủ để làm tiếp sau khi nén (slide "Structured checkpoint" + rubric K4)."""

    goal: str = Field(min_length=1)
    constraints: list[str] = []
    current_state: str
    findings: list[str] = []
    failed_attempts: list[str] = []
    files: list[str] = []
    open_risks: list[str] = []
    next_action: str = Field(min_length=1)


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
    compact_at_tokens: int | None = None,
) -> AgentResult:
    run = AgentRun(llm, system, task, tracer or Tracer(uuid4().hex))
    try:
        iterations = run.act(tools, max_iterations, compact_at_tokens)
        output, repairs = run.finalize(output_model, validation_context, max_repairs)
    except LLMError as e:
        run.tracer.log("error", reason="llm_error", message=str(e))
        raise
    return AgentResult(output=output, iterations=iterations, repairs=repairs)


class AgentRun:
    """Một lần chạy agent: giữ model, lời dặn hệ thống, trace và lịch sử hội thoại."""

    def __init__(self, llm: LLM, system: str, task: str, tracer: Tracer):
        self.llm = llm
        self.system = system
        self.tracer = tracer
        self.task = task  # giữ nguyên văn để đặt lại đầu lịch sử sau khi nén
        self.history = [Message.user(task)]
        # Kết quả các tool chạy thành công; validator đối chiếu output với chúng (ví dụ câu trích
        # lấy từ brand kit, D-10).
        self.observations: list[dict] = []

    # ------------------------------------------------------ pha hành động

    def act(
        self, tools: Sequence[Tool], max_iterations: int, compact_at_tokens: int | None = None
    ) -> int:
        """Cho model gọi tool cho tới khi nó thôi gọi. Trả về số vòng đã chạy."""
        if not tools:
            return 0  # không có tool thì không cần pha này

        tools_by_name = {t.name: t for t in tools}
        call_counts = Counter()

        for iteration in range(1, max_iterations + 1):
            response = self.call_llm(tools=list(tools))
            if not response.tool_calls:
                return iteration

            for call in response.tool_calls:
                key = (call.name, json.dumps(call.args, sort_keys=True, ensure_ascii=False))
                call_counts[key] += 1
                if call_counts[key] >= LOOP_REPEAT_LIMIT:
                    self.stop("loop_detected",
                              f"Agent gọi {call.name} với cùng đối số {LOOP_REPEAT_LIMIT} lần")

                result = self.run_tool(tools_by_name, call)
                self.history.append(Message.tool(call, result.model_dump()))
                if result.ok:
                    self.observations.append({"tool": call.name, "data": result.data})

            # Đọc lại dữ liệu đã bị bỏ khi nén là hành vi đúng, không phải vòng lặp.
            if (compact_at_tokens is not None and response.input_tokens >= compact_at_tokens
                    and self.compact(response.input_tokens)):
                call_counts.clear()

        self.stop("max_iterations", f"Agent chưa xong sau {max_iterations} vòng")

    def compact(self, input_tokens_before: int) -> bool:
        """Nhờ model viết Checkpoint rồi thay lịch sử bằng task gốc + checkpoint.

        Chỉ còn một message vì Gemini đòi function_response đi liền function_call: giữ lại vài
        lượt cuối dễ làm lệch cặp đó. Trả False (lịch sử giữ nguyên) nếu nén hỏng.
        """
        messages = self.history + [Message.user(COMPACT_PROMPT)]
        try:
            response = self.llm.generate(messages, system=self.system, schema=Checkpoint)
            self.log_llm_call(response, structured=True, purpose="compact")
            checkpoint = Checkpoint.model_validate_json(response.text or "")
        except (LLMError, ValidationError) as e:
            self.tracer.log("error", reason="compaction_failed", message=str(e))
            return False

        messages_before = len(self.history)
        state = yaml.safe_dump(checkpoint.model_dump(), allow_unicode=True, sort_keys=False)
        self.history = [Message.user(f"{self.task}\n\n{CHECKPOINT_HEADER}\n{state}")]
        self.tracer.log(
            "decision",
            action="compact",
            input_tokens_before=input_tokens_before,
            messages_before=messages_before,
            messages_after=len(self.history),
            checkpoint=checkpoint.model_dump(),
        )
        return True

    def run_tool(self, tools_by_name: dict[str, Tool], call: ToolCall) -> ToolResult:
        """Chạy tool model yêu cầu. Lỗi (kể cả tool không tồn tại) trả về làm quan sát."""
        started = time.perf_counter()
        tool = tools_by_name.get(call.name)
        if tool is None:
            error = f"không có tool {call.name}, chỉ có {sorted(tools_by_name)}"
            result = ToolResult(ok=False, error=error)
        else:
            result = tool.run(call.args)

        self.tracer.log(
            "tool_call",
            name=call.name,
            args=call.args,
            ok=result.ok,
            data=result.data,
            error=result.error,
            duration_ms=round((time.perf_counter() - started) * 1000),
        )
        return result

    # ------------------------------------------------------ pha chốt kết quả

    def finalize(
        self, output_model: type[BaseModel], context: dict | None, max_repairs: int
    ) -> tuple[BaseModel, int]:
        """Ép model trả JSON đúng schema; sai thì gửi lỗi lại cho sửa. Trả (output, số lần sửa)."""
        self.history.append(Message.user(FINALIZE_PROMPT))
        context = {**(context or {}), "observations": self.observations}

        for repairs in range(max_repairs + 1):
            response = self.call_llm(schema=output_model)
            try:
                output = output_model.model_validate_json(response.text or "", context=context)
                return output, repairs
            except ValidationError as e:
                error = describe(e)

            if repairs < max_repairs:
                self.tracer.log("decision", action="repair", attempt=repairs + 1, error=error)
                self.history.append(Message.user(REPAIR_PROMPT.format(error=error)))

        self.stop("repair_failed", f"Output vẫn sai schema sau {max_repairs} lần sửa: {error}")

    # ------------------------------------------------------ dùng chung

    def call_llm(self, **kwargs) -> LLMResponse:
        """Gọi model với lịch sử hiện tại, ghi trace, rồi thêm câu trả lời vào lịch sử."""
        response = self.llm.generate(self.history, system=self.system, **kwargs)
        self.history.append(Message.model(response))
        self.log_llm_call(response, structured=kwargs.get("schema") is not None)
        return response

    def log_llm_call(self, response: LLMResponse, *, structured: bool, **extra) -> None:
        self.tracer.log(
            "llm_call",
            model=self.llm.model,
            structured=structured,
            tool_calls=[c.name for c in response.tool_calls],
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            **extra,
        )

    def stop(self, reason: str, message: str) -> NoReturn:
        """Dừng bất thường thì phải ghi trace rồi báo lỗi, không được im lặng (Buổi 3)."""
        self.tracer.log("error", reason=reason, message=message)
        raise AgentStopped(reason, message)


def describe(error: ValidationError) -> str:
    """Gom lỗi validation thành một dòng dễ đọc để gửi lại cho model."""
    messages = []
    for e in error.errors():
        location = ".".join(str(part) for part in e["loc"])
        message = e["msg"].removeprefix("Value error, ")
        messages.append(f"{location}: {message}" if location else message)
    return "; ".join(messages)
