"""Test trace ghi ra file JSONL: tiếng Việt, run lỗi, định dạng."""

import json
from uuid import uuid4

import pytest

from agent.trace import EVENTS, Tracer


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


# --- Integration test: chạy UC-01 với FakeLLM, kiểm trace file ---


def test_run_uc01_produces_trace_file(tmp_path):
    """Chạy UC-01 với FakeLLM, kiểm trace file có đủ event cần thiết."""
    from agent.llm import FakeLLM, LLMResponse
    from agent.uc01 import run_uc01

    brief = (
        "Skyveil là xưởng sơn chống nóng ở TP.HCM. "
        "Khách của bên mình chủ yếu là chủ nhà phố mái tôn."
    )
    topic = "sơn chống nóng mái tôn"
    persona = "Chủ nhà phố mái tôn"

    profile_json = json.dumps({
        "name": "Skyveil",
        "about": "Xưởng sơn chống nóng ở TP.HCM",
        "personas": [persona],
        "sources": {
            "name": "Skyveil là xưởng sơn chống nóng ở TP.HCM.",
            "about": "Skyveil là xưởng sơn chống nóng ở TP.HCM.",
            "personas": "Khách của bên mình chủ yếu là chủ nhà phố mái tôn.",
        },
    }, ensure_ascii=False)

    intents = ["informational", "commercial", "transactional", "navigational"]
    prompts = []
    for i in range(32):
        branded = i in (3, 7)
        prompts.append({
            "id": f"p{i:02d}",
            "text": f"Skyveil có bán sơn R200 không? ({i})" if branded else f"Câu hỏi số {i}",
            "intent": intents[i % 4],
            "topic": topic,
            "persona": persona,
            "keywords": ["sơn chống nóng"],
            "mentions_brand": branded,
        })
    prompt_set_json = json.dumps({"prompts": prompts}, ensure_ascii=False)

    llm = FakeLLM(LLMResponse(text=profile_json), LLMResponse(text=prompt_set_json))
    tracer = Tracer(uuid4().hex, traces_dir=tmp_path)

    run_uc01(brief, [topic], llm=llm, tracer=tracer)

    records = read_records(tracer.path)
    events = [r["event"] for r in records]

    # Trace phải mở bằng "input" và đóng bằng "output"
    assert events[0] == "input"
    assert events[-1] == "output"
    # Phải có ít nhất 1 lần gọi LLM
    assert "llm_call" in events
    # run_id phải nhất quán
    assert all(r["run_id"] == tracer.run_id for r in records)
    # llm_call phải ghi token count
    llm_records = [r for r in records if r["event"] == "llm_call"]
    assert all("input_tokens" in r for r in llm_records)
    assert all("output_tokens" in r for r in llm_records)
