import pytest

from agent.db import connect, migrate
from agent.llm import ConfigError

UNREACHABLE = "Không kết nối được Postgres ở DATABASE_URL, chạy docker compose up -d"


def test_connect_without_url_names_variable():
    with pytest.raises(ConfigError, match="DATABASE_URL"):
        connect({})


def test_connect_unreachable_says_run_compose():
    with pytest.raises(ConfigError) as e:
        connect({"DATABASE_URL": "postgresql://postgres:s3cret@127.0.0.1:1/postgres"})
    assert str(e.value).startswith(UNREACHABLE)
    assert "s3cret" not in str(e.value)


def test_migrate_is_idempotent(db):
    schema = db.execute("select current_schema()").fetchone()[0]
    assert schema.startswith("test_")
    migrate(db, schema)
    migrate(db, schema)
    assert db.execute("select to_regclass(%s)", (f"{schema}.runs",)).fetchone()[0] is not None


def test_vector_extension_lives_in_public(db):
    row = db.execute(
        "select extnamespace::regnamespace::text from pg_extension where extname = 'vector'"
    ).fetchone()
    assert row == ("public",)
    db.execute("select '[1,2,3]'::vector")  # kiểu vector dùng được từ schema test


def test_connect_autocommits(db):
    assert db.autocommit
