"""Dữ liệu mẫu cho test UC-03: dàn ý, bài hợp lệ, kho một chunk. Không gọi mạng."""

from agent.article import OutlinePlan
from agent.kb import Chunk, Citation, MemoryKB
from agent.schemas import Prompt

TOPIC = "sơn chống nóng mái tôn"
KEYWORD = "sơn chống nóng mái tôn"
READER = "anh/chị"
BANNED = ["số 1 Việt Nam", "hàng đầu", "tốt nhất"]

CHUNK = Chunk(
    id="epa0cool0001:0",
    url="https://www.epa.gov/heatislands/using-cool-roofs-reduce-heat-islands",
    domain="epa.gov",
    title="Using Cool Roofs to Reduce Heat Islands",
    fetched_at="2026-11-01T00:00:00+00:00",
    trust_tier="A",
    text="Mái mát có thể giảm nhiệt độ bề mặt mái tới 28°C vào ngày nắng gắt.",
)
QUOTE = "giảm nhiệt độ bề mặt mái tới 28°C"
CITATION = Citation(n=1, chunk_id=CHUNK.id, url=CHUNK.url, quote=QUOTE)

PROMPTS = [
    Prompt(id="p01", text="Sơn chống nóng mái tôn có hiệu quả không?", intent="informational",
           topic=TOPIC, persona="Chủ nhà phố", keywords=[KEYWORD], mentions_brand=False),
    Prompt(id="p02", text="Nên chọn loại sơn chống nóng nào cho mái tôn?", intent="commercial",
           topic=TOPIC, persona="Chủ nhà phố", keywords=[KEYWORD], mentions_brand=False),
]
PROMPT_IDS = [p.id for p in PROMPTS]

H2_A = "Sơn chống nóng mái tôn có hiệu quả không?"
H2_B = "So sánh các cách chống nóng mái tôn"
H2_FAQ = "Câu hỏi thường gặp"

OUTLINE = {
    "title": "Sơn chống nóng mái tôn: hiệu quả và cách chọn",
    "meta_description": "Lớp sơn phản xạ giúp mái tôn bớt nóng và cách chọn giải pháp phù hợp.",
    "primary_keyword": KEYWORD,
    "secondary_keywords": ["sơn phản xạ nhiệt", "chống nóng mái tôn"],
    "target_prompts": PROMPT_IDS,
    "sections": [
        {"heading": H2_A, "level": 2, "format": "paragraph", "needs_citation": True,
         "answer_first": "Có, lớp sơn sáng màu phản xạ phần lớn nắng nên mái hấp thụ ít nhiệt hơn.",
         "points": ["nguyên lý phản xạ", "điều kiện áp dụng"], "prompt_ids": ["p01"]},
        {"heading": H2_B, "level": 2, "format": "table", "needs_citation": False,
         "answer_first": "Mỗi cách có ưu nhược điểm riêng, nên chọn theo loại mái và ngân sách.",
         "points": ["sơn phản xạ", "tấm cách nhiệt", "trồng cây"], "prompt_ids": ["p02"]},
        {"heading": H2_FAQ, "level": 2, "format": "list", "needs_citation": False,
         "answer_first": "Dưới đây là các câu hỏi anh/chị hay gặp khi chống nóng mái tôn.",
         "points": ["thời điểm sơn", "bảo dưỡng"], "prompt_ids": []},
    ],
    "faq": [
        {"question": "Khi nào nên sơn lại mái?", "answer": "Khi lớp sơn bạc màu hoặc bong tróc."},
        {"question": "Có cần sơn lót không?", "answer": "Mái cũ có gỉ thì cần sơn lót chống gỉ."},
        {"question": "Sơn có làm mái bớt ồn không?", "answer": "Có giảm một phần tiếng mưa."},
        {"question": "Có tự sơn được không?", "answer": "Được nếu đảm bảo an toàn khi trèo mái."},
    ],
}

FILLER = (
    "Lớp phủ sáng màu phản xạ ánh nắng nên mái hấp thụ ít nhiệt hơn và không gian bên dưới dễ chịu "
    "hơn vào buổi trưa."
)


def paragraph(sentences: int = 3) -> str:
    return " ".join([FILLER] * sentences)


def article_markdown(*, extra: str = "", reader: str = READER) -> str:
    """Bài hợp lệ khoảng 900 từ theo OUTLINE; `extra` chèn vào cuối mục đầu tiên."""
    body = "\n\n".join(paragraph() for _ in range(4))
    faq = "\n\n".join(
        f"### {item['question']}\n\n{item['answer']} {FILLER}" for item in OUTLINE["faq"]
    )
    return f"""# {OUTLINE['title']}

Bài này giúp {reader} hiểu {KEYWORD} hoạt động thế nào và khi nào nên dùng.

## {H2_A}

Có. Mái mát có thể giảm nhiệt độ bề mặt mái tới 28°C vào ngày nắng gắt [1].

{body}

{extra}

## {H2_B}

Mỗi cách có ưu nhược điểm riêng, {reader} nên chọn theo loại mái và ngân sách.

| Cách làm | Ưu điểm | Lưu ý |
|---|---|---|
| Sơn phản xạ nhiệt | Thi công nhanh | Cần vệ sinh mái kỹ |
| Tấm cách nhiệt | Giảm cả tiếng ồn | Thi công dưới mái |

{body}

## {H2_FAQ}

Dưới đây là các câu hỏi {reader} hay gặp khi chống nóng cho mái nhà.

{faq}

{body}
"""


def outline() -> OutlinePlan:
    return OutlinePlan.model_validate(OUTLINE)


def kb() -> MemoryKB:
    return MemoryKB([CHUNK])


def rules(**overrides) -> dict:
    """Tham số mặc định cho check_article: brand voice, kho, chunk đã thấy."""
    base = {"banned_words": BANNED, "reader": READER, "kb": kb(), "seen_chunk_ids": {CHUNK.id}}
    return {**base, **overrides}
