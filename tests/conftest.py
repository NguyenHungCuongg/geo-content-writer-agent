"""Cấu hình chung cho test: không test nào gọi API embedding thật."""

import pytest

from agent.tools import dedupe


def fake_embedder(texts: list[str]) -> list[list[float]]:
    """Câu giống hệt nhau cho cùng một vector, câu khác nhau cho các vector trực giao."""
    unique = list(dict.fromkeys(texts))
    return [[float(text == u) for u in unique] for text in texts]


@pytest.fixture(autouse=True)
def offline_embedder(monkeypatch):
    monkeypatch.setattr(dedupe, "default_gemini_embedder", fake_embedder)
