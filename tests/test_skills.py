"""Contract của mọi skill trong skills/*/SKILL.md (Task 5, đặc tả mục 4.2)."""

import re
from pathlib import Path

import pytest
import yaml

SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"
SKILL_FILES = sorted(SKILLS_DIR.glob("*/SKILL.md"))
REQUIRED_SECTIONS = [
    "Khi nào dùng", "Đầu vào", "Đầu ra", "Các bước", "Ràng buộc",
    "Ví dụ đúng", "Ví dụ sai", "Final check",
]


def frontmatter(text: str) -> dict:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "thiếu frontmatter YAML ở đầu file"
    return yaml.safe_load(match.group(1)) or {}


def test_uc03_skills_exist():
    names = {path.parent.name for path in SKILL_FILES}
    assert {"prompt-set", "brand-voice", "geo-outline"} <= names


@pytest.mark.parametrize("path", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skill_has_full_contract(path: Path):
    text = path.read_text(encoding="utf-8")
    meta = frontmatter(text)
    assert meta.get("name") == path.parent.name
    assert str(meta.get("description", "")).strip()
    for section in REQUIRED_SECTIONS:
        assert re.search(rf"^## {section}\s*$", text, re.MULTILINE), f"thiếu mục {section}"
    assert "```" not in text, "skill không được chứa khối code"
