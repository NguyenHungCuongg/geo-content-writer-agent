"""Test module đọc trace chỉ-đọc cho trace analyst (Challenge B)."""

import json

import pytest

from agent.tools.traces import list_in, list_traces, read_in, trace_tools


def write(path, events):
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")


@pytest.fixture
def root(tmp_path):
    write(tmp_path / "eval-a.jsonl", [{"event": "input"}, {"event": "output"}])
    write(tmp_path / "eval-b.jsonl", [{"event": "input"}])
    (tmp_path / "note.txt").write_text("không phải trace", encoding="utf-8")
    return tmp_path


def test_lists_and_reads(root):
    assert [t["name"] for t in list_in(root)] == ["eval-a", "eval-b"]
    assert list_in(root, "eval-a*")[0]["lines"] == 2
    assert read_in(root, "eval-a") == [{"event": "input"}, {"event": "output"}]


def test_read_accepts_suffix(root):
    assert read_in(root, "eval-a.jsonl") == read_in(root, "eval-a")


def test_skips_malformed_lines(tmp_path):
    (tmp_path / "x.jsonl").write_text('{"a": 1}\n{"event": "inp\n{"b": 2}\n', encoding="utf-8")
    assert read_in(tmp_path, "x") == [{"a": 1}, {"b": 2}]


@pytest.mark.parametrize("name", ["../secret", "..\\secret", "/etc/passwd", "C:\\x", "sub/a"])
def test_rejects_paths_outside_root(root, name):
    with pytest.raises(ValueError):
        read_in(root, name)


def test_missing_file(root):
    with pytest.raises(FileNotFoundError):
        read_in(root, "eval-zzz")


def test_env_root(root, monkeypatch):
    monkeypatch.setenv("TRACE_QA_DIR", str(root))
    assert [t["name"] for t in list_traces()] == ["eval-a", "eval-b"]


def test_native_read_truncates(tmp_path):
    (tmp_path / "x.jsonl").write_text('{"k": "' + "a" * 100 + '"}\n', encoding="utf-8")
    read = {t.name: t for t in trace_tools(tmp_path, max_chars=40)}["read_trace"]
    data = read.run({"name": "x"}).data
    assert len(data["content"]) == 40 and data["truncated"] is True
