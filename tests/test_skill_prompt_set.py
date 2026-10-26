import json
from pathlib import Path

from agent import uc01
from agent.llm import FakeLLM, LLMResponse
from agent.trace import Tracer

BRIEF = (
    "Skyveil là xưởng sơn chống nóng ở TP.HCM. "
    "Khách của bên mình chủ yếu là chủ nhà phố mái tôn. "
    "Skyveil là thương hiệu sơn chống nóng số 1 Việt Nam."
)
TOPIC = "sơn chống nóng mái tôn"


def prompt_set_payload() -> dict:
    intents = ["informational", "commercial", "transactional", "navigational"]
    prompts = []
    for i in range(32):
        branded = i in (3, 7)
        prompts.append(
            {
                "id": f"p{i:02d}",
                "text": f"Skyveil có bán sơn R200 không? ({i})" if branded else f"Câu hỏi số {i}",
                "intent": intents[i % 4],
                "topic": TOPIC,
                "persona": "Chủ nhà phố mái tôn",
                "keywords": ["sơn chống nóng"],
                "mentions_brand": branded,
            }
        )
    return {"prompts": prompts}


def test_skill_file_has_required_contract_and_constraints():
    skill_path = Path("skills/prompt-set/SKILL.md")
    text = skill_path.read_text(encoding="utf-8")

    assert "name: prompt-set" in text
    assert "description:" in text
    assert "Khi nào dùng" in text or "khi nào dùng" in text.lower()
    required_items = [
        "Đầu vào",
        "Đầu ra",
        "Các bước",
        "Ràng buộc",
        "Ví dụ đúng",
        "Ví dụ sai",
        "Final check",
    ]
    for required in required_items:
        assert required in text
    for keyword in ["30", "15%", "10%", "navigational", "mentions_brand", "brief"]:
        assert keyword in text


def test_run_uc01_records_skill_invocation():
    profile = {
        "name": "Skyveil",
        "about": "Xưởng sơn chống nóng ở TP.HCM",
        "personas": ["Chủ nhà phố mái tôn"],
        "unverified_claims": ["Skyveil là thương hiệu sơn chống nóng số 1 Việt Nam"],
        "sources": {
            "name": "Skyveil là xưởng sơn chống nóng ở TP.HCM.",
            "about": "Skyveil là xưởng sơn chống nóng ở TP.HCM.",
            "personas": "Khách của bên mình chủ yếu là chủ nhà phố mái tôn.",
        },
    }
    llm = FakeLLM(
        LLMResponse(text="xong"),
        LLMResponse(text=json.dumps(profile, ensure_ascii=False)),
        LLMResponse(text="xong"),
        LLMResponse(text=json.dumps(prompt_set_payload(), ensure_ascii=False)),
    )
    tracer = Tracer("test-skill")

    uc01.run_uc01(BRIEF, [TOPIC], llm=llm, tracer=tracer)

    assert any(
        e["event"] == "skill_invocation" and e.get("name") == "prompt-set"
        for e in tracer.events
    )
