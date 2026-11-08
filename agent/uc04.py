"""UC-04: Fact-checker agent (Phase 2, Task 6).

Bao gồm:
- run_uc04: kiểm tra tính xác thực các claim trong Article qua 2 bước (tách claim, tìm bằng chứng)
- fact_check_loop: phối hợp giữa Writer (revise_uc03) và Fact-checker (run_uc04), tối đa 2 vòng
"""

from __future__ import annotations

from typing import Any

from agent.article import Article
from agent.claims import ClaimReport
from agent.kb import KB
from agent.llm import LLM
from agent.trace import Tracer


def run_uc04(
    article: Article,
    *,
    kb: KB | None = None,
    llm: LLM | None = None,
    tracer: Tracer | None = None,
    client: Any = None,
) -> ClaimReport:
    """Kiểm tra fact-check cho một bài viết.

    Chỉ dùng các tool: kb_search, web_search, fetch_url.
    """
    raise NotImplementedError("run_uc04 chưa được cài đặt (Stub Phase 2)")


def fact_check_loop(
    article: Article,
    *,
    kb: KB | None = None,
    llm: LLM | None = None,
    tracer: Tracer | None = None,
    max_rounds: int = 2,
) -> tuple[Article, ClaimReport]:
    """Vòng lặp sửa bài giữa Writer và Fact-checker, tối đa max_rounds (mặc định 2)."""
    raise NotImplementedError("fact_check_loop chưa được cài đặt (Stub Phase 2)")
