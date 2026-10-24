"""Khung chung cho mọi tool của agent.

Tool cụ thể (load_brand_kit, dedupe_prompts...) nằm ở các module con trong thư mục này (Task 4).
"""

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError


class ToolResult(BaseModel):
    """Kết quả trả về cho loop. Lỗi cũng là một kết quả (ok=False), không phải exception."""

    ok: bool
    data: dict | None = None
    error: str | None = None


@dataclass(frozen=True)
class Tool:
    name: str
    description: str             # LLM đọc mô tả này để chọn tool
    args_model: type[BaseModel]  # schema đối số, gửi kèm cho LLM
    fn: Callable[[BaseModel], dict]
    timeout_s: float = 15

    def run(self, args: dict) -> ToolResult:
        """Kiểm đối số rồi gọi tool; mọi lỗi được gói vào ToolResult để loop không bị crash.

        Timeout và retry do Task 4 bổ sung.
        """
        try:
            parsed = self.args_model.model_validate(args)
        except ValidationError as e:
            return ToolResult(ok=False, error=f"đối số sai: {e}")

        try:
            return ToolResult(ok=True, data=self.fn(parsed))
        except Exception as e:
            return ToolResult(ok=False, error=f"{type(e).__name__}: {e}")
