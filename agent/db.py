"""Kết nối Postgres (+ pgvector) và tạo bảng.

`connect` đọc DATABASE_URL từ `.env`; Postgres chạy bằng `docker compose up -d`. `migrate` chạy
`schema.sql` trong một schema cho trước, nên test và eval có schema riêng, xoá được sau khi chạy.
"""

import os
from collections.abc import Mapping
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg import sql

from agent.llm import ConfigError, require_env

SCHEMA_SQL = Path(__file__).with_name("schema.sql")
UNREACHABLE = "Không kết nối được Postgres ở DATABASE_URL, chạy docker compose up -d"


def connect(env: Mapping[str, str] | None = None) -> psycopg.Connection:
    """`env` để test truyền vào; để trống thì đọc `.env`.

    Connection ở chế độ autocommit: checkpointer LangGraph cần vậy, và lệnh ghi không mất vì quên
    commit.
    """
    if env is None:
        load_dotenv()
        env = os.environ
    url = require_env(env, "DATABASE_URL")
    try:
        return psycopg.connect(url, autocommit=True, connect_timeout=5)
    except psycopg.OperationalError as e:
        # Lý do của libpq (không chứa mật khẩu) phân biệt "chưa chạy compose" với "sai mật khẩu".
        reason = str(e).strip().splitlines()[0]
        raise ConfigError(f"{UNREACHABLE} ({reason})") from e


def migrate(conn: psycopg.Connection, schema: str = "public") -> None:
    """Tạo `schema` nếu chưa có và chạy schema.sql trong đó; chạy lại nhiều lần không lỗi.

    Sau lệnh này search_path của `conn` là `<schema>, public`.
    """
    name = sql.Identifier(schema)
    conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(name))
    conn.execute(sql.SQL("SET search_path TO {}, public").format(name))
    conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
