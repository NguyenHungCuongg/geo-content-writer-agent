"""Công cụ thao tác với kho tri thức RAG (Phase 2, Task 4 - UC-02b).

Bao gồm:
- kb_search_tool: tìm kiếm các đoạn chunk liên quan trong kho tri thức
- kb_ingest_tool: tải trang từ URL trong allowlist và nạp vào kho tri thức
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agent.kb import KB
from agent.tools import Tool
from agent.tools.web import fetch


class KBSearchArgs(BaseModel):
    query: str = Field(..., description="Từ khoá hoặc câu hỏi cần tìm trong kho tri thức")
    k: int = Field(default=5, ge=1, le=10, description="Số kết quả tối đa (1-10)")


def kb_search_tool(kb: KB) -> Tool:
    def kb_search_fn(args: KBSearchArgs) -> dict[str, Any]:
        hits = kb.search(args.query, k=args.k)
        return {
            "query": args.query,
            "count": len(hits),
            "results": [
                {
                    "id": hit.id,
                    "url": hit.url,
                    "domain": hit.domain,
                    "title": hit.title,
                    "trust_tier": hit.trust_tier,
                    "text": hit.text,
                    "score": hit.score,
                }
                for hit in hits
            ],
        }

    return Tool(
        name="kb_search",
        description=(
            "Tìm kiếm thông tin trong kho tri thức RAG. "
            "Trả về các đoạn văn bản (chunks) liên quan kèm ID và URL để trích dẫn."
        ),
        args_model=KBSearchArgs,
        fn=kb_search_fn,
        timeout_s=15.0,
        max_retries=1,
    )


class KBIngestArgs(BaseModel):
    url: str = Field(..., description="URL trang web thuộc allowlist cần nạp vào kho")


def kb_ingest_tool(kb: KB, tracer: Any = None) -> Tool:
    def kb_ingest_fn(args: KBIngestArgs) -> dict[str, Any]:
        page = fetch(args.url, tracer=tracer)
        result = kb.ingest(page, tracer=tracer)
        return {
            "url": result.url,
            "chunks": result.chunks,
            "suspicious": result.suspicious,
            "duplicate": result.duplicate,
        }

    return Tool(
        name="kb_ingest",
        description=(
            "Tải trang web từ URL thuộc allowlist, phân đoạn và nạp vào kho tri thức. "
            "Trả về kết quả nạp (số chunk, cờ trùng/nghi vấn) chứ không trả nội dung trang."
        ),
        args_model=KBIngestArgs,
        fn=kb_ingest_fn,
        timeout_s=20.0,
        max_retries=2,
    )
