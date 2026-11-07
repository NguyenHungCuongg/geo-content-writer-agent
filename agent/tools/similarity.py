"""Chống đạo văn cho UC-03 (tiêu chí 6, luật cứng 3): tỉ lệ 8-gram của bài trùng với trang nguồn.

Stub ngày đầu (Task 5): chữ ký đã chốt, thân hàm chưa cài.
"""

from collections.abc import Mapping

from pydantic import BaseModel, Field

from agent.tools import Tool


def ngram_overlap(text: str, source: str, n: int = 8) -> float:
    """Tỉ lệ n-gram (theo âm tiết, đã chuẩn hoá) của `text` có mặt trong `source`, từ 0 đến 1."""
    raise NotImplementedError("Task 5: ngram_overlap chưa cài")


class CheckSimilarityArgs(BaseModel):
    text: str = Field(description="Đoạn hoặc cả bài cần kiểm trùng với các trang nguồn")


def check_similarity_tool(pages: Mapping[str, str]) -> Tool:
    """Tool `check_similarity(text)` -> {"max_ratio", "url"}: trang trùng nhiều nhất trong `pages`.

    `pages` ánh xạ URL -> nội dung trang trong kho. KB (Task 4) chỉ có ingest/search/get, không
    liệt kê được trang, nên nơi gọi truyền nội dung trang vào đây.
    """

    def check_similarity_fn(args: CheckSimilarityArgs) -> dict:
        raise NotImplementedError("Task 5: check_similarity chưa cài")

    return Tool(
        name="check_similarity",
        description=(
            "Kiểm đoạn văn có chép trang nguồn không: trả tỉ lệ 8-gram trùng cao nhất (max_ratio, "
            "0-1) và URL trang đó. Bài phải có max_ratio không quá 0,05."
        ),
        args_model=CheckSimilarityArgs,
        fn=check_similarity_fn,
    )
