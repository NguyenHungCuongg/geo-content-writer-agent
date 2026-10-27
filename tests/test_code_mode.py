"""Test tool `run_code` (Code Mode, Buổi 7): chạy Python của model trong tiến trình con."""

from agent.tools.code_mode import make_run_code_tool

FIXTURE = "tests.code_mode_fixture"


def run(code, functions=("double",), **kw):
    return make_run_code_tool(FIXTURE, functions, **kw).run({"code": code})


def test_prints_result():
    assert run("print(tools.double(21))").data["stdout"].strip() == "42"


def test_vietnamese_output():
    assert "Lỗi sửa" in run("print('Lỗi sửa')").data["stdout"]


def test_only_allowed_functions():
    assert not run("tools.secret()").ok


def test_blocks_imports():
    result = run("import os")
    assert not result.ok and "os" in result.error


def test_allows_safe_imports():
    assert run("import json, collections\nprint(1)").ok


def test_blocks_open():
    assert not run("open('pyproject.toml')").ok


def test_truncates_output():
    result = run("print('x' * 5000)")
    assert len(result.data["stdout"]) == 4000 and result.data["truncated"] is True


def test_syntax_error_reports_traceback():
    result = run("def (")
    assert not result.ok and "SyntaxError" in result.error


def test_kills_infinite_loop():
    result = run("while True: pass", timeout_s=1)
    assert not result.ok and "TimeoutError" in result.error


def test_child_env_has_no_secrets(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    out = run("print(tools.env_keys())", functions=("env_keys",), env={"X": "1"}).data["stdout"]
    assert "GEMINI_API_KEY" not in out and "'X'" in out


def test_description_lists_signatures():
    assert "double(x: int) -> int" in make_run_code_tool(FIXTURE, ["double"]).description
