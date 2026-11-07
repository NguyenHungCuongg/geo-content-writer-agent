"""Chống đạo văn cho UC-03 (tiêu chí 6, luật cứng 3): tỉ lệ 8-gram của bài trùng với trang nguồn.

8-gram tính theo âm tiết sau khi chuẩn hoá (NFC, chữ thường, bỏ dấu câu và dấu trích dẫn [n]), nên
đổi hoa thường hay dấu câu không lách được phép đo.
"""

import functools
import re
import unicodedata
from collections.abc import Callable, Mapping
from pathlib import Path

import trafilatura
import yaml
from pydantic import BaseModel, Field

from agent.kb import MANIFEST_PATH
from agent.tools import Tool

WORD = re.compile(r"\w+")
CITATION_MARK = re.compile(r"\[\d+\]")

PageSource = Mapping[str, str] | Callable[[], Mapping[str, str]]


def syllables(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", CITATION_MARK.sub(" ", text)).casefold()
    return WORD.findall(text)


def ngrams(tokens: list[str], n: int) -> list[tuple[str, ...]]:
    return [tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


def ngram_overlap(text: str, source: str, n: int = 8) -> float:
    """Tỉ lệ n-gram (theo âm tiết, đã chuẩn hoá) của `text` có mặt trong `source`, từ 0 đến 1.

    Văn bản ngắn hơn n âm tiết thì không đo được, trả 0.
    """
    grams = ngrams(syllables(text), n)
    if not grams:
        return 0.0
    source_grams = set(ngrams(syllables(source), n))
    return sum(g in source_grams for g in grams) / len(grams)


def max_overlap(text: str, pages: Mapping[str, str], n: int = 8) -> dict:
    """Trang trùng nhiều nhất: {"max_ratio": float, "url": str | None}."""
    best_ratio, best_url = 0.0, None
    for url, page in pages.items():
        ratio = ngram_overlap(text, page, n)
        if ratio > best_ratio:
            best_ratio, best_url = ratio, url
    return {"max_ratio": round(best_ratio, 4), "url": best_url}


class CheckSimilarityArgs(BaseModel):
    text: str = Field(description="Đoạn hoặc cả bài cần kiểm trùng với các trang nguồn")


def check_similarity_tool(pages: PageSource) -> Tool:
    """Tool `check_similarity(text)` -> {"max_ratio", "url"}: trang trùng nhiều nhất trong `pages`.

    `pages` ánh xạ URL -> nội dung trang, hoặc là hàm trả ánh xạ đó (đọc lại mỗi lần gọi, để tính
    cả các chunk agent vừa đọc). KB (Task 4) chỉ có ingest/search/get, không liệt kê được trang,
    nên nơi gọi truyền nội dung trang vào đây.
    """

    def check_similarity_fn(args: CheckSimilarityArgs) -> dict:
        source = pages() if callable(pages) else pages
        return max_overlap(args.text, source)

    return Tool(
        name="check_similarity",
        description=(
            "Kiểm đoạn văn có chép trang nguồn không: trả tỉ lệ cụm 8 từ trùng cao nhất "
            "(max_ratio, 0-1) và URL trang đó. Bài phải có max_ratio không quá 0,05."
        ),
        args_model=CheckSimilarityArgs,
        fn=check_similarity_fn,
        timeout_s=30.0,
        max_retries=0,
    )


@functools.cache
def load_miniweb_pages(manifest_path: Path = MANIFEST_PATH) -> dict[str, str]:
    """Nội dung mọi trang trong snapshot mini-web, trích như `ingest_miniweb` (trafilatura).

    Đây là các trang kho tri thức được nạp từ đó; dùng làm nguồn mặc định cho check_similarity.
    """
    if not manifest_path.is_file():
        return {}
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    pages = {}
    for item in data.get("pages", []):
        path = manifest_path.parent / item.get("file", "")
        if item.get("file") and path.is_file():
            html = path.read_text(encoding="utf-8")
            pages[item["url"]] = trafilatura.extract(html, include_tables=True) or ""
    return pages
