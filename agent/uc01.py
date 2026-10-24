"""UC-01: phân tích brief thương hiệu thành BrandProfile, rồi sinh PromptSet."""

from agent.schemas import BrandProfile, PromptSet
from agent.trace import Tracer


def run_uc01(
    brief: str,
    topics: list[str],
    *,
    llm=None,
    tracer: Tracer | None = None,
) -> tuple[BrandProfile, PromptSet]:
    """Chạy UC-01 trên một brief và 1-3 chủ đề.

    `llm`: để trống thì dùng Gemini; test truyền LLM giả để không gọi mạng.
    `tracer`: để trống thì tạo Tracer mới với run_id ngẫu nhiên.
    """
    raise NotImplementedError("run_uc01 chưa cài đặt (Task 3, bước 5)")
