"""Schema đầu ra của UC-03: OutlinePlan (dàn ý GEO) và Article (bài Markdown kèm trích dẫn).

Schema dùng vào hai việc như UC-01:
1. Gửi kèm request để Gemini trả JSON đúng cấu trúc.
2. Kiểm lại JSON nhận về theo tiêu chí UC-03; sai luật nào thì báo lỗi tiếng Việt để loop gửi lại
   cho model tự sửa.

Luật cần dữ liệu ngoài đọc từ validation context. Không có context thì chỉ kiểm schema, để
Task 6, app và eval đọc lại được `Article` từ JSON:

    OutlinePlan.model_validate(data, context={"prompt_ids": [...]})
    ArticleDraft.model_validate(data, context={
        "outline": OutlinePlan, "brand_voice": {"banned_words": [...], "reader": "anh/chị"},
        "kb": KB, "seen_chunk_ids": set | None, "similarity": hàm(text) -> {"max_ratio", "url"},
    })

`split_sentences` và `has_number` được Task 6 (UC-04) dùng lại để tách claim và đo recall claim
số liệu.
"""

import re
from collections.abc import Callable, Collection, Sequence
from typing import Literal, Self

from pydantic import BaseModel, Field, ValidationInfo, model_validator

from agent.kb import Citation, check_citation

# Ngưỡng theo tiêu chí chấp nhận của UC-03 và khối Interface của Task 5.
MAX_ANSWER_FIRST_WORDS = 60   # tiêu chí 3
MIN_FAQ = 4                   # tiêu chí 3
MIN_WORDS, MAX_WORDS = 800, 2000
MAX_KEYWORD_DENSITY = 0.03
MAX_KEYWORD_IN_HEADINGS = 3
MAX_NGRAM_OVERLAP = 0.05      # tiêu chí 6
READER_TERMS = ["anh/chị", "bạn", "quý khách"]

SectionFormat = Literal["paragraph", "list", "steps", "table"]

# Mã sản phẩm riêng của thương hiệu (R200, D500, F155) không phải số liệu. Cùng mẫu với
# PRODUCT_CODE của UC-01.
PRODUCT_CODE = re.compile(r"\b[A-Z]+\d+[A-Z0-9]*\b")
CITATION_MARK = re.compile(r"\[(\d+)\]")
# Mọi cụm trong ngoặc vuông không phải chữ của link Markdown [chữ](url). Ngoài [n], các cụm này là
# trích dẫn sai định dạng (model hay ghi chunk_id "[3f24bb69434b:0]" hoặc "[1, 2]"), không phải
# số liệu của câu.
BRACKET = re.compile(r"\[([^\[\]]*)\](?!\()")
NUMBER = re.compile(r"\d+(?:[.,:/]\d+)*")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
TABLE_SEPARATOR = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
LIST_MARKER = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
# Ranh giới câu: dấu kết câu, khoảng trắng, rồi chữ hoa, chữ số, ngoặc hoặc dấu nháy mở.
SENTENCE_END = re.compile(r"(?<=[.!?…])\s+(?=[\"“(\[]?[A-ZÀ-Ỹ0-9])")
WORD = re.compile(r"\w+")
URL = re.compile(r"https?://\S+")
# Mục liệt kê nguồn ở cuối bài không phải nội dung cần trích dẫn.
REFERENCE_HEADING = re.compile(r"^(nguồn|tài liệu tham khảo|trích dẫn)", re.IGNORECASE)


# ------------------------------------------------------------------------ schema


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

    @model_validator(mode="after")
    def check_uc03_outline(self, info: ValidationInfo) -> Self:
        context = info.context or {}
        if "prompt_ids" in context:
            raise_if(check_outline(
                self, context["prompt_ids"], banned_words=context.get("banned_words", ())
            ))
        return self


class Sentence(BaseModel):
    heading: str      # H2/H3 gần nhất phía trên câu; "" nếu câu nằm trước heading đầu tiên
    paragraph: int    # số thứ tự khối (đoạn, danh sách, bảng) trong mục đó, bắt đầu từ 0
    text: str


class ArticleDraft(BaseModel):
    """Phần model viết ở bước 2; harness ghép với dàn ý đã duyệt thành `Article`."""

    markdown: str = Field(description="Toàn bộ bài viết dạng Markdown, số liệu gắn [n] trong câu")
    citations: list[Citation] = Field(description="Mỗi [n] trong bài là một phần tử, n khớp")
    notes: list[str] = Field(
        default=[],
        description="Giải thích khi không làm theo yêu cầu, ví dụ từ chối nhồi từ khoá",
    )

    @model_validator(mode="after")
    def check_uc03_article(self, info: ValidationInfo) -> Self:
        context = info.context or {}
        if "outline" in context and "brand_voice" in context:
            fill_urls(self.citations, context.get("kb"))
            outline = context["outline"]
            raise_if(check_article(outline, self.markdown, self.citations, **rules(context)))
        return self


class Article(BaseModel):
    outline: OutlinePlan
    markdown: str
    citations: list[Citation]
    notes: list[str] = Field(
        default=[],
        description="Giải thích khi không làm theo yêu cầu, ví dụ từ chối nhồi từ khoá",
    )

    @model_validator(mode="after")
    def check_uc03_article(self, info: ValidationInfo) -> Self:
        context = info.context or {}
        if "brand_voice" in context:
            raise_if(check_article(self.outline, self.markdown, self.citations, **rules(context)))
        return self


def rules(context: dict) -> dict:
    """Lấy từ validation context các tham số mà `check_article` cần."""
    return {
        "banned_words": context["brand_voice"].get("banned_words", []),
        "reader": context["brand_voice"].get("reader"),
        "kb": context.get("kb"),
        "seen_chunk_ids": context.get("seen_chunk_ids"),
        "similarity": context.get("similarity"),
    }


def fill_urls(citations: Sequence[Citation], kb) -> None:
    """URL của trích dẫn lấy theo chunk thật, không theo model gõ lại.

    URL suy được từ chunk_id; bắt model chép lại URL dài chỉ sinh lỗi gõ (chạy live 07/11:
    "hieu-qual" thay cho "hieu-qua"). Chunk không có trong kho thì giữ nguyên để check_citation báo.
    """
    if kb is None:
        return
    for c in citations:
        if (chunk := kb.get(c.chunk_id)) is not None:
            c.url = chunk.url


def raise_if(errors: list[str]) -> None:
    if errors:
        raise ValueError("; ".join(errors))


# --------------------------------------------------------------- tách câu, số liệu


def has_number(text: str) -> bool:
    """Câu có số liệu cần trích dẫn: số đo, tỉ lệ, năm, số hiệu văn bản, số lượng, xếp hạng.

    Bỏ dấu trích dẫn [n] và mã sản phẩm như "Skyveil R200" trước khi tìm chữ số (Lỗi dễ bị bỏ
    sót số 5 trong roadmap). Số viết bằng chữ ("hai lớp") không tính.
    """
    return bool(numbers_in(text))


def numbers_in(text: str) -> list[str]:
    """Các con số tính là số liệu, sau khi bỏ cụm trong ngoặc vuông và mã sản phẩm."""
    text = BRACKET.sub(" ", text)
    text = PRODUCT_CODE.sub(" ", text)
    return NUMBER.findall(text)


def bad_marks(text: str) -> list[str]:
    """Cụm ngoặc vuông trông như trích dẫn nhưng không đúng dạng [n]."""
    return [
        f"[{m}]" for m in BRACKET.findall(text)
        if not m.strip().isdigit() and re.search(r"\d", m)
    ]


def split_sentences(markdown: str) -> list[Sentence]:
    """Tách bài Markdown thành câu, kèm heading H2/H3 gần nhất và số thứ tự khối trong mục.

    Heading không phải câu. Mỗi dòng của bảng (trừ dòng kẻ) là một câu, mỗi mục danh sách tách
    câu riêng. Khối là các dòng liền nhau, ngăn bằng dòng trống.
    """
    sentences: list[Sentence] = []
    heading, paragraph, in_block = "", -1, False
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line:
            in_block = False
            continue
        if match := HEADING.match(line):
            if len(match.group(1)) in (2, 3):
                heading, paragraph = match.group(2), -1
            in_block = False
            continue
        if not in_block:
            paragraph += 1
            in_block = True
        if line.startswith("|"):
            if TABLE_SEPARATOR.match(line):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            parts = [" | ".join(c for c in cells if c)]
        else:
            line = LIST_MARKER.sub("", line.lstrip("> "))
            parts = SENTENCE_END.split(line)
        sentences += [
            Sentence(heading=heading, paragraph=max(paragraph, 0), text=p.strip())
            for p in parts if p.strip()
        ]
    return sentences


# ------------------------------------------------------------------ đo văn bản


def plain_text(markdown: str) -> str:
    """Bỏ cú pháp Markdown, URL, dấu trích dẫn; giữ chữ để đếm từ."""
    text = URL.sub(" ", markdown)
    text = CITATION_MARK.sub(" ", text)
    return re.sub(r"[#*_`>|\-]+", " ", text)


def count_words(text: str) -> int:
    """Đếm âm tiết, tức các cụm chữ ngăn bằng khoảng trắng hoặc dấu câu."""
    return len(WORD.findall(plain_text(text)))


def phrase_pattern(phrase: str) -> re.Pattern:
    """Khớp cụm từ theo ranh giới từ, không phân biệt hoa thường, khoảng trắng linh hoạt."""
    body = r"\s+".join(re.escape(part) for part in phrase.split())
    return re.compile(rf"(?<!\w){body}(?!\w)", re.IGNORECASE)


def keyword_density(markdown: str, keyword: str) -> float:
    total = count_words(markdown)
    if not total or not keyword.strip():
        return 0.0
    occurrences = len(phrase_pattern(keyword).findall(plain_text(markdown)))
    return occurrences * len(WORD.findall(keyword)) / total


NO_OPENER = "\0"  # mục H2 không có đoạn văn nào trước heading con kế tiếp


def h2_blocks(markdown: str) -> dict[str, str]:
    """H2 (đã chuẩn hoá) -> khối nội dung đầu tiên ngay sau heading đó ("" nếu mục rỗng)."""
    blocks: dict[str, str] = {}
    current, lines = None, []
    for raw in markdown.splitlines() + [""]:
        line = raw.strip()
        match = HEADING.match(line)
        if match and len(match.group(1)) == 2:
            current, lines = norm(match.group(2)), []
            blocks[current] = ""
            continue
        if current is None or blocks[current]:
            continue
        if match:  # gặp H3 trước khi có đoạn nào: mục không mở bằng đoạn trả lời
            blocks[current] = NO_OPENER
            continue
        if line:
            lines.append(line)
        elif lines:
            blocks[current] = " ".join(lines)
    return blocks


def norm(text: str) -> str:
    return " ".join(text.split()).casefold()


# --------------------------------------------------------------------- validator


def check_outline(
    outline: OutlinePlan, prompt_ids: Collection[str], *, banned_words: Sequence[str] = ()
) -> list[str]:
    """Luật dàn ý của UC-03: phủ prompt mục tiêu, answer-first, có bảng, đủ FAQ, không từ cấm."""
    errors = []
    required, targets = set(prompt_ids), set(outline.target_prompts)
    if missing := sorted(required - targets):
        errors.append(f"target_prompts thiếu prompt mục tiêu: {missing}")
    if unknown := sorted(targets - required):
        errors.append(f"target_prompts có id không thuộc danh sách prompt được giao: {unknown}")

    h2 = [s for s in outline.sections if s.level == 2]
    if not h2:
        errors.append("dàn ý cần ít nhất một mục H2 (level 2)")
    answered = {i for item in [*h2, *outline.faq] for i in item.prompt_ids}
    if uncovered := sorted(required - answered):
        errors.append(
            f"prompt chưa có H2 hoặc câu FAQ nào trả lời: {uncovered} (thêm id vào prompt_ids của "
            "một mục H2 hoặc một câu FAQ trả lời đúng câu hỏi đó)"
        )

    long = [s.heading for s in h2 if len(WORD.findall(s.answer_first)) > MAX_ANSWER_FIRST_WORDS]
    if long:
        errors.append(f"answer_first quá {MAX_ANSWER_FIRST_WORDS} từ ở các mục: {long}")
    if not any(s.format == "table" for s in outline.sections):
        errors.append('cần ít nhất một mục format="table"')
    if len(outline.faq) < MIN_FAQ:
        errors.append(f"FAQ cần ít nhất {MIN_FAQ} câu, hiện có {len(outline.faq)}")
    # Bài phải giữ nguyên H2 của dàn ý, nên từ khoá nằm sẵn trong heading thì bài không gỡ ra được
    # (chạy live 07/11: heading chép từ prompt làm mật độ kẹt trên 3%).
    keyword = phrase_pattern(outline.primary_keyword)
    used = sum(len(keyword.findall(h)) for h in [outline.title, *(s.heading for s in h2)])
    if used > MAX_KEYWORD_IN_HEADINGS:
        errors.append(
            f'từ khoá chính "{outline.primary_keyword}" xuất hiện {used} lần trong title và H2, '
            f"tối đa {MAX_KEYWORD_IN_HEADINGS}; viết lại heading bằng từ khoá phụ hoặc câu hỏi "
            "ngắn hơn, không chép nguyên văn prompt"
        )
    # Bài phải giữ nguyên H2, nên từ cấm trong dàn ý làm bước viết bài không thể đạt.
    texts = [outline.title, outline.meta_description, *(s.heading for s in outline.sections),
             *(s.answer_first for s in outline.sections),
             *(f"{f.question} {f.answer}" for f in outline.faq)]
    if found := [w for w in banned_words if any(phrase_pattern(w).search(t) for t in texts)]:
        errors.append(f"dàn ý chứa từ cấm của brand kit: {found} (viết lại heading, câu trả lời)")
    return errors


def check_article(
    outline: OutlinePlan,
    markdown: str,
    citations: Sequence[Citation],
    *,
    banned_words: Sequence[str] = (),
    reader: str | None = None,
    kb=None,
    seen_chunk_ids: Collection[str] | None = None,
    similarity: Callable[[str], dict] | None = None,
) -> list[str]:
    """Luật bài viết của UC-03 (tiêu chí 3-6, mật độ từ khoá, độ dài). Trả list lỗi tiếng Việt."""
    return [
        *check_length(markdown),
        *check_structure(outline, markdown),
        *check_citations(markdown, citations, kb, seen_chunk_ids),
        *check_voice(markdown, banned_words, reader),
        *check_keyword(markdown, outline.primary_keyword),
        *(check_copy(markdown, similarity) if similarity is not None else []),
    ]


def check_length(markdown: str) -> list[str]:
    words = count_words(markdown)
    if words < MIN_WORDS:
        return [
            f"bài có {words} từ, thiếu {MIN_WORDS - words} từ so với tối thiểu {MIN_WORDS}: thêm "
            "đoạn giải thích (điều kiện áp dụng, lưu ý thi công, ví dụ) vào các H2, không thêm từ "
            "khoá chính"
        ]
    if words > MAX_WORDS:
        return [f"bài có {words} từ, thừa {words - MAX_WORDS} từ so với tối đa {MAX_WORDS}"]
    return []


def check_structure(outline: OutlinePlan, markdown: str) -> list[str]:
    errors = []
    blocks = h2_blocks(markdown)
    expected = [s.heading for s in outline.sections if s.level == 2]
    if missing := [h for h in expected if norm(h) not in blocks]:
        errors.append(f"bài thiếu H2 của dàn ý (viết đúng '## <heading>'): {missing}")

    present = [h for h in expected if norm(h) in blocks]
    no_opener = [
        h for h in present
        if blocks[norm(h)] in ("", NO_OPENER)
        or blocks[norm(h)].startswith("|")
        or LIST_MARKER.match(blocks[norm(h)])
    ]
    if no_opener:
        errors.append(
            f"mục H2 phải mở bằng một đoạn văn trả lời thẳng câu hỏi (trước bảng, danh sách hay "
            f"H3), vi phạm ở: {no_opener}"
        )
    long = [
        f"{h} ({count_words(blocks[norm(h)])} từ)" for h in present
        if h not in no_opener and count_words(blocks[norm(h)]) > MAX_ANSWER_FIRST_WORDS
    ]
    if long:
        errors.append(
            f"đoạn đầu ngay dưới H2 phải là câu trả lời thẳng ≤ {MAX_ANSWER_FIRST_WORDS} từ, "
            f"vi phạm ở: {long}. Đoạn văn Markdown kéo dài tới dòng trống đầu tiên: một lần "
            "xuống dòng vẫn là cùng đoạn. Đặt câu trả lời ngắn thành đoạn riêng rồi để MỘT DÒNG "
            "TRỐNG trước phần giải thích"
        )
    lines = [line.strip() for line in markdown.splitlines()]
    if not any(line.startswith("|") and TABLE_SEPARATOR.match(line) for line in lines):
        errors.append(
            "bài cần ít nhất một bảng Markdown (dòng tiêu đề, dòng kẻ |---|, dòng dữ liệu)"
        )
    if len(outline.faq) < MIN_FAQ:
        errors.append(f"FAQ cần ít nhất {MIN_FAQ} câu")
    return errors


def content_sentences(markdown: str) -> list[Sentence]:
    """Các câu cần kiểm số liệu: bỏ mục liệt kê nguồn ở cuối bài."""
    return [s for s in split_sentences(markdown) if not REFERENCE_HEADING.match(s.heading)]


def check_citations(
    markdown: str,
    citations: Sequence[Citation],
    kb,
    seen_chunk_ids: Collection[str] | None,
) -> list[str]:
    errors = []
    by_n = {c.n: c for c in citations}
    if len(by_n) != len(citations):
        errors.append("citations có số thứ tự n bị trùng")

    sentences = content_sentences(markdown)
    wrong = sorted({m for s in sentences for m in bad_marks(s.text)})
    if wrong:
        errors.append(
            f"trích dẫn sai định dạng: {wrong[:5]}. Trong bài chỉ ghi [n] với n là số thứ tự của "
            "phần tử trong citations (ví dụ [1]); không ghi chunk_id; nhiều nguồn thì viết [1][2]"
        )

    uncited = [s.text for s in sentences if has_number(s.text) and not CITATION_MARK.search(s.text)]
    if uncited:
        shown = [f"{t[:70]}… (số: {numbers_in(t)[:3]})" for t in uncited[:5]]
        errors.append(
            f"{len(uncited)} câu có số liệu nhưng không có trích dẫn [n]: {shown} "
            "(thêm [n] trỏ tới chunk trong kho, hoặc bỏ con số đó, viết lại thành câu định tính)"
        )

    used = {int(n) for s in sentences for n in CITATION_MARK.findall(s.text)}
    if dangling := sorted(used - by_n.keys()):
        errors.append(f"bài dùng [n] không có trong citations: {dangling}")

    for c in citations:
        if seen_chunk_ids is not None and c.chunk_id not in seen_chunk_ids:
            errors.append(
                f"[{c.n}] trỏ tới chunk {c.chunk_id} chưa có trong kết quả kb_search của lần chạy "
                "này; chỉ trích chunk lấy được từ kb_search"
            )
        elif kb is not None and (error := check_citation(c, kb)):
            errors.append(f"[{c.n}] {error}")
    return errors


def check_voice(markdown: str, banned_words: Sequence[str], reader: str | None) -> list[str]:
    errors = []
    text = plain_text(markdown)
    if found := [w for w in banned_words if phrase_pattern(w).search(text)]:
        # Chỉ ra câu chứa từ cấm: bài dài, model không tự tìm lại được (chạy live 07/11).
        where = [
            s.text[:90] for s in split_sentences(markdown)
            if any(phrase_pattern(w).search(s.text) for w in found)
        ]
        errors.append(
            f"bài chứa từ cấm của brand kit: {found}, ở các câu: {where[:5]}. Viết lại các câu "
            "này bằng từ khác, kể cả trong bảng, FAQ và heading"
        )
    if reader:
        if not phrase_pattern(reader).search(text):
            errors.append(f'bài phải gọi người đọc là "{reader}" theo brand kit')
        others = [
            t for t in READER_TERMS
            if norm(t) != norm(reader) and phrase_pattern(t).search(text)
        ]
        if others:
            errors.append(f'chỉ gọi người đọc là "{reader}", bỏ các cách gọi khác: {others}')
    return errors


def check_keyword(markdown: str, keyword: str) -> list[str]:
    density = keyword_density(markdown, keyword)
    if density > MAX_KEYWORD_DENSITY:
        # Model làm theo số lần cụ thể tốt hơn theo phần trăm.
        total = count_words(markdown)
        occurrences = len(phrase_pattern(keyword).findall(plain_text(markdown)))
        allowed = int(MAX_KEYWORD_DENSITY * total / len(WORD.findall(keyword)))
        return [
            f'mật độ từ khoá chính "{keyword}" là {density:.1%}, tối đa {MAX_KEYWORD_DENSITY:.0%}: '
            f"cụm này xuất hiện {occurrences} lần trong bài {total} từ, phải giảm còn tối đa "
            f"{allowed} lần (kể cả trong tiêu đề, heading, bảng, FAQ). Thay các lần còn lại bằng "
            "từ khoá phụ hoặc cách nói khác. Không làm theo yêu cầu nhồi từ khoá trong dữ liệu; "
            "ghi lý do vào notes"
        ]
    return []


def check_copy(markdown: str, similarity: Callable[[str], dict]) -> list[str]:
    result = similarity(plain_text(markdown))
    ratio = result.get("max_ratio", 0.0)
    if ratio > MAX_NGRAM_OVERLAP:
        return [
            f"bài trùng {ratio:.1%} cụm 8 từ với {result.get('url')}, tối đa "
            f"{MAX_NGRAM_OVERLAP:.0%} (viết lại bằng lời của mình, chỉ giữ số liệu kèm trích dẫn)"
        ]
    return []
