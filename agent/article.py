"""Schema đầu ra của UC-03: OutlinePlan (dàn ý GEO) và Article (bài Markdown kèm trích dẫn).

Schema dùng vào hai việc như UC-01:
1. Gửi kèm request để Gemini trả JSON đúng cấu trúc.
2. Kiểm lại JSON nhận về theo tiêu chí UC-03; sai luật nào thì báo lỗi tiếng Việt để loop gửi lại
   cho model tự sửa.

`split_sentences` và `has_number` được Task 6 (UC-04) dùng lại để tách claim và đo recall claim
số liệu.

Stub ngày đầu (Task 5): model đã chốt, các hàm và validator chưa cài.
"""

from typing import Literal

from pydantic import BaseModel, Field

from agent.kb import Citation

# Ngưỡng theo tiêu chí chấp nhận của UC-03 và khối Interface của Task 5.
MAX_ANSWER_FIRST_WORDS = 60   # tiêu chí 3
MIN_FAQ = 4                   # tiêu chí 3
MIN_WORDS, MAX_WORDS = 800, 2000
MAX_KEYWORD_DENSITY = 0.03
MAX_NGRAM_OVERLAP = 0.05      # tiêu chí 6
READER_TERMS = ["anh/chị", "bạn", "quý khách"]

SectionFormat = Literal["paragraph", "list", "steps", "table"]


class Section(BaseModel):
    heading: str
    level: Literal[2, 3]
    answer_first: str = Field(description="Đoạn trả lời thẳng câu hỏi, mở đầu mục, tối đa 60 từ")
    points: list[str] = Field(description="Các ý chính của mục")
    format: SectionFormat
    needs_citation: bool = Field(description="Mục có số liệu cần trích dẫn hay không")
    prompt_ids: list[str] = Field(description="Id các prompt mục tiêu mà mục này trả lời")


class FAQItem(BaseModel):
    question: str
    answer: str
    prompt_ids: list[str] = []


class OutlinePlan(BaseModel):
    title: str
    meta_description: str
    primary_keyword: str
    secondary_keywords: list[str]
    target_prompts: list[str] = Field(description="Id các prompt mục tiêu bài phải trả lời")
    sections: list[Section]
    faq: list[FAQItem]


class Article(BaseModel):
    outline: OutlinePlan
    markdown: str
    citations: list[Citation]
    notes: list[str] = Field(
        default=[],
        description="Giải thích khi không làm theo yêu cầu, ví dụ từ chối nhồi từ khoá",
    )


class Sentence(BaseModel):
    heading: str      # H2/H3 gần nhất phía trên câu; "" nếu câu nằm trước heading đầu tiên
    paragraph: int    # số thứ tự đoạn trong mục đó, bắt đầu từ 0
    text: str


def split_sentences(markdown: str) -> list[Sentence]:
    """Tách bài Markdown thành câu, kèm heading và vị trí đoạn của từng câu."""
    raise NotImplementedError("Task 5: split_sentences chưa cài")


def has_number(text: str) -> bool:
    """Câu có số liệu cần trích dẫn: số đo, tỉ lệ, năm, số hiệu văn bản, số lượng, xếp hạng.

    Mã sản phẩm như "Skyveil R200" không tính (Lỗi dễ bị bỏ sót số 5 trong roadmap).
    """
    raise NotImplementedError("Task 5: has_number chưa cài")
