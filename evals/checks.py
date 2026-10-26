"""Code-based acceptance checks for UC-01 eval cases."""

from collections.abc import Callable

from pydantic import ValidationError

from agent.schemas import (
    BrandProfile,
    Prompt,
    PromptSet,
    check_brand_flag,
    check_brand_mentions,
    check_count,
    check_intent_share,
    check_near_duplicates,
    quotable_texts,
)
from agent.uc01 import brand_terms


def evaluate_case(
    case: dict,
    profile: BrandProfile,
    prompt_set: PromptSet,
    *,
    observations: list[dict],
    find_duplicates: Callable[[list[str]], list],
) -> dict:
    """Return per-criterion results; no subjective LLM judge is used."""
    topics = case["topics"]
    expect = case.get("expect", {})
    brand_names = brand_terms(profile)
    profile_context = {"brief": case["brief"], "observations": observations}
    prompt_context = {
        "topics": topics,
        "personas": profile.personas,
        "brand_names": brand_names,
    }

    schema_valid = True
    schema_error = None
    try:
        BrandProfile.model_validate(profile.model_dump(), context=profile_context)
        PromptSet.model_validate(prompt_set.model_dump(), context=prompt_context)
    except ValidationError as error:
        schema_valid = False
        schema_error = str(error)

    prompt_errors = [
        *check_count(prompt_set.prompts),
        *check_intent_share(prompt_set.prompts),
        *check_brand_mentions(prompt_set.prompts),
        *check_brand_flag(prompt_set.prompts, brand_names),
    ]
    try:
        duplicate_errors = check_near_duplicates(prompt_set.prompts, find_duplicates)
    except Exception as error:
        duplicate_errors = [f"không kiểm được prompt trùng nghĩa: {error}"]

    quoted_texts = quotable_texts(profile_context)
    sources_are_quotes = all(
        bool(quote) and any(quote in source for source in quoted_texts)
        for quote in profile.sources.values()
    )
    expected_claims = expect.get("unverified_claims", [])
    claims_recorded = all(
        any(claim.casefold() in item.casefold() for item in profile.unverified_claims)
        for claim in expected_claims
    )

    expected_missing_info = expect.get("missing_info")
    checks = {
        "schema_valid": {"passed": schema_valid, "details": schema_error},
        "at_least_30_prompts": {
            "passed": not check_count(prompt_set.prompts),
            "details": prompt_errors[0] if check_count(prompt_set.prompts) else None,
        },
        "intent_share_at_least_15_percent": {
            "passed": not check_intent_share(prompt_set.prompts),
            "details": check_intent_share(prompt_set.prompts) or None,
        },
        "brand_mentions_only_navigational_and_at_most_10_percent": {
            "passed": not check_brand_mentions(prompt_set.prompts)
            and not check_brand_flag(prompt_set.prompts, brand_names),
            "details": prompt_errors or None,
        },
        "no_cosine_duplicates_at_or_above_0_9": {
            "passed": not duplicate_errors,
            "details": duplicate_errors or None,
        },
        "expected_missing_info": {
            "passed": (
                expected_missing_info is None
                or bool(profile.missing_info) == expected_missing_info
            ),
            "details": profile.missing_info or None,
        },
        "expected_claims_are_unverified": {
            "passed": claims_recorded,
            "details": profile.unverified_claims or None,
        },
        "all_sources_are_literal_quotes": {
            "passed": sources_are_quotes,
            "details": profile.sources if not sources_are_quotes else None,
        },
    }
    return {
        "case_id": case["id"],
        "passed": all(result["passed"] for result in checks.values()),
        "checks": checks,
        "profile": profile.model_dump(mode="json"),
        "prompt_set": prompt_set.model_dump(mode="json"),
    }


def fixture_prompt_set(topics: list[str], personas: list[str], brand_name: str) -> PromptSet:
    """Produce valid, varied fixture prompts for the deterministic offline harness run."""
    templates = {
        "informational": [
            "Vì sao {topic} thường được cân nhắc khi trời nắng?",
            "Cách tìm hiểu đặc tính của {topic} trước khi chọn?",
            "Những yếu tố nào ảnh hưởng đến hiệu quả {topic}?",
            "Khi nào nên kiểm tra tình trạng mái trước khi xử lý {topic}?",
            "Có những cách nào để đánh giá nhu cầu {topic} cho nhà ở?",
            "Quy trình cơ bản khi tìm hiểu giải pháp {topic} là gì?",
            "Điều gì cần lưu ý về vật liệu dùng cho {topic}?",
            "Làm sao phân biệt các phương án {topic} theo nhu cầu?",
        ],
        "commercial": [
            "Nên so sánh tiêu chí nào khi chọn dịch vụ {topic}?",
            "Giải pháp {topic} nào phù hợp với ngân sách gia đình?",
            "Ưu nhược điểm của các loại vật liệu cho {topic} là gì?",
            "Đơn vị thi công {topic} thường báo giá dựa trên yếu tố nào?",
            "Làm thế nào chọn nhà cung cấp phù hợp cho {topic}?",
            "Các lựa chọn {topic} khác nhau về bảo hành ra sao?",
            "Cần đối chiếu thông tin gì giữa các bên bán {topic}?",
            "Gói {topic} nào phù hợp với mái nhà diện tích nhỏ?",
        ],
        "transactional": [
            "Cần chuẩn bị gì để đặt lịch khảo sát {topic}?",
            "Có thể yêu cầu báo giá {topic} qua những thông tin nào?",
            "Các bước đặt mua vật liệu cho {topic} gồm những gì?",
            "Làm sao đặt lịch thi công {topic} vào cuối tuần?",
            "Thông tin nào cần gửi để nhận tư vấn về {topic}?",
            "Có thể thanh toán đơn hàng {topic} bằng cách nào?",
            "Sau khi xác nhận đơn {topic}, lịch giao hàng ra sao?",
            "Cách đăng ký dịch vụ kiểm tra mái cho {topic}?",
        ],
        "navigational": [
            f"Thông tin chính thức của {brand_name} về {{topic}} ở đâu?",
            f"{brand_name} cung cấp lựa chọn nào cho {{topic}}?",
            "Tìm danh sách nhà cung cấp giải pháp {topic} ở đâu?",
            "Trang giới thiệu dịch vụ {topic} của đơn vị thi công ở đâu?",
            "Có thể xem danh mục sản phẩm dành cho {topic} ở đâu?",
            "Tìm địa chỉ tư vấn giải pháp {topic} tại khu vực nào?",
            "Website của nhà cung cấp vật liệu {topic} là gì?",
            "Xem hướng dẫn liên hệ đơn vị làm {topic} ở đâu?",
        ],
    }
    prompts = []
    intents = list(templates)
    for index in range(32):
        intent = intents[index % len(intents)]
        template_index = index // len(intents)
        topic = topics[index % len(topics)]
        text = templates[intent][template_index].format(topic=topic)
        mentions_brand = brand_name.casefold() in text.casefold()
        prompts.append(Prompt(
            id=f"p{index + 1:02d}",
            text=text,
            intent=intent,
            topic=topic,
            persona=personas[index % len(personas)],
            keywords=topic.split()[:4],
            mentions_brand=mentions_brand,
        ))
    return PromptSet(prompts=prompts)