"""Test các luật của BrandProfile mà test_uc01 chưa phủ."""

import pytest
from pydantic import ValidationError

from agent.schemas import BrandProfile

BRIEF = "Skyveil là xưởng sơn chống nóng ở TP.HCM."


def profile(sources: dict) -> dict:
    return {"name": "Skyveil", "about": "Xưởng sơn chống nóng", "sources": sources}


def test_accepts_profile_traced_to_brief():
    data = profile({"name": BRIEF, "about": BRIEF})
    assert BrandProfile.model_validate(data, context={"brief": BRIEF}).name == "Skyveil"


@pytest.mark.parametrize("quote", ["", "   "])
def test_empty_quote_does_not_count_as_source(quote):
    with pytest.raises(ValidationError, match=r"thiếu câu trích.*about"):
        BrandProfile.model_validate(profile({"name": BRIEF, "about": quote}))


def test_rejects_quote_not_in_brief():
    data = profile({"name": BRIEF, "about": "Câu bịa."})
    with pytest.raises(ValidationError, match="không phải câu trích nguyên văn"):
        BrandProfile.model_validate(data, context={"brief": BRIEF})


def test_missing_info_needs_clarifying_question():
    data = profile({"name": BRIEF, "about": BRIEF}) | {"missing_info": ["giá"]}
    with pytest.raises(ValidationError, match="clarifying_questions"):
        BrandProfile.model_validate(data)


KIT = {"name": "Skyveil", "mission": "Giúp nhà mái tôn ở miền Nam bớt nóng.", "founded": 2019}


def kit_observation(kit: dict = KIT) -> dict:
    return {"tool": "load_brand_kit", "data": kit}


def test_accepts_quote_from_brand_kit_of_the_brief_brand():
    data = profile({"name": BRIEF, "about": "bớt nóng", "mission": "Giúp nhà mái tôn"})
    context = {"brief": BRIEF, "observations": [kit_observation()]}
    assert BrandProfile.model_validate(data, context=context).name == "Skyveil"


def test_rejects_quote_from_brand_kit_of_another_brand():
    other_brief = "Đồi Mây là xưởng rang cà phê ở Bảo Lộc."
    data = profile({"name": other_brief, "about": "Giúp nhà mái tôn ở miền Nam bớt nóng."})
    context = {"brief": other_brief, "observations": [kit_observation()]}
    with pytest.raises(ValidationError, match=r"không phải câu trích nguyên văn.*about"):
        BrandProfile.model_validate(data, context=context)


def test_only_brand_kit_results_count_as_quotable():
    data = profile({"name": BRIEF, "about": "Giúp nhà mái tôn"})
    context = {"brief": BRIEF, "observations": [{"tool": "dedupe_prompts", "data": KIT}]}
    with pytest.raises(ValidationError, match="không phải câu trích nguyên văn"):
        BrandProfile.model_validate(data, context=context)
