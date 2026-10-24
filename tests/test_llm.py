"""Test GeminiLLM bằng client giả ở tầng SDK: không gọi mạng, không cần API key."""

import pytest
from google.genai import errors, types
from pydantic import BaseModel

from agent.llm import ConfigError, GeminiLLM, LLMError, Message, ToolCall
from agent.tools import Tool

ENV = {"GEMINI_API_KEY": "fake-key", "GEMINI_MODEL": "fake-model"}


def api_error(code: int) -> errors.APIError:
    return errors.APIError(code, {"error": {"code": code, "message": "lỗi giả", "status": "X"}})


def gemini_response(*parts: types.Part) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=list(parts)))],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=12, candidates_token_count=3
        ),
    )


class FakeClient:
    """Trả lần lượt từng phần tử trong `outcomes`; phần tử là exception thì ném ra."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []
        self.models = self

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def make_llm(client: FakeClient, sleeps: list | None = None) -> GeminiLLM:
    return GeminiLLM(env=ENV, client=client, sleep=(sleeps if sleeps is not None else []).append)


@pytest.mark.parametrize("missing", ["GEMINI_API_KEY", "GEMINI_MODEL"])
def test_missing_env_var_gives_one_line_error(missing):
    env = {k: v for k, v in ENV.items() if k != missing}
    with pytest.raises(ConfigError) as exc:
        GeminiLLM(env=env)
    assert missing in str(exc.value)
    assert "\n" not in str(exc.value)


def test_retries_429_with_backoff_then_succeeds():
    client = FakeClient(api_error(429), api_error(429), gemini_response(types.Part(text="ok")))
    sleeps = []
    response = make_llm(client, sleeps).generate([Message.user("chào")])
    assert response.text == "ok"
    assert len(client.calls) == 3
    assert sleeps == [2.0, 4.0]


def test_gives_up_after_three_retries():
    client = FakeClient(*[api_error(429)] * 4)
    sleeps = []
    with pytest.raises(LLMError, match="3 lần thử lại"):
        make_llm(client, sleeps).generate([Message.user("chào")])
    assert len(client.calls) == 4
    assert sleeps == [2.0, 4.0, 8.0]


def test_does_not_retry_bad_request():
    client = FakeClient(api_error(400))
    with pytest.raises(LLMError, match="400"):
        make_llm(client).generate([Message.user("chào")])
    assert len(client.calls) == 1


def test_parses_tool_calls_and_token_usage():
    call = types.FunctionCall(id="c1", name="load_brand_kit", args={"path": "brand_kit.yaml"})
    response = make_llm(FakeClient(gemini_response(types.Part(function_call=call)))).generate(
        [Message.user("đọc brand kit")]
    )
    assert response.tool_calls == [ToolCall("c1", "load_brand_kit", {"path": "brand_kit.yaml"})]
    assert response.text is None
    assert (response.input_tokens, response.output_tokens) == (12, 3)
    assert response.raw is not None


class Answer(BaseModel):
    value: int


class PathArgs(BaseModel):
    path: str


def test_sends_schema_tools_and_tool_results():
    tool = Tool("load_brand_kit", "Đọc brand kit", PathArgs, lambda a: {})
    call = ToolCall("c1", "load_brand_kit", {"path": "brand_kit.yaml"})
    history = [
        Message.user("đọc brand kit"),
        Message(role="model", tool_calls=[call]),
        Message.tool(call, {"ok": True}),
    ]
    client = FakeClient(gemini_response(types.Part(text='{"value": 1}')))
    make_llm(client).generate(history, system="Bạn là agent", tools=[tool], schema=Answer)

    sent = client.calls[0]
    config = sent["config"]
    assert sent["model"] == "fake-model"
    assert config.system_instruction == "Bạn là agent"
    assert config.response_json_schema == Answer.model_json_schema()
    assert config.tools[0].function_declarations[0].name == "load_brand_kit"

    roles = [c.role for c in sent["contents"]]
    assert roles == ["user", "model", "user"]
    assert sent["contents"][2].parts[0].function_response.response == {"ok": True}
