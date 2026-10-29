"""Cấu hình chung cho test: không gọi API embedding thật, không ghi trace vào repo."""

import pytest

from agent import trace
from agent.tools import dedupe


def fake_embedder(texts: list[str]) -> list[list[float]]:
    """Câu giống hệt nhau cho cùng một vector, câu khác nhau cho các vector trực giao."""
    unique = list(dict.fromkeys(texts))
    return [[float(text == u) for u in unique] for text in texts]


@pytest.fixture(autouse=True)
def offline_embedder(monkeypatch):
    monkeypatch.setattr(dedupe, "default_gemini_embedder", fake_embedder)


@pytest.fixture(autouse=True)
def isolated_traces(monkeypatch, tmp_path):
    """Tracer("test") của các test không ghi vào traces/ của repo."""
    monkeypatch.setattr(trace, "TRACES_DIR", tmp_path / "traces")
