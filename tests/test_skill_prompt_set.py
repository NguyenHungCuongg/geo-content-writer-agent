"""Contract của skill prompt-set (Task 5): đủ mục và chép đúng luật UC-01."""

import re

from agent.uc01 import SKILL_PATH


def test_skill_file_has_required_contract_and_constraints():
    text = SKILL_PATH.read_text(encoding="utf-8")

    assert "name: prompt-set" in text
    assert "description:" in text
    for section in [
        "Khi nào dùng", "Đầu vào", "Đầu ra", "Các bước", "Ràng buộc",
        "Ví dụ đúng", "Ví dụ sai", "Final check",
    ]:
        assert f"## {section}" in text
    for keyword in ["30", "15%", "10%", "navigational", "mentions_brand", "dedupe_prompts"]:
        assert keyword in text

    steps = text.split("## Các bước")[1].split("##")[0]
    assert 5 <= len(re.findall(r"^\d+\.", steps, re.MULTILINE)) <= 8
    assert "```" not in text  # skill không chứa script
