"""Khung chung cho mọi tool của agent.

Tool cụ thể (load_brand_kit, dedupe_prompts...) nằm ở các module con trong thư mục này (Task 4).
"""

import concurrent.futures
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx
from google.genai import errors
from pydantic import BaseModel, ValidationError

# Lỗi tạm thời đáng thử lại: 429 vượt rate limit, 500/504 lỗi tạm phía server, 503 model quá tải.
# agent/llm.py dùng lại hằng này.
RETRYABLE_CODES = {429, 500, 503, 504}


def is_transient(e: Exception) -> bool:
    """Lỗi mạng hoặc lỗi tạm của API thì đáng thử lại. Lỗi dữ liệu, cấu hình, quyền, timeout thì
    không: thử lại vẫn sai, hoặc lại chờ thêm `timeout_s`."""
    if isinstance(e, errors.APIError):
        return e.code in RETRYABLE_CODES
    return isinstance(e, (ConnectionError, httpx.TransportError))


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
    backoff_s: float = 1.0       # chờ backoff_s, 2*backoff_s... giữa các lần thử lại

    def run(self, args: dict) -> ToolResult:
        """Kiểm đối số rồi gọi tool; mọi lỗi được gói vào ToolResult để loop không bị crash.

        Lỗi tạm thời (`is_transient`) được thử lại tối đa `max_retries` lần.
        """
        try:
            parsed = self.args_model.model_validate(args)
        except ValidationError as e:
            return ToolResult(ok=False, error=f"đối số sai: {e}")

        error = ""
        for attempt in range(self.max_retries + 1):
            if attempt:
                time.sleep(self.backoff_s * 2 ** (attempt - 1))
            try:
                return ToolResult(ok=True, data=self.call(parsed))
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
                if not is_transient(e):
                    break
        return ToolResult(ok=False, error=error)

    def call(self, parsed: BaseModel) -> dict:
        """Chạy `fn` ở luồng riêng để trả lỗi đúng hạn `timeout_s`."""
        # ponytail: Python không dừng được luồng đang chạy, nên luồng quá hạn vẫn chạy nền tới
        # khi fn tự xong, và Python chờ nó khi thoát. Tool gọi mạng phải tự đặt timeout HTTP
        # (xem dedupe.py).
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(self.fn, parsed)
            done, _ = concurrent.futures.wait([future], timeout=self.timeout_s)
            if not done:
                raise TimeoutError(f"tool chạy quá {self.timeout_s}s")
            return future.result()
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
