"""Test schema lịch nội dung 4 tuần (ContentCalendar) và hàm plan_calendar của UC-09."""

import json

import pytest
from pydantic import ValidationError

from agent.llm import FakeLLM, LLMResponse
from agent.schemas import Prompt, PromptSet
from agent.trace import Tracer
from agent.uc09 import (
    ApprovalDecision,
    CalendarItem,
    ContentCalendar,
    check_calendar,
    plan_calendar,
)


def make_prompts(n: int = 32) -> PromptSet:
    intents = ("informational", "navigational", "commercial", "transactional")
    prompts = [
        Prompt(
            id=f"p{i:02d}",
            text=f"Câu hỏi số {i} về giải pháp chống nóng mái nhà?",
            intent=intents[i % 4],
            topic="sơn chống nóng mái tôn",
            persona="Chủ nhà",
            keywords=[f"từ khoá {i}"],
            mentions_brand=False,
        )
        for i in range(1, n + 1)
    ]
    return PromptSet.model_construct(prompts=prompts)


def valid_items(count: int = 8) -> list[dict]:
    items = []
    for i in range(1, count + 1):
        other1 = f"art-{(i % count) + 1:02d}"
        other2 = f"art-{((i + 1) % count) + 1:02d}"
        items.append({
            "id": f"art-{i:02d}",
            "week": ((i - 1) % 4) + 1,
            "title": f"Bài viết chuyên sâu số {i} về chống nóng mái tôn",
            "primary_keyword": f"sơn chống nóng chuyên đề {i}",
            "prompt_ids": [f"p{i:02d}", f"p{i + 8:02d}"],
            "internal_links": [other1, other2],
            "status": "todo",
        })
    return items


def test_valid_calendar_passes():
    cal = ContentCalendar.model_validate(
        {"items": valid_items(8)},
        context={"prompt_ids": {f"p{i:02d}" for i in range(1, 33)}},
    )
    assert len(cal.items) == 8
    assert check_calendar(cal.items) == []


def test_calendar_rejects_cannibalization():
    items = valid_items(8)
    # Bài 2 trùng primary_keyword với bài 1 (khác hoa thường và khoảng trắng)
    items[1]["primary_keyword"] = "  SƠN chống nóng   chuyên đề 1 "
    with pytest.raises(ValidationError, match="primary_keyword|trùng"):
        ContentCalendar.model_validate({"items": items})


def test_calendar_requires_two_internal_links():
    # Chỉ có 1 internal link
    items_one = valid_items(8)
    items_one[0]["internal_links"] = ["art-02"]
    with pytest.raises(ValidationError, match="internal_links"):
        ContentCalendar.model_validate({"items": items_one})

    # Tự trỏ tới chính mình
    items_self = valid_items(8)
    items_self[0]["internal_links"] = ["art-01", "art-02"]
    with pytest.raises(ValidationError, match="internal_links"):
        ContentCalendar.model_validate({"items": items_self})

    # Trỏ tới ID không có trong lịch
    items_unknown = valid_items(8)
    items_unknown[0]["internal_links"] = ["art-02", "art-99"]
    with pytest.raises(ValidationError, match="internal_links"):
        ContentCalendar.model_validate({"items": items_unknown})


def test_calendar_requires_eight_items_and_four_weeks():
    # Dưới 8 bài
    with pytest.raises(ValidationError, match="8 bài"):
        ContentCalendar.model_validate({"items": valid_items(7)})

    # Thiếu tuần 4
    items_no_week4 = valid_items(8)
    for item in items_no_week4:
        if item["week"] == 4:
            item["week"] = 1
    with pytest.raises(ValidationError, match="4 tuần|tuần"):
        ContentCalendar.model_validate({"items": items_no_week4})


def test_calendar_validates_prompt_ids_from_context():
    items = valid_items(8)
    items[0]["prompt_ids"] = ["p01", "p999"]
    with pytest.raises(ValidationError, match="prompt_ids|p999"):
        ContentCalendar.model_validate(
            {"items": items},
            context={"prompt_ids": {f"p{i:02d}" for i in range(1, 33)}},
        )


def test_plan_calendar_repairs_and_returns_valid_calendar():
    ps = make_prompts(32)
    bad_items = valid_items(8)
    bad_items[1]["primary_keyword"] = bad_items[0]["primary_keyword"]  # cannibalization

    good_items = valid_items(8)
    llm = FakeLLM(
        LLMResponse(text=json.dumps({"items": bad_items}, ensure_ascii=False)),
        LLMResponse(text=json.dumps({"items": good_items}, ensure_ascii=False)),
    )
    tracer = Tracer("test-plan")
    cal = plan_calendar(ps, llm=llm, tracer=tracer)

    assert len(cal.items) == 8
    assert all(isinstance(it, CalendarItem) for it in cal.items)
    assert any(e.get("action") == "repair" for e in tracer.events)


def test_approval_decision_schema():
    d = ApprovalDecision(decision="approve", reviewer="admin")
    assert d.decision == "approve"
    assert d.reason == ""
    assert d.reviewer == "admin"


def test_uc09_cli_start_approve_and_resume(monkeypatch, tmp_path, capsys):
    import agent.graph as graph_mod
    from agent.kb import BRAND_KIT_PATH, MemoryKB, ingest_brand_kit, ingest_miniweb
    from agent.uc09 import main

    kb = MemoryKB()
    ingest_miniweb(kb)
    ingest_brand_kit(kb, BRAND_KIT_PATH)

    monkeypatch.setenv("UC09_FORCE_FILE_CHECKPOINTER", "1")
    monkeypatch.setattr(graph_mod, "TRACES_DIR", tmp_path)
    monkeypatch.setattr("agent.trace.TRACES_DIR", tmp_path)
    monkeypatch.setattr(graph_mod, "_default_kb", lambda: kb)
    monkeypatch.setattr(graph_mod, "GeminiLLM", lambda: graph_mod.ScriptedWorkflowLLM(kb))

    brief_file = tmp_path / "brief.md"
    brief_file.write_text("Skyveil chuyên sơn chống nóng mái tôn.", encoding="utf-8")
    run_id = "c9" * 16

    # 1. start (dừng chờ duyệt ở art-01)
    rc = main([
        "start",
        "--brief",
        str(brief_file),
        "--topic",
        "sơn chống nóng mái tôn",
        "--run-id",
        run_id,
    ])
    assert rc == 0
    out_start = json.loads(capsys.readouterr().out)
    assert out_start["calendar"]["items"][0]["status"] == "review"

    # 2. approve art-01
    rc = main([
        "approve",
        run_id,
        "--decision",
        "approve",
        "--reason",
        "Đạt chuẩn",
        "--reviewer",
        "admin",
    ])
    assert rc == 0
    out_app = json.loads(capsys.readouterr().out)
    assert out_app["calendar"]["items"][0]["status"] == "approved"
    assert out_app["calendar"]["items"][1]["status"] == "review"

    # 3. resume với --auto-approve để hoàn tất các bài còn lại
    rc = main(["resume", run_id, "--auto-approve"])
    assert rc == 0
    out_res = json.loads(capsys.readouterr().out)
    assert all(it["status"] == "approved" for it in out_res["calendar"]["items"])

