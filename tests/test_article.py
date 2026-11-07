"""Test UC-03: schema bài viết, tách câu, phát hiện số liệu, validator dàn ý và bài, 8-gram."""

import pytest
from pydantic import ValidationError

from agent.article import (
    Article,
    ArticleDraft,
    OutlinePlan,
    check_article,
    check_outline,
    count_words,
    has_number,
    split_sentences,
)
from agent.kb import Citation
from agent.tools.similarity import (
    check_similarity_tool,
    load_miniweb_pages,
    max_overlap,
    ngram_overlap,
)
from tests.uc03_fixture import (
    BANNED,
    CHUNK,
    CITATION,
    H2_A,
    H2_B,
    KEYWORD,
    OUTLINE,
    PROMPT_IDS,
    article_markdown,
    outline,
    rules,
)

COPY_BAIT_URL = "https://tapchinhaviet.example/huong-dan-chong-nong-mai-ton-toan-tap"


def errors_of(markdown: str, citations=(CITATION,), **overrides) -> str:
    return "; ".join(check_article(outline(), markdown, list(citations), **rules(**overrides)))


# ------------------------------------------------------------- has_number


@pytest.mark.parametrize(("text", "expected"), [
    ("Skyveil R200 phủ tốt trên mái tôn", False),
    ("Nhiệt độ mái giảm 12°C", True),
    ("Năm 2024 nắng nóng kéo dài", True),
    ("Theo QCVN 09:2017/BXD", True),
    ("Nên sơn 2 lớp", True),
    ("Xếp thứ 3 về độ phản xạ", True),
])
def test_number_sentences(text, expected):
    assert has_number(text) is expected


def test_citation_mark_alone_is_not_a_number():
    assert not has_number("Lớp sơn sáng màu phản xạ nắng tốt hơn [2].")
    assert has_number("Giá 1.450.000 đ cho thùng 5 lít của Skyveil R200.")


# --------------------------------------------------------- split_sentences


def test_split_sentences_tracks_heading_and_block():
    markdown = (
        "# Tiêu đề\n\nMở bài. Câu hai.\n\n## Mục A\n\nĐoạn một. Câu sau [1].\n\n"
        "- Ý thứ nhất\n- Ý thứ hai\n\n### Mục con\n\n| A | B |\n|---|---|\n| 1 | 2 |\n"
    )
    got = [(s.heading, s.paragraph, s.text) for s in split_sentences(markdown)]
    assert got == [
        ("", 0, "Mở bài."), ("", 0, "Câu hai."),
        ("Mục A", 0, "Đoạn một."), ("Mục A", 0, "Câu sau [1]."),
        ("Mục A", 1, "Ý thứ nhất"), ("Mục A", 1, "Ý thứ hai"),
        ("Mục con", 0, "A | B"), ("Mục con", 0, "1 | 2"),
    ]


def test_split_sentences_keeps_abbreviations_and_decimals():
    texts = [s.text for s in split_sentences("Tại TP.HCM giá là 1.450.000 đ. Sau đó tăng.")]
    assert texts == ["Tại TP.HCM giá là 1.450.000 đ.", "Sau đó tăng."]


# ------------------------------------------------------------------ dàn ý


def test_valid_outline_passes():
    assert check_outline(outline(), PROMPT_IDS) == []
    OutlinePlan.model_validate(OUTLINE, context={"prompt_ids": PROMPT_IDS})


def test_outline_rejects_uncovered_prompt():
    data = {**OUTLINE, "sections": [{**s, "prompt_ids": []} for s in OUTLINE["sections"]]}
    with pytest.raises(ValidationError, match="prompt chưa có H2 hoặc câu FAQ"):
        OutlinePlan.model_validate(data, context={"prompt_ids": PROMPT_IDS})


def test_faq_question_can_cover_prompt():
    sections = [{**s, "prompt_ids": []} for s in OUTLINE["sections"]]
    faq = [{**f, "prompt_ids": PROMPT_IDS} if i == 0 else f for i, f in enumerate(OUTLINE["faq"])]
    plan = OutlinePlan.model_validate({**OUTLINE, "sections": sections, "faq": faq})
    assert check_outline(plan, PROMPT_IDS) == []


def test_outline_rejects_missing_target_and_unknown_id():
    data = {**OUTLINE, "target_prompts": ["p01", "p99"]}
    errors = "; ".join(check_outline(OutlinePlan.model_validate(data), PROMPT_IDS))
    assert "thiếu prompt mục tiêu: ['p02']" in errors
    assert "['p99']" in errors


def test_outline_rejects_long_answer_first_no_table_short_faq():
    sections = [{**s, "format": "paragraph"} for s in OUTLINE["sections"]]
    sections[0]["answer_first"] = " ".join(["chữ"] * 61)
    data = {**OUTLINE, "sections": sections, "faq": OUTLINE["faq"][:3]}
    errors = "; ".join(check_outline(OutlinePlan.model_validate(data), PROMPT_IDS))
    assert "answer_first quá 60 từ" in errors
    assert 'format="table"' in errors
    assert "FAQ cần ít nhất 4 câu, hiện có 3" in errors


# -------------------------------------------------------------------- bài


def test_valid_article_passes():
    markdown = article_markdown()
    assert 800 <= count_words(markdown) <= 2000
    assert errors_of(markdown) == ""


def test_article_rejects_uncited_number():
    errors = errors_of(article_markdown(extra="Nên sơn 2 lớp để màng sơn đều."))
    assert "1 câu có số liệu nhưng không có trích dẫn" in errors


def test_reference_section_is_not_checked_for_numbers():
    markdown = article_markdown() + "\n## Nguồn tham khảo\n\n[1] EPA, 2024.\n"
    assert errors_of(markdown) == ""


def test_article_rejects_banned_word():
    errors = errors_of(article_markdown(extra="Đây là giải pháp Tốt Nhất cho mái tôn."))
    assert "từ cấm" in errors
    assert "tốt nhất" in errors


def test_banned_word_matches_whole_words_only():
    assert errors_of(article_markdown(), banned_words=["mát"]) != ""
    assert errors_of(article_markdown(), banned_words=["má"]) == ""  # "mái", "mát" không khớp


def test_article_rejects_wrong_addressing():
    errors = errors_of(article_markdown(reader="bạn"))
    assert 'bài phải gọi người đọc là "anh/chị"' in errors
    assert "['bạn']" in errors


def test_article_rejects_copied_source():
    pages = load_miniweb_pages()
    copied = pages[COPY_BAIT_URL][:2500]
    errors = errors_of(
        article_markdown(extra=copied), similarity=lambda text: max_overlap(text, pages)
    )
    assert "cụm 8 từ" in errors
    assert COPY_BAIT_URL in errors


def test_original_article_passes_similarity_on_miniweb():
    pages = load_miniweb_pages()
    assert errors_of(article_markdown(), similarity=lambda text: max_overlap(text, pages)) == ""


def test_article_rejects_keyword_stuffing():
    stuffed = " ".join([KEYWORD] * 12)
    assert "mật độ từ khoá chính" in errors_of(article_markdown(extra=stuffed))


def test_article_rejects_short_text_missing_h2_and_table():
    errors = errors_of(f"# Bài ngắn\n\n## {H2_A}\n\nCó, anh/chị nên sơn [1].\n")
    assert "so với tối thiểu 800" in errors
    assert H2_B in errors
    assert "bảng Markdown" in errors


def test_h2_must_open_with_paragraph():
    markdown = article_markdown().replace(
        f"## {H2_B}\n\nMỗi cách", f"## {H2_B}\n\n### Mục con\n\nMỗi cách"
    )
    assert "phải mở bằng một đoạn văn" in errors_of(markdown)


def test_citation_must_exist_in_kb_and_quote_must_match():
    fake = Citation(n=1, chunk_id=CHUNK.id, url=CHUNK.url, quote="giảm 50°C")
    unused = Citation(n=2, chunk_id=CHUNK.id, url=CHUNK.url, quote=CITATION.quote)
    assert "không nằm trong nội dung chunk" in errors_of(article_markdown(), citations=[fake])
    assert "không có trong citations: [1]" in errors_of(article_markdown(), citations=[])
    assert "không được dùng trong bài: [2]" in errors_of(
        article_markdown(), citations=[CITATION, unused]
    )


def test_citation_must_come_from_kb_search_of_this_run():
    errors = errors_of(article_markdown(), seen_chunk_ids=set())
    assert "chưa có trong kết quả kb_search" in errors


def test_article_validator_runs_only_with_context():
    data = {"markdown": "ngắn", "citations": [], "notes": []}
    ArticleDraft.model_validate(data)  # không context: chỉ kiểm schema
    context = {"outline": outline(), "brand_voice": {"banned_words": BANNED, "reader": "anh/chị"}}
    with pytest.raises(ValidationError, match="so với tối thiểu 800"):
        ArticleDraft.model_validate(data, context=context)


def test_article_round_trip_without_context():
    article = Article(outline=outline(), markdown=article_markdown(), citations=[CITATION])
    assert Article.model_validate_json(article.model_dump_json()) == article


# ---------------------------------------------------------------- 8-gram


def test_ngram_overlap_basics():
    text = "lớp sơn sáng màu phản xạ phần lớn ánh nắng nên mái nhà mát hơn rõ rệt"
    assert ngram_overlap(text, text) == 1.0
    assert ngram_overlap(text.upper().replace(" ", ", "), text) == 1.0  # hoa thường, dấu câu
    assert ngram_overlap(text, "một nội dung hoàn toàn khác không liên quan gì tới bài") == 0.0
    assert ngram_overlap("quá ngắn", "quá ngắn") == 0.0


def test_check_similarity_tool_reports_closest_page():
    pages = {"https://a.example/x": "một hai ba bốn năm sáu bảy tám chín mười",
             "https://b.example/y": "khác hẳn"}
    tool = check_similarity_tool(lambda: pages)
    result = tool.run({"text": "một hai ba bốn năm sáu bảy tám chín mười"})
    assert result.ok
    assert result.data == {"max_ratio": 1.0, "url": "https://a.example/x"}


def test_chunk_id_marker_is_reported_as_wrong_format_not_as_number():
    # Lỗi gặp khi chạy live 07/11: Gemini ghi chunk_id trong ngoặc thay cho [n].
    sentence = "Mái kim loại hấp thụ nhiệt rất nhanh [3f24bb69434b:0]."
    assert not has_number(sentence)
    errors = errors_of(article_markdown(extra=sentence))
    assert "trích dẫn sai định dạng: ['[3f24bb69434b:0]']" in errors
    assert "câu có số liệu" not in errors


def test_uncited_error_names_the_numbers():
    errors = errors_of(article_markdown(extra="Nên sơn từ 2 đến 3 lớp cho mái tôn."))
    assert "(số: ['2', '3'])" in errors


def test_outline_limits_primary_keyword_in_headings():
    sections = [{**s, "heading": f"{KEYWORD} {i}"} for i, s in enumerate(OUTLINE["sections"])]
    data = {**OUTLINE, "title": KEYWORD, "sections": sections}
    errors = "; ".join(check_outline(OutlinePlan.model_validate(data), PROMPT_IDS))
    assert "xuất hiện 4 lần trong title và H2, tối đa 3" in errors


def test_outline_rejects_banned_word_in_heading():
    sections = [{**OUTLINE["sections"][0], "heading": "Loại sơn tốt nhất cho mái tôn"},
                *OUTLINE["sections"][1:]]
    plan = OutlinePlan.model_validate({**OUTLINE, "sections": sections})
    errors = "; ".join(check_outline(plan, PROMPT_IDS, banned_words=BANNED))
    assert "dàn ý chứa từ cấm của brand kit: ['tốt nhất']" in errors
