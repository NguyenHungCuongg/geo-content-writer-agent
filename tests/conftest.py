"""Cấu hình chung cho test: không gọi API embedding thật, không ghi trace vào repo."""

import os
import secrets
from pathlib import Path

import pytest
from dotenv import dotenv_values
from psycopg import sql

from agent import trace
from agent.db import connect, migrate
from agent.tools import dedupe

ROOT = Path(__file__).resolve().parent.parent


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


@pytest.fixture
def db():
    """Connection tới schema test_<hex> mới, đã migrate; schema bị xoá sau test."""
    url = os.environ.get("DATABASE_URL") or dotenv_values(ROOT / ".env").get("DATABASE_URL")
    if not url:
        if os.environ.get("CI"):
            pytest.fail("CI phải có DATABASE_URL để chạy test DB")
        pytest.skip("Chưa có DATABASE_URL: chạy docker compose up -d rồi điền .env")
    try:
        conn = connect({"DATABASE_URL": url})
    except Exception as e:
        if os.environ.get("CI"):
            pytest.fail(f"CI không kết nối được Postgres: {e}")
        pytest.skip(f"Chưa kết nối được Postgres: {e}")
    schema = f"test_{secrets.token_hex(4)}"
    migrate(conn, schema)
    yield conn
    conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
    conn.close()
