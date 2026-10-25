import math
import time

from pydantic import BaseModel

from agent.tools import Tool, ToolResult
from agent.tools.brand_kit import load_brand_kit
from agent.tools.dedupe import create_dedupe_tool


class SlowArgs(BaseModel):
    delay_s: float


def slow_fn(args: SlowArgs) -> dict:
    time.sleep(args.delay_s)
    return {"done": True}


def test_tool_timeout_returns_error():
    tool = Tool(
        name="slow_tool",
        description="A tool that simulates slow execution",
        args_model=SlowArgs,
        fn=slow_fn,
        timeout_s=0.05,
        max_retries=1,
    )
    result = tool.run({"delay_s": 0.2})
    assert isinstance(result, ToolResult)
    assert result.ok is False
    assert "timeout" in result.error.lower()


class DummyArgs(BaseModel):
    value: int


def test_tool_retries_and_succeeds():
    attempts = 0

    def flaky_fn(args: DummyArgs) -> dict:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise RuntimeError("Transient error")
        return {"value": args.value}

    tool = Tool(
        name="flaky_tool",
        description="A flaky tool",
        args_model=DummyArgs,
        fn=flaky_fn,
        max_retries=2,
    )
    result = tool.run({"value": 42})
    assert result.ok is True
    assert result.data == {"value": 42}
    assert attempts == 2


def test_tool_fails_after_all_retries():
    attempts = 0

    def fail_fn(args: DummyArgs) -> dict:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("Permanent network error")

    tool = Tool(
        name="fail_tool",
        description="A failing tool",
        args_model=DummyArgs,
        fn=fail_fn,
        max_retries=2,
    )
    result = tool.run({"value": 10})
    assert result.ok is False
    assert "RuntimeError: Permanent network error" in result.error
    assert attempts == 3  # 1 initial + 2 retries


def test_tool_does_not_retry_value_error():
    attempts = 0

    def bad_val_fn(args: DummyArgs) -> dict:
        nonlocal attempts
        attempts += 1
        raise ValueError("Invalid value")

    tool = Tool(
        name="val_error_tool",
        description="A tool raising ValueError",
        args_model=DummyArgs,
        fn=bad_val_fn,
        max_retries=2,
    )
    result = tool.run({"value": 10})
    assert result.ok is False
    assert "ValueError: Invalid value" in result.error
    assert attempts == 1  # Fails immediately without useless retries


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
