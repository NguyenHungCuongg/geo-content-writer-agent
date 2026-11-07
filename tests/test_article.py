"""Test UC-03: schema bài viết. Stub ngày đầu chỉ kiểm interface import được và model đúng hình."""

import pytest

from agent.article import Article, FAQItem, OutlinePlan, Section, Sentence, has_number
from agent.kb import Citation
from agent.tools.similarity import check_similarity_tool
from agent.uc03 import revise_uc03, run_uc03


def make_outline() -> OutlinePlan:
    return OutlinePlan(
        title="Sơn chống nóng mái tôn có hiệu quả không?",
        meta_description="Cách sơn phản xạ nhiệt giảm nóng cho nhà mái tôn.",
        primary_keyword="sơn chống nóng mái tôn",
        secondary_keywords=["sơn phản xạ nhiệt"],
        target_prompts=["p01"],
        sections=[
            Section(
                heading="Sơn chống nóng hoạt động thế nào?",
                level=2,
                answer_first="Sơn phản xạ phần lớn bức xạ mặt trời nên mái hấp thụ ít nhiệt hơn.",
                points=["độ phản xạ", "độ phát xạ"],
                format="table",
                needs_citation=True,
                prompt_ids=["p01"],
            )
        ],
        faq=[FAQItem(question="Nên sơn mấy lớp?", answer="Theo hướng dẫn của nhà sản xuất.")],
    )


def test_article_models_round_trip():
    article = Article(
        outline=make_outline(),
        markdown="# Tiêu đề\n\n## Mục\n\nĐoạn văn.",
        citations=[Citation(n=1, chunk_id="abc:0", url="https://example.gov.vn/x", quote="x")],
    )
    assert Article.model_validate_json(article.model_dump_json()) == article
    assert article.notes == []
    assert Sentence(heading="Mục", paragraph=0, text="Đoạn văn.").paragraph == 0


def test_stub_functions_are_not_implemented_yet():
    with pytest.raises(NotImplementedError):
        has_number("Nhiệt độ mái giảm 12°C")
    assert check_similarity_tool({}).name == "check_similarity"
    assert callable(run_uc03) and callable(revise_uc03)
