"""Schema đầu ra của UC-01: BrandProfile (hồ sơ thương hiệu) và PromptSet (tập câu hỏi).

Schema dùng vào hai việc:
1. Gửi kèm request để Gemini trả JSON đúng cấu trúc.
2. Kiểm lại JSON nhận về. Sai luật nào thì báo lỗi bằng tiếng Việt; loop gửi lỗi đó
   lại cho Gemini để tự sửa (tối đa 2 lần).

Luật cần dữ liệu ngoài thì đọc từ validation context, không có context thì bỏ qua:

    PromptSet.model_validate(data, context={
        "topics": [...], "personas": [...], "brand_names": [...],
    })
    BrandProfile.model_validate(data, context={"brief": "..."})
"""

from collections import Counter
from typing import Literal, Self, get_args

from pydantic import BaseModel, Field, ValidationInfo, model_validator

Intent = Literal["informational", "navigational", "commercial", "transactional"]
INTENTS = get_args(Intent)

# Ngưỡng theo tiêu chí chấp nhận của UC-01.
MIN_PROMPTS = 30         # tiêu chí 2
MIN_INTENT_SHARE = 0.15  # tiêu chí 2
MAX_BRAND_SHARE = 0.10   # tiêu chí 4

# Persona harness tự thêm khi brief không mô tả nhóm khách hàng nào. Không lấy từ brief nên
# không cần câu trích trong sources; brief thiếu persona thì vẫn ghi vào missing_info.
DEFAULT_PERSONA = "Khách hàng chung"


def normalize(text: str) -> str:
    """Bỏ khoảng trắng thừa, không phân biệt hoa thường; dùng khi so khớp chuỗi."""
    return " ".join(text.split()).casefold()


# ---------------------------------------------------------------- PromptSet


class Prompt(BaseModel):
    id: str = Field(description="Duy nhất trong tập, ví dụ p01")
    text: str = Field(description="Câu hỏi tự nhiên bằng tiếng Việt mà người dùng hay hỏi AI")
    intent: Intent
    topic: str = Field(description="Một trong các chủ đề đã chốt")
    persona: str = Field(description="Một trong BrandProfile.personas")
    keywords: list[str] = Field(description="Từ khoá chính và phụ")
    mentions_brand: bool = Field(description="Câu có chứa tên thương hiệu hay không")


def check_count(prompts: list[Prompt]) -> list[str]:
    if len(prompts) < MIN_PROMPTS:
        return [f"cần ít nhất {MIN_PROMPTS} prompt, hiện có {len(prompts)}"]
    return []


def check_unique_ids(prompts: list[Prompt]) -> list[str]:
    duplicated = [i for i, count in Counter(p.id for p in prompts).items() if count > 1]
    return [f"id bị trùng: {duplicated}"] if duplicated else []


def check_intent_share(prompts: list[Prompt]) -> list[str]:
    total = len(prompts)
    counts = Counter(p.intent for p in prompts)
    return [
        f"intent {intent} có {counts[intent]}/{total} prompt, cần ít nhất {MIN_INTENT_SHARE:.0%}"
        for intent in INTENTS
        if total and counts[intent] / total < MIN_INTENT_SHARE
    ]


def check_brand_mentions(prompts: list[Prompt]) -> list[str]:
    errors = []
    branded = [p for p in prompts if p.mentions_brand]

    not_navigational = [p.id for p in branded if p.intent != "navigational"]
    if not_navigational:
        errors.append(f"chỉ prompt navigational được nhắc thương hiệu, vi phạm: {not_navigational}")

    if prompts and len(branded) / len(prompts) > MAX_BRAND_SHARE:
        errors.append(
            f"{len(branded)}/{len(prompts)} prompt nhắc thương hiệu, tối đa {MAX_BRAND_SHARE:.0%}"
        )
    return errors


def check_brand_flag(prompts: list[Prompt], brand_names: list[str]) -> list[str]:
    """mentions_brand phải đúng với việc câu có chứa tên thương hiệu (hoặc alias) hay không."""
    names = [normalize(name) for name in brand_names if name.strip()]
    if not names:
        return []
    wrong = [
        p.id for p in prompts
        if p.mentions_brand != any(name in normalize(p.text) for name in names)
    ]
    return [f"mentions_brand không khớp nội dung câu: {wrong}"] if wrong else []


def check_allowed(prompts: list[Prompt], field: str, allowed: list[str]) -> list[str]:
    """Giá trị của `field` (topic hoặc persona) phải nằm trong danh sách cho phép."""
    if not allowed:
        return []
    bad = [p.id for p in prompts if getattr(p, field) not in allowed]
    return [f"{field} phải thuộc {allowed}, vi phạm: {bad}"] if bad else []


class PromptSet(BaseModel):
    prompts: list[Prompt]

    @model_validator(mode="after")
    def check_uc01_rules(self, info: ValidationInfo) -> Self:
        context = info.context or {}
        errors = [
            *check_count(self.prompts),
            *check_unique_ids(self.prompts),
            *check_intent_share(self.prompts),
            *check_brand_mentions(self.prompts),
            *check_brand_flag(self.prompts, context.get("brand_names", [])),
            *check_allowed(self.prompts, "topic", context.get("topics", [])),
            *check_allowed(self.prompts, "persona", context.get("personas", [])),
        ]
        if errors:
            raise ValueError("; ".join(errors))
        return self


# ------------------------------------------------------------- BrandProfile

# Trường có dữ liệu thì phải có câu trích trong `sources` (tiêu chí 6).
TRACEABLE_FIELDS = (
    "name", "about", "mission", "service_area",
    "products", "personas", "brand_voice", "competitors",
)


class Product(BaseModel):
    name: str
    attributes: list[str] = Field(default=[], description="Thuộc tính nêu trong brief")
    price: str | None = Field(default=None, description="Giá tham khảo nếu brief có")


class BrandProfile(BaseModel):
    name: str
    about: str | None = None
    mission: str | None = None
    service_area: list[str] = []
    products: list[Product] = []
    personas: list[str] = Field(default=[], description="Tên ngắn của từng nhóm khách hàng")
    brand_voice: str | None = None
    competitors: list[str] = []
    missing_info: list[str] = Field(default=[], description="Thông tin brief còn thiếu")
    clarifying_questions: list[str] = Field(
        default=[], description="Câu hỏi làm rõ cho từng mục trong missing_info"
    )
    unverified_claims: list[str] = Field(
        default=[], description="Khẳng định trong brief không có bằng chứng, ví dụ 'số 1 Việt Nam'"
    )
    sources: dict[str, str] = Field(
        default={},
        description="Tên trường -> câu trích NGUYÊN VĂN từ brief làm căn cứ cho trường đó",
    )

    def has_source(self, field: str) -> bool:
        """Có câu trích không rỗng cho `field`, hoặc cho khoá con như `products[0]`."""
        prefixes = (f"{field}[", f"{field}.")
        return any(
            (key == field or key.startswith(prefixes)) and quote.strip()
            for key, quote in self.sources.items()
        )

    def check_questions(self) -> list[str]:
        if self.missing_info and not self.clarifying_questions:
            return ["có missing_info thì phải có clarifying_questions"]
        return []

    def check_sources_exist(self) -> list[str]:
        def needs_source(field: str) -> bool:
            value = getattr(self, field)
            return bool(value) and value != [DEFAULT_PERSONA]

        unsourced = [f for f in TRACEABLE_FIELDS if needs_source(f) and not self.has_source(f)]
        return [f"thiếu câu trích trong sources cho các trường: {unsourced}"] if unsourced else []

    def check_sources_in_brief(self, brief: str) -> list[str]:
        if not brief:
            return []
        brief = normalize(brief)
        made_up = [key for key, quote in self.sources.items() if normalize(quote) not in brief]
        return [f"sources không phải câu trích nguyên văn từ brief: {made_up}"] if made_up else []

    @model_validator(mode="after")
    def check_traceable(self, info: ValidationInfo) -> Self:
        context = info.context or {}
        errors = [
            *self.check_questions(),
            *self.check_sources_exist(),
            *self.check_sources_in_brief(context.get("brief", "")),
        ]
        if errors:
            raise ValueError("; ".join(errors))
        return self
