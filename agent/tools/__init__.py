"""Khung chung cho mọi tool của agent.

Tool cụ thể (load_brand_kit, dedupe_prompts...) nằm ở các module con trong thư mục này (Task 4).
"""

import concurrent.futures
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

# Lỗi logic/dữ liệu không thử lại vì kết quả không đổi
NON_RETRYABLE_EXCEPTIONS = (ValueError, FileNotFoundError)


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
    timeout_s: float = 15.0
    max_retries: int = 2

    def run(self, args: dict) -> ToolResult:
        """Kiểm đối số rồi gọi tool; mọi lỗi được gói vào ToolResult để loop không bị crash.

        Timeout và retry tối đa max_retries lần với lỗi tạm thời.
        """
        try:
            parsed = self.args_model.model_validate(args)
        except ValidationError as e:
            return ToolResult(ok=False, error=f"đối số sai: {e}")

        last_error = ""
        for _ in range(self.max_retries + 1):
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            try:
                future = executor.submit(self.fn, parsed)
                data = future.result(timeout=self.timeout_s)
                return ToolResult(ok=True, data=data)
            except (concurrent.futures.TimeoutError, TimeoutError):
                last_error = f"TimeoutError: hàm chạy quá {self.timeout_s}s"
            except NON_RETRYABLE_EXCEPTIONS as e:
                return ToolResult(ok=False, error=f"{type(e).__name__}: {e}")
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

        return ToolResult(ok=False, error=last_error)
