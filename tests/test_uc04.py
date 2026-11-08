"""Test run_uc04 và fact_check_loop bằng FakeLLM + MemoryKB: không gọi mạng."""

import json

from agent.article import Article
from agent.claims import blocking_claims
from agent.llm import FakeLLM, LLMResponse, ToolCall
from agent.trace import Tracer
from agent.uc04 import fact_check_loop, run_uc04
from tests.uc03_fixture import CHUNK, CITATION, article_markdown, kb, outline

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def reply(data: dict) -> LLMResponse:
    return LLMResponse(text=json.dumps(data, ensure_ascii=False))


NO_TOOL = LLMResponse(text="xong")

# Bài mẫu có 1 câu số liệu: "giảm nhiệt độ bề mặt mái tới 28°C"
SAMPLE_ARTICLE = Article(
    outline=outline(),
    markdown=article_markdown(),
    citations=[CITATION],
)


def extract_claims() -> dict:
    """Kết quả bước 1 (tách claim) cho bài mẫu."""
    return {
        "claims": [
            {
                "claim": "Mái mát có thể giảm nhiệt độ bề mặt mái tới 28°C",
                "heading": "Sơn chống nóng mái tôn có hiệu quả không?",
                "paragraph": 0,
                "has_number": True,
            },
        ]
    }


def evidence_supported() -> dict:
    """Bước 2: evidence ủng hộ từ tier A."""
    return {
        "evidence": [
            {
                "claim_index": 0,
                "chunk_id": CHUNK.id,
                "url": CHUNK.url,
                "quote": "giảm nhiệt độ bề mặt mái tới 28°C",
                "trust_tier": "A",
                "stance": "supports",
            }
        ]
    }


def evidence_contradicted() -> dict:
    """Bước 2: evidence phản bác từ tier A."""
    return {
        "evidence": [
            {
                "claim_index": 0,
                "chunk_id": CHUNK.id,
                "url": CHUNK.url,
                "quote": "giảm nhiệt độ bề mặt mái tới 28°C",
                "trust_tier": "A",
                "stance": "contradicts",
            }
        ]
    }


def uc04_responses_supported() -> list[LLMResponse]:
    """Responses cho run_uc04 khi claim được supported.

    Luồng LLM calls:
    1. Bước 1 (extract): tools=() → act skipped → finalize (1 call) → extract_claims
    2. Bước 2 (evidence): tools=[kb_search,...] →
       act iteration 1 (kb_search call) → act iteration 2 (NO_TOOL, stop) →
       finalize (1 call) → evidence
    """
    return [
        reply(extract_claims()),        # finalize bước 1
        LLMResponse(                    # act bước 2: gọi kb_search
            tool_calls=[ToolCall(id="s1", name="kb_search",
                                 args={"query": "giảm nhiệt độ mái"})]
        ),
        NO_TOOL,                        # act bước 2: thôi gọi tool
        reply(evidence_supported()),    # finalize bước 2
    ]


def uc04_responses_contradicted() -> list[LLMResponse]:
    """Responses cho run_uc04 khi claim bị contradicted."""
    return [
        reply(extract_claims()),
        LLMResponse(
            tool_calls=[ToolCall(id="s1", name="kb_search",
                                 args={"query": "giảm nhiệt độ mái"})]
        ),
        NO_TOOL,
        reply(evidence_contradicted()),
    ]


def revise_responses() -> list[LLMResponse]:
    """Responses cho revise_uc03 (Writer sửa bài).

    Luồng: skill_invocation → write_article → run_agent:
      act: kb_search → NO_TOOL → finalize: draft
    """
    return [
        LLMResponse(  # act: gọi kb_search
            tool_calls=[ToolCall(id="s1", name="kb_search",
                                 args={"query": "mái mát giảm nhiệt"})]
        ),
        NO_TOOL,  # act: thôi gọi tool
        reply({   # finalize: trả ArticleDraft
            "markdown": article_markdown(),
            "citations": [CITATION.model_dump()],
            "notes": [],
        }),
    ]


# ---------------------------------------------------------------------------
# test_fact_checker_has_no_write_tools (DoD tiêu chí 5)
# ---------------------------------------------------------------------------


def test_fact_checker_has_no_write_tools():
    """Tên tool của run_uc04 ⊆ {kb_search, web_search, fetch_url}."""
    llm = FakeLLM(*uc04_responses_supported())
    tracer = Tracer("test-tools", traces_dir=None)
    run_uc04(SAMPLE_ARTICLE, kb=kb(), llm=llm, tracer=tracer)

    tool_names = {
        e["name"]
        for e in tracer.events
        if e.get("event") == "tool_call"
    }
    allowed = {"kb_search", "web_search", "fetch_url"}
    assert tool_names <= allowed, f"Tool không hợp lệ: {tool_names - allowed}"


# ---------------------------------------------------------------------------
# test_loop_stops_after_two_rounds (DoD)
# ---------------------------------------------------------------------------


def test_loop_stops_after_two_rounds(tmp_path):
    """FakeLLM giữ claim contradicted mãi → dừng sau 2 vòng, blocking khác rỗng."""
    llm = FakeLLM(
        # --- Vòng 1: run_uc04 (contradicted) ---
        *uc04_responses_contradicted(),
        # --- revise_uc03 (Writer sửa bài) ---
        *revise_responses(),
        # --- Vòng 2: run_uc04 (vẫn contradicted) ---
        *uc04_responses_contradicted(),
    )

    tracer = Tracer("test-loop", traces_dir=tmp_path)
    final_article, final_report = fact_check_loop(
        SAMPLE_ARTICLE, kb=kb(), llm=llm, tracer=tracer, max_rounds=2
    )

    assert final_report.round == 2
    blocked = blocking_claims(final_report)
    assert len(blocked) > 0, "Phải còn blocking claims vì claim vẫn contradicted"

    # Kiểm tra trace có 2 fact_check_round
    rounds = [
        e for e in tracer.events
        if e.get("event") == "decision" and e.get("action") == "fact_check_round"
    ]
    assert len(rounds) == 2


# ---------------------------------------------------------------------------
# test_blocking_empty_when_fixable (DoD tiêu chí 4)
# ---------------------------------------------------------------------------


def test_blocking_empty_when_fixable(tmp_path):
    """Claim sửa được → blocking_claims rỗng sau vòng cuối."""
    llm = FakeLLM(*uc04_responses_supported())

    tracer = Tracer("test-fixable", traces_dir=tmp_path)
    final_article, final_report = fact_check_loop(
        SAMPLE_ARTICLE, kb=kb(), llm=llm, tracer=tracer, max_rounds=2
    )

    blocked = blocking_claims(final_report)
    assert len(blocked) == 0, "Claim supported → không có blocking"
