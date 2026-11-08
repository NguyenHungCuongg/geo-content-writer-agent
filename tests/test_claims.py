from agent.claims import (
    ClaimReport,
    ClaimVerdict,
    Evidence,
    Location,
    apply_evidence_rule,
    blocking_claims,
    report_feedback,
)
from agent.trace import Tracer


def make_verdict(
    evidences: list[Evidence],
    claim: str = "Nhiệt độ giảm 12°C",
    has_number: bool = True,
    initial_verdict: str = "unverifiable",
) -> ClaimVerdict:
    return ClaimVerdict(
        claim=claim,
        location=Location(heading="Hiệu quả", paragraph=0),
        has_number=has_number,
        verdict=initial_verdict,
        evidence=evidences,
        action="rewrite",
    )


def test_evidence_rule_1a_supports():
    # 1 A -> supported
    evs = [
        Evidence(
            chunk_id="chunk1",
            url="https://moc.gov.vn/qcvn09",
            quote="Nhiệt độ giảm 12°C",
            trust_tier="A",
            stance="supports",
        )
    ]
    v = make_verdict(evs)
    res = apply_evidence_rule(v)
    assert res.verdict == "supported"
    assert res.action == "keep"


def test_evidence_rule_1b_unverifiable():
    # 1 B -> unverifiable
    evs = [
        Evidence(
            chunk_id="chunk1",
            url="https://cafeland.vn/son-chong-nong",
            quote="Nhiệt độ giảm 12°C",
            trust_tier="B",
            stance="supports",
        )
    ]
    v = make_verdict(evs)
    res = apply_evidence_rule(v)
    assert res.verdict == "unverifiable"
    assert res.action == "rewrite"


def test_evidence_rule_2b_same_domain():
    # 2 B cùng domain -> unverifiable
    evs = [
        Evidence(
            chunk_id="c1",
            url="https://cafeland.vn/bai-1",
            quote="Nhiệt độ giảm 12°C",
            trust_tier="B",
            stance="supports",
        ),
        Evidence(
            chunk_id="c2",
            url="https://cafeland.vn/bai-2",
            quote="Nhiệt độ giảm 12°C",
            trust_tier="B",
            stance="supports",
        ),
    ]
    v = make_verdict(evs)
    res = apply_evidence_rule(v)
    assert res.verdict == "unverifiable"


def test_evidence_rule_2b_different_domain():
    # 2 B khác domain -> supported
    evs = [
        Evidence(
            chunk_id="c1",
            url="https://cafeland.vn/bai-1",
            quote="Nhiệt độ giảm 12°C",
            trust_tier="B",
            stance="supports",
        ),
        Evidence(
            chunk_id="c2",
            url="https://baohatinh.vn/bai-2",
            quote="Nhiệt độ giảm 12°C",
            trust_tier="B",
            stance="supports",
        ),
    ]
    v = make_verdict(evs)
    assert v.location.heading == "Hiệu quả"
    assert v.location.paragraph == 0
    res = apply_evidence_rule(v)
    assert res.verdict == "supported"
    assert res.action == "keep"


def test_evidence_rule_1a_supports_and_1a_contradicts():
    # 1 A supports + 1 A contradicts -> unverifiable
    evs = [
        Evidence(
            chunk_id="c1",
            url="https://moc.gov.vn/qcvn09",
            quote="Nhiệt độ giảm 12°C",
            trust_tier="A",
            stance="supports",
        ),
        Evidence(
            chunk_id="c2",
            url="https://nchmf.gov.vn/thoitiet",
            quote="Nhiệt độ chỉ giảm tối đa 5°C",
            trust_tier="A",
            stance="contradicts",
        ),
    ]
    v = make_verdict(evs)
    res = apply_evidence_rule(v)
    assert res.verdict == "unverifiable"
    assert res.action == "rewrite"


def test_evidence_rule_only_c():
    # chỉ có C -> unverifiable
    evs = [
        Evidence(
            chunk_id=None,
            url="https://blogmaiton.example/post-1",
            quote="Nhiệt độ giảm 12°C",
            trust_tier="C",
            stance="supports",
        ),
        Evidence(
            chunk_id=None,
            url="https://dien-dan-xay-dung.example/thread-2",
            quote="Nhiệt độ giảm 12°C",
            trust_tier="C",
            stance="supports",
        ),
    ]
    v = make_verdict(evs)
    res = apply_evidence_rule(v)
    assert res.verdict == "unverifiable"


def test_evidence_rule_contradicted_threshold():
    # contradicts đạt ngưỡng, supports không đạt -> contradicted
    evs = [
        Evidence(
            chunk_id="c1",
            url="https://moc.gov.vn/qcvn09",
            quote="Nhiệt độ chỉ giảm 2-5°C",
            trust_tier="A",
            stance="contradicts",
        )
    ]
    v = make_verdict(evs)
    res = apply_evidence_rule(v)
    assert res.verdict == "contradicted"
    assert res.action == "remove"


def test_evidence_rule_tracer(tmp_path):
    tracer = Tracer("test-run", traces_dir=tmp_path)
    evs = [
        Evidence(
            chunk_id="c1",
            url="https://moc.gov.vn/qcvn09",
            quote="Nhiệt độ giảm 12°C",
            trust_tier="A",
            stance="supports",
        )
    ]
    v = make_verdict(evs, initial_verdict="unverifiable")
    res = apply_evidence_rule(v, tracer=tracer)
    assert res.verdict == "supported"
    decision_events = [e for e in tracer.events if e.get("event") == "decision"]
    assert len(decision_events) == 1
    assert decision_events[0]["action"] == "evidence_rule"
    assert decision_events[0]["old_verdict"] == "unverifiable"
    assert decision_events[0]["new_verdict"] == "supported"


def test_blocking_claims_and_feedback():
    c1 = make_verdict(
        [], claim="Nhiệt độ giảm 12°C", has_number=True, initial_verdict="unverifiable"
    )
    c1.verdict = "unverifiable"
    c2 = make_verdict(
        [], claim="Sơn mái tôn giúp làm mát", has_number=False, initial_verdict="unverifiable"
    )
    c2.verdict = "unverifiable"
    c3 = make_verdict(
        [], claim="Giảm 20% chi phí điện", has_number=True, initial_verdict="supported"
    )
    c3.verdict = "supported"
    c4 = make_verdict(
        [], claim="90% mái nhà hư hại", has_number=True, initial_verdict="contradicted"
    )
    c4.verdict = "contradicted"

    report = ClaimReport(claims=[c1, c2, c3, c4], round=1)
    blocking = blocking_claims(report)
    assert len(blocking) == 2
    assert {b.claim for b in blocking} == {"Nhiệt độ giảm 12°C", "90% mái nhà hư hại"}

    feedback = report_feedback(report)
    assert len(feedback) == 2
    assert any("Nhiệt độ giảm 12°C" in fb for fb in feedback)
    assert any("90% mái nhà hư hại" in fb for fb in feedback)
