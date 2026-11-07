"""Test run_uc03 và revise_uc03 bằng FakeLLM + MemoryKB: không gọi mạng."""

import json

import pytest

from agent import uc03
from agent.article import Article
from agent.llm import FakeLLM, LLMResponse, ToolCall
from agent.loop import AgentStopped
from agent.trace import Tracer
from agent.uc03 import InputError, revise_uc03, run_uc03
from tests.uc03_fixture import (
    CHUNK,
    CITATION,
    OUTLINE,
    PROMPTS,
    TOPIC,
    article_markdown,
    kb,
    outline,
)

NO_TOOL = LLMResponse(text="xong")
SEARCH = LLMResponse(tool_calls=[ToolCall(id="s1", name="kb_search",
                                          args={"query": "mái mát giảm nhiệt độ bề mặt"})])


def reply(data: dict) -> LLMResponse:
    return LLMResponse(text=json.dumps(data, ensure_ascii=False))


def draft(markdown: str | None = None, citations=(CITATION,), notes=()) -> dict:
    return {
        "markdown": markdown or article_markdown(),
        "citations": [c.model_dump() for c in citations],
        "notes": list(notes),
    }


def run(*responses: LLMResponse, tracer: Tracer | None = None) -> Article:
    tracer = tracer or Tracer("test-uc03", traces_dir=None)
    return run_uc03(TOPIC, PROMPTS, kb=kb(), llm=FakeLLM(*responses), tracer=tracer, pages={})


@pytest.fixture
def tracer(tmp_path) -> Tracer:
    return Tracer("test-uc03", traces_dir=tmp_path)


def events(tracer: Tracer, name: str) -> list[dict]:
    return [e for e in tracer.events if e["event"] == name]


def happy_path() -> list[LLMResponse]:
    """Bước 1: tìm kho, thôi gọi tool, trả dàn ý. Bước 2: không gọi thêm tool, trả bài."""
    return [SEARCH, NO_TOOL, reply(OUTLINE), NO_TOOL, reply(draft())]


def test_runs_outline_then_article(tracer):
    article = run(*happy_path(), tracer=tracer)
    assert article.outline == outline()
    assert article.citations == [CITATION]
    assert [e["name"] for e in events(tracer, "skill_invocation")] == ["geo-outline", "brand-voice"]
    assert events(tracer, "output")[0]["article"]["citations"][0]["chunk_id"] == CHUNK.id


def test_citations_trace_back_to_kb_search(tracer):
    article = run(*happy_path(), tracer=tracer)
    searched = {
        hit["id"]
        for e in events(tracer, "tool_call") if e["name"] == "kb_search" and e["ok"]
        for hit in e["data"]["results"]
    }
    assert article.citations
    assert {c.chunk_id for c in article.citations} <= searched


def test_citation_without_kb_search_is_sent_back_for_repair(tracer):
    # Không gọi kb_search ở bước nào: chunk đúng nhưng chưa "thấy" trong run -> phải sửa.
    no_citation = draft(article_markdown().replace(
        "Mái mát có thể giảm nhiệt độ bề mặt mái tới 28°C vào ngày nắng gắt [1].",
        "Mái sáng màu giúp bề mặt mái bớt nóng rõ rệt vào ngày nắng gắt.",
    ), citations=())
    run(NO_TOOL, reply(OUTLINE), NO_TOOL, reply(draft()), reply(no_citation), tracer=tracer)
    repair = [e for e in events(tracer, "decision") if e.get("action") == "repair"]
    assert len(repair) == 1
    assert "chưa có trong kết quả kb_search" in repair[0]["error"]


def test_outline_repairs_uncovered_prompt(tracer):
    uncovered = {**OUTLINE, "sections": [{**s, "prompt_ids": []} for s in OUTLINE["sections"]]}
    article = run(SEARCH, NO_TOOL, reply(uncovered), reply(OUTLINE), NO_TOOL, reply(draft()),
                  tracer=tracer)
    assert article.outline == outline()
    repair = [e for e in events(tracer, "decision") if e.get("action") == "repair"]
    assert "prompt chưa có H2 hoặc câu FAQ" in repair[0]["error"]


def test_outline_gives_up_after_two_repairs(tracer):
    responses = [SEARCH, NO_TOOL, reply({**OUTLINE, "faq": []})]
    with pytest.raises(AgentStopped, match="sau 2 lần sửa") as stopped:
        run(*responses, tracer=tracer)
    assert stopped.value.reason == "repair_failed"


def test_article_gives_up_after_three_repairs_and_lists_failures(tracer):
    stuffed = draft(article_markdown(extra=" ".join(["sơn chống nóng mái tôn"] * 15)))
    responses = [SEARCH, NO_TOOL, reply(OUTLINE), NO_TOOL, reply(stuffed)]
    with pytest.raises(AgentStopped, match="sau 3 lần sửa") as stopped:
        run(*responses, tracer=tracer)
    assert "mật độ từ khoá chính" in str(stopped.value)
    repairs = [e for e in events(tracer, "decision") if e.get("action") == "repair"]
    assert len(repairs) == 3  # dàn ý qua ngay, bài sửa đủ 3 lần rồi dừng


def test_article_without_numbers_needs_no_citation(tracer):
    qualitative = draft(article_markdown().replace(
        "Mái mát có thể giảm nhiệt độ bề mặt mái tới 28°C vào ngày nắng gắt [1].",
        "Mái sáng màu giúp bề mặt mái bớt nóng rõ rệt vào ngày nắng gắt.",
    ), citations=(), notes=["Kho chưa có số liệu cho mục hiệu quả, viết định tính."])
    article = run(NO_TOOL, reply(OUTLINE), NO_TOOL, reply(qualitative), tracer=tracer)
    assert article.citations == []
    assert article.notes


@pytest.mark.parametrize(("topic", "prompts"), [("", PROMPTS), (TOPIC, []),
                                                 (TOPIC, PROMPTS + PROMPTS)])
def test_rejects_bad_input_before_llm(topic, prompts):
    llm, store = FakeLLM(NO_TOOL), kb()
    with pytest.raises(InputError):
        run_uc03(topic, prompts, kb=store, llm=llm, pages={})
    assert llm.calls == []


def test_brand_kit_without_reader_is_rejected(tmp_path):
    kit = tmp_path / "kit.yaml"
    kit.write_text("name: Hư Cấu\nbrand_voice:\n  tone: vui\n", encoding="utf-8")
    llm, store = FakeLLM(NO_TOOL), kb()
    with pytest.raises(InputError, match="addressing.reader"):
        run_uc03(TOPIC, PROMPTS, brand_kit_path=kit, kb=store, llm=llm, pages={})


def test_prompt_data_is_wrapped_and_skills_sent():
    llm = FakeLLM(*happy_path())
    run_uc03(TOPIC, PROMPTS, kb=kb(), llm=llm, pages={})
    first = llm.calls[0]
    assert "<prompts>" in first["messages"][0].text
    assert "## Final check" in first["system"]  # skill geo-outline nằm trong system prompt
    article_call = llm.calls[3]
    assert "<outline>" in article_call["messages"][0].text
    assert "brand-voice" in article_call["system"]


def test_similarity_is_checked_against_pages_and_traced(tracer):
    run_uc03(TOPIC, PROMPTS, kb=kb(), llm=FakeLLM(*happy_path()), tracer=tracer,
             pages={"https://a.example/x": "nội dung không liên quan"})
    checks = [e for e in events(tracer, "decision") if e.get("action") == "check_similarity"]
    assert checks
    assert checks[-1]["max_ratio"] <= 0.05


def test_compact_threshold_read_from_env(monkeypatch):
    seen = []
    real = uc03.run_agent

    def spy(*args, **kwargs):
        seen.append(kwargs["compact_at_tokens"])
        return real(*args, **kwargs)

    monkeypatch.setenv("COMPACT_AT_TOKENS", "50000")
    monkeypatch.setattr(uc03, "run_agent", spy)
    run_uc03(TOPIC, PROMPTS, kb=kb(), llm=FakeLLM(*happy_path()), pages={})
    assert seen == [50000, 50000]


# ------------------------------------------------------------------- revise


def original() -> Article:
    return Article(outline=outline(), markdown=article_markdown(), citations=[CITATION])


def test_revise_keeps_outline_and_old_citations(tracer):
    edited = draft(article_markdown(extra="Anh/chị nên kiểm tra mái trước mùa nắng."))
    llm = FakeLLM(NO_TOOL, reply(edited))
    revised = revise_uc03(original(), ["Thêm lời khuyên kiểm tra mái"], kb=kb(), llm=llm,
                          tracer=tracer, pages={})
    assert revised.outline == original().outline
    assert revised.citations == [CITATION]  # chunk cũ được coi là đã thấy, không cần tìm lại
    assert "<feedback>" in llm.calls[0]["messages"][0].text
    assert [e["name"] for e in events(tracer, "skill_invocation")] == ["brand-voice"]


def test_revise_uses_same_validator(tracer):
    banned = draft(article_markdown(extra="Đây là giải pháp hàng đầu."))
    article, store, llm = original(), kb(), FakeLLM(NO_TOOL, reply(banned))
    with pytest.raises(AgentStopped) as stopped:
        revise_uc03(article, ["Viết lại"], kb=store, llm=llm, tracer=tracer, pages={})
    assert "từ cấm" in str(stopped.value)


def test_revise_needs_feedback():
    article, store, llm = original(), kb(), FakeLLM(NO_TOOL)
    with pytest.raises(InputError):
        revise_uc03(article, ["  "], kb=store, llm=llm, pages={})


def test_mistyped_citation_url_is_filled_from_chunk(tracer):
    # Lỗi gặp khi chạy live 07/11: model gõ sai URL dài khi chép lại.
    typo = CITATION.model_copy(update={"url": CHUNK.url.replace("cool-roofs", "cool-roof")})
    article = run(*happy_path()[:4], reply(draft(citations=[typo])), tracer=tracer)
    assert article.citations[0].url == CHUNK.url
    assert not [e for e in events(tracer, "decision") if e.get("action") == "repair"]
