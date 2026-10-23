import importlib
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GEMINI_VARS = {"GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_EMBED_MODEL"}


@pytest.mark.parametrize("name", ["agent", "evals"])
def test_package_imports(name):
    importlib.import_module(name)


def _env_example() -> dict[str, str]:
    pairs = {}
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            pairs[key.strip()] = value.strip()
    return pairs


def test_env_example_lists_gemini_vars():
    assert GEMINI_VARS <= _env_example().keys()


def test_env_example_has_no_values():
    assert {k: v for k, v in _env_example().items() if v} == {}


def _ignored(path: str) -> bool:
    r = subprocess.run(["git", "check-ignore", "-q", "--no-index", path], cwd=ROOT)
    assert r.returncode in (0, 1), f"git check-ignore lỗi với {path}"
    return r.returncode == 0


@pytest.mark.parametrize("path", [
    ".env",
    ".env.local",
    "traces/0a1b2c.jsonl",
    ".venv/pyvenv.cfg",
    "geo_content_writer_agent.egg-info/PKG-INFO",
    "agent/__pycache__/x.pyc",
])
def test_gitignore_ignores(path):
    assert _ignored(path)


@pytest.mark.parametrize("path", [
    ".env.example",
    "traces/samples/0a1b2c.jsonl",
    "traces/samples/.gitkeep",
])
def test_gitignore_keeps(path):
    assert not _ignored(path)
