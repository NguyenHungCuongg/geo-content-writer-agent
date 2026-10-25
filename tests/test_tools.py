import math
import time

import httpx
import pytest
import yaml
from pydantic import BaseModel
from test_llm import api_error

from agent.tools import Tool, ToolResult
from agent.tools.brand_kit import load_brand_kit
from agent.tools.dedupe import MAX_PROMPTS, create_dedupe_tool


class SlowArgs(BaseModel):
    delay_s: float


def test_tool_timeout_returns_error():
    attempts = 0

    def slow_fn(args: SlowArgs) -> dict:
        nonlocal attempts
        attempts += 1
        time.sleep(args.delay_s)
        return {"done": True}

    tool = Tool(
        name="slow_tool",
        description="A tool that simulates slow execution",
        args_model=SlowArgs,
        fn=slow_fn,
        timeout_s=0.05,
    )
    started = time.perf_counter()
    result = tool.run({"delay_s": 0.5})

    assert isinstance(result, ToolResult)
    assert result.ok is False
    assert "timeout" in result.error.lower()
    assert time.perf_counter() - started < 0.4  # trả về đúng hạn, không chờ luồng treo
    assert attempts == 1  # quá hạn thì không thử lại


class DummyArgs(BaseModel):
    value: int


def counting_tool(errors_to_raise: list[Exception]) -> tuple[Tool, list[int]]:
    """Tool ném lần lượt các lỗi trong danh sách rồi trả kết quả; đếm số lần bị gọi."""
    attempts = [0]

    def fn(args: DummyArgs) -> dict:
        attempts[0] += 1
        if errors_to_raise:
            raise errors_to_raise.pop(0)
        return {"value": args.value}

    tool = Tool(name="t", description="d", args_model=DummyArgs, fn=fn, backoff_s=0)
    return tool, attempts


@pytest.mark.parametrize("error", [
    ConnectionError("mất mạng"),
    httpx.ConnectError("mất mạng"),
    api_error(429),
    api_error(503),
])
def test_tool_retries_transient_error_and_succeeds(error):
    tool, attempts = counting_tool([error])
    result = tool.run({"value": 42})
    assert result.ok is True
    assert result.data == {"value": 42}
    assert attempts == [2]


def test_tool_fails_after_all_retries():
    tool, attempts = counting_tool([ConnectionError("mất mạng")] * 5)
    result = tool.run({"value": 10})
    assert result.ok is False
    assert "ConnectionError: mất mạng" in result.error
    assert attempts == [3]  # 1 lần đầu + 2 lần thử lại


@pytest.mark.parametrize("error", [
    ValueError("Invalid value"),
    FileNotFoundError("không có file"),
    PermissionError("không có quyền"),
    yaml.YAMLError("YAML hỏng"),
    RuntimeError("lỗi logic"),
    api_error(400),
    api_error(404),
])
def test_tool_does_not_retry_permanent_error(error):
    tool, attempts = counting_tool([error])
    result = tool.run({"value": 10})
    assert result.ok is False
    assert type(error).__name__ in result.error
    assert attempts == [1]  # thử lại vẫn sai nên không thử


def test_load_brand_kit_rejects_outside_path():
    result = load_brand_kit.run({"path": "../.env"})
    assert result.ok is False
    assert (
        "ngoài thư mục" in result.error
        or "allowed" in result.error.lower()
        or "outside" in result.error.lower()
    )


def test_load_brand_kit_success():
    result = load_brand_kit.run({"path": "data/brand/brand_kit.yaml"})
    assert result.ok is True
    assert isinstance(result.data, dict)
    assert result.data["name"] == "Skyveil"


def test_dedupe_drops_near_duplicates():
    # Hai vector có cosine similarity đúng 0.95
    sim = 0.95
    v1 = [1.0, 0.0]
    v2 = [sim, math.sqrt(1 - sim**2)]

    def fake_embedder(texts: list[str]) -> list[list[float]]:
        return [v1, v2]

    tool = create_dedupe_tool(embedder=fake_embedder)
    result = tool.run({
        "prompts": ["Sơn chống nóng mái tôn Skyveil", "Sơn cách nhiệt mái tôn Skyveil"],
        "threshold": 0.9,
    })

    assert result.ok is True
    assert result.data["kept"] == [0]
    assert len(result.data["dropped"]) == 1
    dropped_idx, matched_idx, score = result.data["dropped"][0]
    assert dropped_idx == 1
    assert matched_idx == 0
    assert abs(score - 0.95) < 1e-4


def test_dedupe_keeps_distinct_prompts():
    # Hai vector trực giao, cosine = 0.0
    v1 = [1.0, 0.0]
    v2 = [0.0, 1.0]

    def fake_embedder(texts: list[str]) -> list[list[float]]:
        return [v1, v2]

    tool = create_dedupe_tool(embedder=fake_embedder)
    result = tool.run({
        "prompts": ["Sơn chống nóng mái tôn", "Báo giá sơn tường nhà"],
        "threshold": 0.9,
    })

    assert result.ok is True
    assert result.data["kept"] == [0, 1]
    assert result.data["dropped"] == []


def test_dedupe_fails_when_embedder_returns_too_few_vectors():
    tool = create_dedupe_tool(embedder=lambda texts: [[1.0, 0.0]])
    result = tool.run({"prompts": ["câu một", "câu hai"]})
    assert result.ok is False
    assert "1 vector cho 2 câu" in result.error


def test_dedupe_rejects_more_prompts_than_one_embedding_batch():
    tool = create_dedupe_tool(embedder=lambda texts: [[1.0]] * len(texts))
    result = tool.run({"prompts": [f"câu {i}" for i in range(MAX_PROMPTS + 1)]})
    assert result.ok is False
    assert "đối số sai" in result.error
