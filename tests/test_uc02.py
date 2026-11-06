"""Test cho UC-02 agent (agent/uc02.py) và các công cụ liên quan."""

import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent.kb import Chunk, Citation, MemoryKB
from agent.llm import FakeLLM, LLMResponse, ToolCall
from agent.tools.kb import kb_ingest_tool, kb_search_tool
from agent.tools.web import Page
from agent.uc02 import ResearchReport, format_citation, run_uc02

ROOT = Path(__file__).resolve().parent.parent


def test_format_citation():
    c = Citation(n=1, chunk_id="abc:0", url="https://moc.gov.vn", quote="QCVN 09:2017")
    formatted = format_citation(c)
    assert formatted == '[1] https://moc.gov.vn "QCVN 09:2017"'


def test_validator_queries_at_least_three():
    # Ít hơn 3 truy vấn khác nhau -> lỗi
    with pytest.raises(ValidationError, match="queries phải có ít nhất 3 câu khác nhau"):
        ResearchReport.model_validate({
            "topic": "sơn chống nóng",
            "queries": ["sơn chống nóng", "sơn chống nóng"],
            "answers": [],
        })


def test_validator_bracket_citations_must_exist():
    # Câu trả lời chứa [1] và [2] nhưng chỉ có citation [1] -> lỗi
    c1 = Citation(n=1, chunk_id="c:0", url="https://moc.gov.vn", quote="Nội dung 1")
    with pytest.raises(ValidationError, match="chưa có trong danh sách citations"):
        ResearchReport.model_validate({
            "topic": "sơn chống nóng",
            "queries": ["q1", "q2", "q3"],
            "answers": [
                {
                    "question": "Câu 1?",
                    "answer": "Sơn giảm nhiệt theo tiêu chuẩn [1] và độ bền [2].",
                    "citations": [c1.model_dump()],
                    "insufficient": False,
                }
            ],
        })


def test_validator_insufficient_rules():
    # insufficient=True nhưng lại có citation -> lỗi
    c1 = Citation(n=1, chunk_id="c:0", url="https://moc.gov.vn", quote="Nội dung 1")
    with pytest.raises(ValidationError, match="insufficient=True thì không được có citation"):
        ResearchReport.model_validate({
            "topic": "sơn chống nóng",
            "queries": ["q1", "q2", "q3"],
            "answers": [
                {
                    "question": "Câu không nguồn?",
                    "answer": "Hiện không đủ nguồn thông tin.",
                    "citations": [c1.model_dump()],
                    "insufficient": True,
                }
            ],
        })

    # insufficient=True nhưng answer không báo "không đủ nguồn" -> lỗi
    with pytest.raises(ValidationError, match="phải là câu báo không đủ nguồn"):
        ResearchReport.model_validate({
            "topic": "sơn chống nóng",
            "queries": ["q1", "q2", "q3"],
            "answers": [
                {
                    "question": "Câu không nguồn?",
                    "answer": "Không tìm thấy dữ liệu liên quan ở bất kỳ đâu.",
                    "citations": [],
                    "insufficient": True,
                }
            ],
        })


def test_validator_check_citation_with_kb_context():
    chunk = Chunk(
        id="moc:0",
        url="https://moc.gov.vn/qcvn",
        domain="moc.gov.vn",
        title="Quy chuẩn",
        fetched_at="2026-11-05T00:00:00Z",
        trust_tier="A",
        text="Hệ số phản xạ nhiệt của mái công trình đạt 0.70.",
    )
    kb = MemoryKB([chunk])

    # Trích dẫn đúng đoạn trích -> hợp lệ
    c_good = Citation(n=1, chunk_id="moc:0", url="https://moc.gov.vn/qcvn", quote="đạt 0.70")
    report = ResearchReport.model_validate(
        {
            "topic": "tiêu chuẩn mái",
            "queries": ["q1", "q2", "q3"],
            "answers": [
                {
                    "question": "Hệ số bao nhiêu?",
                    "answer": "Theo quy định, hệ số đạt 0.70 [1].",
                    "citations": [c_good.model_dump()],
                    "insufficient": False,
                }
            ],
        },
        context={"kb": kb},
    )
    assert len(report.answers) == 1

    # Trích dẫn sai đoạn trích -> lỗi
    c_bad = Citation(n=1, chunk_id="moc:0", url="https://moc.gov.vn/qcvn", quote="đạt 0.99")
    with pytest.raises(ValidationError, match="không nằm trong nội dung"):
        ResearchReport.model_validate(
            {
                "topic": "tiêu chuẩn mái",
                "queries": ["q1", "q2", "q3"],
                "answers": [
                    {
                        "question": "Hệ số bao nhiêu?",
                        "answer": "Hệ số đạt 0.99 [1].",
                        "citations": [c_bad.model_dump()],
                        "insufficient": False,
                    }
                ],
            },
            context={"kb": kb},
        )


def test_run_uc02_offline_agent_loop():
    """Chạy vòng lặp run_uc02 với FakeLLM và MemoryKB."""
    chunk = Chunk(
        id="tuoitre:0",
        url="https://tuoitre.vn/nang-nong",
        domain="tuoitre.vn",
        title="Nắng nóng",
        fetched_at="2026-11-05T00:00:00Z",
        trust_tier="B",
        text="Nhiệt độ mặt mái tôn có thể vượt ngưỡng 60 độ C vào giữa trưa hè.",
    )
    kb = MemoryKB([chunk])

    report_data = {
        "topic": "nhiệt độ mái tôn",
        "queries": [
            "nhiệt độ mái tôn mùa hè",
            "mái tôn nóng bao nhiêu độ",
            "giải pháp làm mát mái tôn",
        ],
        "answers": [
            {
                "question": "Mái tôn nóng bao nhiêu độ vào buổi trưa?",
                "answer": "Vào buổi trưa hè, nhiệt độ mặt mái tôn có thể vượt ngưỡng 60 độ C [1].",
                "citations": [
                    {
                        "n": 1,
                        "chunk_id": "tuoitre:0",
                        "url": "https://tuoitre.vn/nang-nong",
                        "quote": "vượt ngưỡng 60 độ C",
                    }
                ],
                "insufficient": False,
            },
            {
                "question": "Thủ đô của Pháp là gì?",
                "answer": "Hiện không đủ nguồn thông tin về câu hỏi này trong kho tri thức.",
                "citations": [],
                "insufficient": True,
            },
        ],
    }

    # FakeLLM:
    # Vòng 1 gọi tool kb_search
    # Vòng 2 trả kết quả ResearchReport hoàn chỉnh
    llm = FakeLLM(
        LLMResponse(
            text="Tìm kiếm trong kho tri thức",
            tool_calls=[ToolCall("call_1", "kb_search", {"query": "nhiệt độ mái tôn", "k": 5})],
        ),
        LLMResponse(text=ResearchReport.model_validate(report_data).model_dump_json()),
    )

    report = run_uc02(
        topic="nhiệt độ mái tôn",
        questions=[
            "Mái tôn nóng bao nhiêu độ vào buổi trưa?",
            "Thủ đô của Pháp là gì?",
        ],
        kb=kb,
        llm=llm,
    )

    assert len(report.queries) == 3
    assert len(report.answers) == 2
    assert not report.answers[0].insufficient
    assert report.answers[0].citations[0].quote == "vượt ngưỡng 60 độ C"
    assert report.answers[1].insufficient is True


def test_kb_tools():
    """Kiểm tra trực tiếp kb_search_tool và kb_ingest_tool."""
    chunk = Chunk(
        id="c1:0",
        url="https://tuoitre.vn/test",
        domain="tuoitre.vn",
        title="Test",
        fetched_at="2026-11-05T00:00:00Z",
        trust_tier="B",
        text="Sơn chống nóng mái nhà Skyveil.",
    )
    kb = MemoryKB([chunk])

    # 1. Search tool
    s_tool = kb_search_tool(kb)
    res = s_tool.run({"query": "Skyveil", "k": 5})
    assert res.ok
    assert res.data["count"] == 1
    assert res.data["results"][0]["id"] == "c1:0"

    # 2. Ingest tool với URL giả lập
    page = Page(
        url="https://tuoitre.vn/bai-moi",
        final_url="https://tuoitre.vn/bai-moi",
        title="Bài mới",
        text="Thông tin nạp mới vào kho.",
        fetched_at="2026-11-05T00:00:00Z",
    )
    ing_tool = kb_ingest_tool(kb)
    # Monkeypatch fetch để không gọi mạng
    import agent.tools.kb as tkb
    orig_fetch = tkb.fetch
    tkb.fetch = lambda url, tracer=None: page
    try:
        ires = ing_tool.run({"url": "https://tuoitre.vn/bai-moi"})
        assert ires.ok
        assert ires.data["url"] == "https://tuoitre.vn/bai-moi"
        assert ires.data["chunks"] >= 1
        assert not ires.data["duplicate"]
        # Đảm bảo không trả nội dung trang
        assert "text" not in ires.data
    finally:
        tkb.fetch = orig_fetch


def test_uc02_cli_help():
    cmd = [sys.executable, "-m", "agent.uc02", "--help"]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0
    assert "--topic" in r.stdout
    assert "--question" in r.stdout
