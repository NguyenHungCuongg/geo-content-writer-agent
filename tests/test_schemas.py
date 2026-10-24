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
