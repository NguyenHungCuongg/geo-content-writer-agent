"""Test trace ghi ra file JSONL: tiếng Việt, run lỗi, định dạng."""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from agent.trace import EVENTS, TRACES_DIR, Tracer


def read_records(path):
    """Đọc file JSONL, trả về danh sách dict."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").strip().splitlines()]


# --- DoD bắt buộc ---


def test_trace_writes_vietnamese(tmp_path):
    """DoD: ghi 'Sơn chống nóng mái tôn Skyveil' rồi đọc lại đúng."""
    tracer = Tracer("vn", traces_dir=tmp_path)
    tracer.log("input", text="Sơn chống nóng mái tôn Skyveil")

    records = read_records(tmp_path / "vn.jsonl")
    assert records[0]["text"] == "Sơn chống nóng mái tôn Skyveil"


def test_error_run_still_traced(tmp_path):
    """DoD: run lỗi vẫn có dòng event='error' trong file."""
    tracer = Tracer("err", traces_dir=tmp_path)
    tracer.log("input", brief="test")
    tracer.log("error", reason="llm_error", message="Gemini lỗi 500")

    events = [r["event"] for r in read_records(tmp_path / "err.jsonl")]
    assert events == ["input", "error"]


# --- Test bổ sung ---


def test_file_created_on_first_log(tmp_path):
    """File chưa có trước khi log, có ngay sau log đầu tiên."""
    path = tmp_path / "new.jsonl"
    tracer = Tracer("new", traces_dir=tmp_path)
    assert not path.exists()

    tracer.log("input", x=1)
    assert path.exists()


def test_every_line_is_valid_json_with_required_fields(tmp_path):
    """Mỗi dòng parse được thành JSON và có đủ ts, run_id, event."""
    tracer = Tracer("schema", traces_dir=tmp_path)
    tracer.log("input", brief="hello")
    tracer.log("llm_call", model="fake", input_tokens=10, output_tokens=5,
               structured=False, tool_calls=[])
    tracer.log("tool_call", name="echo", args={"n": 1}, ok=True,
               data={"n": 1}, error=None, duration_ms=3)
    tracer.log("output", result="done")

    for record in read_records(tmp_path / "schema.jsonl"):
        assert "ts" in record
        assert record["run_id"] == "schema"
        assert record["event"] in EVENTS


def test_run_id_matches_in_every_record(tmp_path):
    """run_id trong file phải khớp với tracer.run_id."""
    tracer = Tracer("abc123", traces_dir=tmp_path)
    tracer.log("input", x=1)
    tracer.log("decision", action="repair", attempt=1, error="sai schema")
    tracer.log("output", x=2)

    for record in read_records(tmp_path / "abc123.jsonl"):
        assert record["run_id"] == "abc123"


def test_invalid_event_rejected_no_file_written(tmp_path):
    """Event không hợp lệ vẫn bị ValueError, không ghi gì vào file."""
    tracer = Tracer("bad", traces_dir=tmp_path)
    with pytest.raises(ValueError, match="event không hợp lệ"):
        tracer.log("khong_ton_tai", data="x")

    assert not (tmp_path / "bad.jsonl").exists()
    assert tracer.events == []


def test_write_failure_does_not_break_run(tmp_path):
    """Không ghi được file thì run vẫn chạy và event vẫn vào bộ nhớ (app stream từ đó)."""
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("x", encoding="utf-8")
    tracer = Tracer("x", traces_dir=blocker)

    tracer.log("error", reason="llm_error", message="x")
    assert [e["event"] for e in tracer.events] == ["error"]


def test_default_dir_is_repo_traces():
    """Backend phát lại trace từ <gốc repo>/traces, không phụ thuộc thư mục đang chạy."""
    assert TRACES_DIR == Path(__file__).resolve().parents[1] / "traces"


def test_rejected_run_uc01_writes_trace_file(tmp_path):
    """run_uc01 thật (chặn ở bước kiểm input) vẫn để lại file trace có input và error."""
    from agent.llm import FakeLLM
    from agent.uc01 import InputError, run_uc01

    tracer = Tracer(uuid4().hex, traces_dir=tmp_path)
    with pytest.raises(InputError):
        run_uc01("   ", ["sơn chống nóng mái tôn"], llm=FakeLLM(), tracer=tracer)

    records = read_records(tracer.path)
    assert [r["event"] for r in records] == ["input", "error"]
    assert records == tracer.events
