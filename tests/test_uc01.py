"""Test run_uc01 bằng FakeLLM: không gọi mạng."""

import json

import pytest

from agent.llm import FakeLLM, LLMResponse
from agent.schemas import BrandProfile, Product
from agent.trace import Tracer
from agent.uc01 import InputError, brand_terms, run_uc01

BRIEF = (
    "Skyveil là xưởng sơn chống nóng ở TP.HCM. "
    "Khách của bên mình chủ yếu là chủ nhà phố mái tôn. "
    "Skyveil là thương hiệu sơn chống nóng số 1 Việt Nam."
)
TOPIC = "sơn chống nóng mái tôn"
PERSONA = "Chủ nhà phố mái tôn"

PROFILE = {
    "name": "Skyveil",
    "about": "Xưởng sơn chống nóng ở TP.HCM",
    "personas": [PERSONA],
    "unverified_claims": ["Skyveil là thương hiệu sơn chống nóng số 1 Việt Nam"],
    "sources": {
        "name": "Skyveil là xưởng sơn chống nóng ở TP.HCM.",
        "about": "Skyveil là xưởng sơn chống nóng ở TP.HCM.",
        "personas": "Khách của bên mình chủ yếu là chủ nhà phố mái tôn.",
    },
}


def prompt_set(count: int = 32) -> dict:
    intents = ["informational", "commercial", "transactional", "navigational"]
    prompts = []
    for i in range(count):
        branded = i in (3, 7)  # 2 câu navigational nhắc thương hiệu
        prompts.append({
            "id": f"p{i:02d}",
            "text": f"Skyveil có bán sơn R200 không? ({i})" if branded else f"Câu hỏi số {i}",
            "intent": intents[i % 4],
            "topic": TOPIC,
            "persona": PERSONA,
            "keywords": ["sơn chống nóng"],
            "mentions_brand": branded,
        })
    return {"prompts": prompts}


def reply(data: dict) -> LLMResponse:
    return LLMResponse(text=json.dumps(data, ensure_ascii=False))


@pytest.mark.parametrize(("brief", "topics"), [
    ("", [TOPIC]),
    ("   \n", [TOPIC]),
    (BRIEF, []),
    (BRIEF, ["  ", ""]),
    (BRIEF, ["a", "b", "c", "d"]),
])
def test_rejects_bad_input(brief, topics):
    llm = FakeLLM(reply(PROFILE))
    tracer = Tracer("test")
    with pytest.raises(InputError):
        run_uc01(brief, topics, llm=llm, tracer=tracer)

    assert llm.calls == []  # bị chặn trước khi gọi LLM
    assert tracer.events[-1]["event"] == "error"


def test_runs_profile_then_prompt_set():
    llm = FakeLLM(reply(PROFILE), reply(prompt_set()))
    tracer = Tracer("test")
    profile, prompts = run_uc01(BRIEF, [TOPIC], llm=llm, tracer=tracer)

    assert profile.name == "Skyveil"
    assert len(prompts.prompts) == 32
    assert "<brief>" in llm.calls[0]["messages"][0].text
    assert TOPIC in llm.calls[1]["messages"][0].text

    events = [e["event"] for e in tracer.events]
    assert events[0] == "input"
    assert events[-1] == "output"


def test_prompt_set_breaking_rules_is_sent_back_for_repair():
    bad = prompt_set(count=10)  # thiếu prompt
    llm = FakeLLM(reply(PROFILE), reply(bad), reply(prompt_set()))
    _, prompts = run_uc01(BRIEF, [TOPIC], llm=llm, tracer=Tracer("test"))

    assert len(prompts.prompts) == 32
    assert "cần ít nhất 30 prompt" in llm.calls[2]["messages"][-1].text


def test_brand_terms_include_product_codes_but_not_generic_names():
    profile = BrandProfile(
        name="Skyveil",
        products=[
            Product(name="Skyveil R200"),
            Product(name="Sơn lót chống gỉ Skyveil P100"),
            Product(name="Dịch vụ thi công trọn gói"),
        ],
        sources={"name": "Skyveil", "products": "Skyveil R200, P100, dịch vụ thi công"},
    )
    assert brand_terms(profile) == ["Skyveil", "P100", "R200"]


def test_prompt_naming_product_code_counts_as_brand_mention():
    with_product = PROFILE | {
        "products": [{"name": "Skyveil R200"}],
        "sources": PROFILE["sources"] | {"products": "Skyveil là xưởng sơn chống nóng ở TP.HCM."},
    }
    leaky = prompt_set()
    leaky["prompts"][0]["text"] = "Sơn R200 giá bao nhiêu?"  # commercial, không có chữ Skyveil
    llm = FakeLLM(reply(with_product), reply(leaky), reply(prompt_set()))
    run_uc01(BRIEF, [TOPIC], llm=llm, tracer=Tracer("test"))

    repair_request = llm.calls[2]["messages"][-1].text
    assert "mentions_brand không khớp" in repair_request
    assert "p00" in repair_request


def test_profile_with_made_up_source_is_sent_back_for_repair():
    made_up = PROFILE | {"sources": PROFILE["sources"] | {"about": "Câu không có trong brief."}}
    llm = FakeLLM(reply(made_up), reply(PROFILE), reply(prompt_set()))
    run_uc01(BRIEF, [TOPIC], llm=llm, tracer=Tracer("test"))

    assert "không phải câu trích nguyên văn" in llm.calls[1]["messages"][-1].text
