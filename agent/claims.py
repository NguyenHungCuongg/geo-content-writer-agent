"""Schema và logic phán quyết của UC-04: Fact-checker (Phase 2, Task 6).

Bao gồm:
- Data models: Location, Evidence, ClaimVerdict, ClaimReport
- apply_evidence_rule: code tính lại verdict từ evidence, không tin kết luận của model
- blocking_claims: claim has_number có verdict khác supported, dùng khoá nút duyệt (Task 7, 8)
- report_feedback: mỗi claim cần sửa một dòng, đầu vào của revise_uc03 (Task 5)

Luật bằng chứng (roadmap Phase 2, Task 6 line 334):
- supported:    phía supports có ≥1 tier A hoặc ≥2 tier B khác domain,
                VÀ không có contradicts tier A/B.
- contradicted: phía contradicts đạt ngưỡng trên, phía supports không đạt.
- unverifiable: tất cả trường hợp còn lại.
- Tier C không bao giờ đủ. Tier brand theo quyết định D-08.
"""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel

from agent.trace import Tracer


class Location(BaseModel):
    heading: str
    paragraph: int


class Evidence(BaseModel):
    chunk_id: str | None
    url: str
    quote: str
    trust_tier: Literal["A", "B", "C", "brand"]
    stance: Literal["supports", "contradicts"]


class ClaimVerdict(BaseModel):
    claim: str
    location: Location
    has_number: bool
    verdict: Literal["supported", "contradicted", "unverifiable"]
    evidence: list[Evidence]
    action: Literal["keep", "rewrite", "remove"]


class ClaimReport(BaseModel):
    claims: list[ClaimVerdict]
    round: int


# ---------------------------------------------------------------------------
# Hàm nội bộ
# ---------------------------------------------------------------------------


def _domain_of(url: str) -> str:
    """Trích domain từ URL để xác định nguồn độc lập (2B khác domain)."""
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return url.lower()


def _meets_threshold(evidences: list[Evidence]) -> bool:
    """Kiểm tra một phía (supports hoặc contradicts) có đạt ngưỡng hay không.

    Ngưỡng: ≥1 tier A, hoặc ≥2 tier B từ domain khác nhau.
    Tier C và brand không bao giờ đủ (D-08: brand chỉ đủ cho thông tin nội bộ Skyveil,
    claim hiệu quả kỹ thuật phải có A hoặc ≥2B).
    """
    tier_a = [e for e in evidences if e.trust_tier == "A"]
    if len(tier_a) >= 1:
        return True

    tier_b = [e for e in evidences if e.trust_tier == "B"]
    domains = {_domain_of(e.url) for e in tier_b}
    return len(domains) >= 2


# ---------------------------------------------------------------------------
# Hàm public
# ---------------------------------------------------------------------------


def apply_evidence_rule(
    v: ClaimVerdict, *, tracer: Tracer | None = None,
) -> ClaimVerdict:
    """Code tính lại ``verdict`` từ ``evidence``, không tin kết luận của model.

    Ghi trace ``decision`` với ``action="evidence_rule"`` khi verdict bị thay đổi
    so với giá trị model đã gán.
    """
    supports = [e for e in v.evidence if e.stance == "supports"]
    contradicts = [e for e in v.evidence if e.stance == "contradicts"]

    sup_ok = _meets_threshold(supports)
    con_ok = _meets_threshold(contradicts)

    if sup_ok and not con_ok:
        new_verdict: Literal["supported", "contradicted", "unverifiable"] = "supported"
    elif con_ok and not sup_ok:
        new_verdict = "contradicted"
    else:
        # Cả hai đạt (mâu thuẫn) hoặc cả hai không đạt → unverifiable
        new_verdict = "unverifiable"

    # Xác định action dựa trên verdict mới
    if new_verdict == "supported":
        new_action: Literal["keep", "rewrite", "remove"] = "keep"
    elif new_verdict == "contradicted":
        new_action = "remove"
    else:
        new_action = "rewrite"

    old_verdict = v.verdict
    updated = v.model_copy(update={"verdict": new_verdict, "action": new_action})

    if old_verdict != new_verdict and tracer is not None:
        tracer.log(
            "decision",
            action="evidence_rule",
            claim=v.claim,
            old_verdict=old_verdict,
            new_verdict=new_verdict,
            new_action=new_action,
        )

    return updated


def blocking_claims(report: ClaimReport) -> list[ClaimVerdict]:
    """Claim ``has_number`` có verdict khác ``supported``.

    Task 7 và Task 8 dùng danh sách này để khoá nút duyệt (trả HTTP 409)
    khi bài còn claim số liệu chưa được chứng minh.
    """
    return [c for c in report.claims if c.has_number and c.verdict != "supported"]


def report_feedback(report: ClaimReport) -> list[str]:
    """Mỗi claim cần sửa → một dòng (vị trí, hành động, lý do, nguồn).

    Đầu vào của ``revise_uc03`` để Writer sửa bài theo phản hồi của Fact-checker.
    Chỉ lấy claim có ``has_number`` và verdict khác ``supported`` (blocking claims).
    """
    lines: list[str] = []
    for c in report.claims:
        if not c.has_number or c.verdict == "supported":
            continue

        sources = ", ".join(
            f"{e.url} (tier {e.trust_tier}, {e.stance})" for e in c.evidence
        ) or "không tìm thấy nguồn"

        if c.verdict == "contradicted":
            reason = "Số liệu bị nguồn tin cậy phản bác"
            action_text = "gỡ hoặc sửa lại theo nguồn chính xác"
        else:
            reason = "Không tìm được nguồn tin cậy chứng minh"
            action_text = "gỡ số liệu hoặc chuyển thành câu định tính"

        lines.append(
            f"[{c.location.heading}, đoạn {c.location.paragraph}] "
            f"{c.action.upper()}: \"{c.claim}\" — {reason}. "
            f"Nguồn: {sources}. Hành động: {action_text}."
        )
    return lines
