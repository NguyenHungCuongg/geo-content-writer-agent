"""Lớp duy nhất nói chuyện với Gemini.

Phần còn lại của agent chỉ biết interface `LLM` (hàm `generate`), nên test truyền được LLM giả
mà không gọi mạng. `GeminiLLM` là bản thật: đọc `.env`, gọi SDK `google-genai`, retry khi
bị giới hạn tốc độ (429). Tên model đọc từ GEMINI_MODEL, không ghi cứng trong code (D-02).
"""

import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from agent.tools import Tool

# Lỗi tạm thời đáng thử lại: 429 vượt rate limit, 500/504 lỗi tạm phía server, 503 model quá tải.
RETRYABLE_CODES = {429, 500, 503, 504}
# Một request sinh 30+ prompt có thể mất cả phút; quá 2 phút coi như kết nối treo.
TIMEOUT_MS = 120_000


class ConfigError(Exception):
    """Thiếu cấu hình (ví dụ API key). Thông báo một dòng, in thẳng cho người dùng."""


class LLMError(Exception):
    """Gọi LLM thất bại sau khi đã retry."""


# ------------------------------------------------------------ dữ liệu chung


@dataclass(frozen=True)
class ToolCall:
    id: str | None  # Gemini có thể không gửi id; giữ nguyên None để khớp lời gọi gốc
    name: str
    args: dict


@dataclass
class LLMResponse:
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    raw: Any = None  # nội dung gốc của provider, gửi lại nguyên vẹn ở lượt sau


@dataclass
class Message:
    """Một lượt trong hội thoại, không phụ thuộc provider."""

    role: Literal["user", "model", "tool"]
    text: str | None = None
    # Lượt của model: các tool model muốn gọi, và nội dung gốc của provider.
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = None
    # Lượt của tool: lời gọi được trả lời và kết quả của nó.
    call: ToolCall | None = None
    result: dict | None = None

    @classmethod
    def user(cls, text: str) -> "Message":
        return cls(role="user", text=text)

    @classmethod
    def model(cls, response: LLMResponse) -> "Message":
        return cls(role="model", text=response.text, tool_calls=response.tool_calls,
                   raw=response.raw)

    @classmethod
    def tool(cls, call: ToolCall, result: dict) -> "Message":
        return cls(role="tool", call=call, result=result)


class LLM(Protocol):
    model: str

    def generate(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        tools: list[Tool] | None = None,
        schema: type[BaseModel] | None = None,
    ) -> LLMResponse:
        """Gọi model một lần. Có `schema` thì model phải trả JSON theo schema đó."""
        ...


class FakeLLM:
    """LLM giả cho test và demo không tốn quota.

    Trả lần lượt các response soạn sẵn; hết danh sách thì lặp lại response cuối.
    Mỗi lần gọi được lưu vào `calls` để test kiểm model đã nhận gì.
    """

    model = "fake"

    def __init__(self, *responses: LLMResponse):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def generate(self, messages, *, system=None, tools=None, schema=None) -> LLMResponse:
        self.calls.append(
            {"messages": list(messages), "system": system, "tools": tools, "schema": schema}
        )
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


# ------------------------------------------------------------------- Gemini


def require_env(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"Thiếu biến môi trường {name} trong .env (xem .env.example)")
    return value


class GeminiLLM:
    def __init__(
        self,
        *,
        env: Mapping[str, str] | None = None,
        client: Any = None,
        max_retries: int = 3,
        backoff_s: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        """`env` và `client` để test truyền vào; để trống thì đọc `.env` và tạo client thật."""
        if env is None:
            load_dotenv()
            env = os.environ
        self.model = require_env(env, "GEMINI_MODEL")
        self.client = client or genai.Client(
            api_key=require_env(env, "GEMINI_API_KEY"),
            http_options=types.HttpOptions(timeout=TIMEOUT_MS),
        )
        self.max_retries = max_retries
        self.backoff_s = backoff_s
        self.sleep = sleep

    def generate(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        tools: list[Tool] | None = None,
        schema: type[BaseModel] | None = None,
    ) -> LLMResponse:
        config = types.GenerateContentConfig(
            system_instruction=system,
            tools=declare_tools(tools),
            response_mime_type="application/json" if schema else None,
            response_json_schema=schema.model_json_schema() if schema else None,
        )
        response = self.call_with_retry(to_contents(messages), config)
        return parse_response(response)

    def call_with_retry(
        self, contents: list[types.Content], config: types.GenerateContentConfig
    ) -> types.GenerateContentResponse:
        """Thử lại khi gặp lỗi tạm thời hoặc lỗi mạng, tối đa `max_retries` lần.

        Chờ 2s, 4s, 8s...; nếu Gemini báo thời gian chờ (RetryInfo của lỗi 429) thì chờ đúng
        thời gian đó.
        """
        for attempt in range(self.max_retries + 1):
            try:
                return self.client.models.generate_content(
                    model=self.model, contents=contents, config=config
                )
            except errors.APIError as e:
                if e.code not in RETRYABLE_CODES:
                    raise LLMError(f"Gemini lỗi {e.code}: {e.message}") from e
                failure, delay = f"lỗi {e.code}: {e.message}", retry_delay(e)
            except httpx.TransportError as e:
                failure, delay = f"lỗi mạng: {e!r}", 0.0
            if attempt == self.max_retries:
                raise LLMError(f"Gemini vẫn {failure} sau {self.max_retries} lần thử lại")
            self.sleep(max(delay, self.backoff_s * 2**attempt))


def retry_delay(error: errors.APIError) -> float:
    """Số giây Gemini đề nghị chờ (RetryInfo.retryDelay, ví dụ "37s"); không có thì 0."""
    body = error.details if isinstance(error.details, dict) else {}
    for detail in body.get("error", {}).get("details", []):
        if detail.get("@type", "").endswith("RetryInfo"):
            return float(detail.get("retryDelay", "0s").rstrip("s"))
    return 0.0


def declare_tools(tools: list[Tool] | None) -> list[types.Tool] | None:
    """Khai báo tool cho Gemini: tên, mô tả, schema đối số."""
    if not tools:
        return None
    declarations = [
        types.FunctionDeclaration(
            name=t.name,
            description=t.description,
            parameters_json_schema=t.args_model.model_json_schema(),
        )
        for t in tools
    ]
    return [types.Tool(function_declarations=declarations)]


def to_contents(messages: list[Message]) -> list[types.Content]:
    """Đổi hội thoại sang định dạng Gemini. Các kết quả tool liền nhau gộp vào một lượt.

    Lượt model rỗng (bị chặn SAFETY, RECITATION...) bị bỏ: Gemini từ chối lượt không có `parts`.
    """
    contents: list[types.Content] = []
    for m in messages:
        if m.role == "user":
            contents.append(types.Content(role="user", parts=[types.Part(text=m.text)]))
        elif m.role == "model":
            content = m.raw if m.raw is not None else model_content(m)
            if content.parts:
                contents.append(content)
        else:
            add_tool_result(contents, m)
    return contents


def add_tool_result(contents: list[types.Content], m: Message) -> None:
    part = types.Part(function_response=types.FunctionResponse(
        id=m.call.id, name=m.call.name, response=m.result
    ))
    previous = contents[-1] if contents else None
    if previous and previous.role == "user" and previous.parts[0].function_response:
        previous.parts.append(part)
    else:
        contents.append(types.Content(role="user", parts=[part]))


def model_content(m: Message) -> types.Content:
    """Dựng lại lượt của model khi không có nội dung gốc (ví dụ hội thoại do test tạo)."""
    parts = [types.Part(text=m.text)] if m.text else []
    parts += [
        types.Part(function_call=types.FunctionCall(id=c.id, name=c.name, args=c.args))
        for c in m.tool_calls
    ]
    return types.Content(role="model", parts=parts)


def parse_response(response: types.GenerateContentResponse) -> LLMResponse:
    content = response.candidates[0].content if response.candidates else None
    parts = (content.parts or []) if content else []

    text = "".join(p.text for p in parts if p.text and not p.thought) or None
    calls = [p.function_call for p in parts if p.function_call]
    tool_calls = [ToolCall(id=c.id, name=c.name, args=dict(c.args or {})) for c in calls]

    usage = response.usage_metadata
    return LLMResponse(
        text=text,
        tool_calls=tool_calls,
        input_tokens=(usage.prompt_token_count or 0) if usage else 0,
        output_tokens=(usage.candidates_token_count or 0) if usage else 0,
        raw=content,
    )
