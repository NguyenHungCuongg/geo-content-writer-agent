"""Code-based acceptance checks for UC-01 eval cases."""

from collections.abc import Callable

from pydantic import ValidationError

from agent.schemas import (
    DEFAULT_PERSONA,
    TRACEABLE_FIELDS,
    BrandProfile,
    Prompt,
    PromptSet,
    check_brand_flag,
    check_brand_mentions,
    check_count,
    check_intent_share,
    check_near_duplicates,
    leaves,
    normalize,
    quotable_texts,
)
from agent.uc01 import brand_terms


def result_of(errors: list) -> dict:
    return {"passed": not errors, "details": errors or None}


def is_empty(profile: BrandProfile, field: str) -> bool:
    """Persona mặc định do harness tự thêm, không lấy từ brief, nên tính là rỗng."""
    value = getattr(profile, field)
    return not value or value == [DEFAULT_PERSONA]


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

    prompts = prompt_set.prompts
    try:
        duplicate_errors = check_near_duplicates(prompts, find_duplicates)
    except Exception as error:
        duplicate_errors = [f"không kiểm được prompt trùng nghĩa: {error}"]

    texts = quotable_texts(profile_context)
    normalized_texts = [normalize(text) for text in texts]
    invented_prices = [
        product.price for product in profile.products
        if product.price and not any(normalize(product.price) in text for text in normalized_texts)
    ]

    # Khẳng định quá đà phải nằm trong unverified_claims và không lọt vào trường nội dung.
    expected_claims = expect.get("unverified_claims", [])
    recorded_claims = normalize(" ".join(profile.unverified_claims))
    content = normalize(" ".join(leaves(profile.model_dump(include=set(TRACEABLE_FIELDS)))))
    unrecorded_claims = [c for c in expected_claims if normalize(c) not in recorded_claims]
    leaked_claims = [c for c in expected_claims if normalize(c) in content]

    # Brief không nói tới trường này thì agent không được tự điền (tiêu chí 6: không bịa).
    filled_fields = [f for f in expect.get("empty_fields", []) if not is_empty(profile, f)]
    missing_info_ok = not expect.get("missing_info") or bool(profile.missing_info)

    checks = {
        "schema_valid": {"passed": schema_valid, "details": schema_error},
        "at_least_30_prompts": result_of(check_count(prompts)),
        "intent_share_at_least_15_percent": result_of(check_intent_share(prompts)),
        "brand_mentions_only_navigational_and_at_most_10_percent": result_of([
            *check_brand_mentions(prompts), *check_brand_flag(prompts, brand_names),
        ]),
        "no_cosine_duplicates_at_or_above_0_9": result_of(duplicate_errors),
        "expected_missing_info": {
            "passed": missing_info_ok,
            "details": profile.missing_info or None,
        },
        "expected_fields_left_empty": result_of(filled_fields),
        "expected_claims_are_unverified": result_of(unrecorded_claims),
        "unverified_claims_not_in_content_fields": result_of(leaked_claims),
        "all_sources_are_literal_quotes": result_of(profile.check_sources_quoted(texts)),
        "prices_are_literal_quotes": result_of(invented_prices),
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
