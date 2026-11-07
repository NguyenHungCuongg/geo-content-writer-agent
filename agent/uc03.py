"""UC-03: lập dàn ý GEO rồi viết bài theo giọng thương hiệu, mọi số liệu có trích dẫn.

Bước 1 ra `OutlinePlan` (tối đa 2 lần sửa), bước 2 ra `Article` (tối đa 3 vòng sửa); quá giới hạn
thì `AgentStopped("repair_failed")` liệt kê mục chưa đạt. `revise_uc03` dùng cùng validator, cho
Task 6 (fact-checker) và Task 7 (người duyệt từ chối) gọi.

Stub ngày đầu (Task 5): chữ ký đã chốt, thân hàm chưa cài.
"""

from pathlib import Path

from agent.article import Article
from agent.kb import BRAND_KIT_PATH, KB
from agent.llm import LLM
from agent.schemas import Prompt
from agent.trace import Tracer


def run_uc03(
    topic: str,
    prompts: list[Prompt],
    *,
    brand_kit_path: Path = BRAND_KIT_PATH,
    kb: KB | None = None,
    llm: LLM | None = None,
    tracer: Tracer | None = None,
) -> Article:
    """Viết một bài cho `topic`, trả lời các `prompts` mục tiêu (lấy từ PromptSet của UC-01).

    `compact_at_tokens` đọc từ biến môi trường COMPACT_AT_TOKENS.
    """
    raise NotImplementedError("Task 5: run_uc03 chưa cài")


def revise_uc03(
    article: Article,
    feedback: list[str],
    *,
    kb: KB | None = None,
    llm: LLM | None = None,
    tracer: Tracer | None = None,
) -> Article:
    """Sửa `article` theo `feedback` (mỗi dòng một chỗ cần sửa), qua cùng validator với run_uc03."""
    raise NotImplementedError("Task 5: revise_uc03 chưa cài")
