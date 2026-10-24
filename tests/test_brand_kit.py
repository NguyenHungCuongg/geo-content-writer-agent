from pathlib import Path

import yaml

BRAND = Path(__file__).resolve().parent.parent / "data" / "brand"
KIT = yaml.safe_load((BRAND / "brand_kit.yaml").read_text(encoding="utf-8"))


def test_intro_mission_area():
    assert KIT["about"] and KIT["mission"] and KIT["service_area"]


def test_products_have_attributes_and_price():
    assert len(KIT["products"]) >= 5
    for p in KIT["products"]:
        assert p["attributes"] and p["price"], p["id"]


def test_personas():
    assert len(KIT["personas"]) >= 2


def test_brand_voice():
    voice = KIT["brand_voice"]
    assert voice["tone"] and voice["addressing"] and voice["sentence_length"]
    assert voice["banned_words"]


def test_competitors_have_abbrev_and_ascii_alias():
    assert len(KIT["competitors"]) >= 3
    for c in KIT["competitors"]:
        assert any(a.isascii() for a in c["aliases"]), c["name"]
        assert any(a.isupper() and len(a) <= 4 for a in c["aliases"]), c["name"]


def test_claims_have_evidence_and_respect_voice():
    banned = [w.lower() for w in KIT["brand_voice"]["banned_words"]]
    for c in KIT["approved_claims"]:
        assert c["evidence"], c["id"]
        assert not [w for w in banned if w in c["claim"].lower()], c["id"]


def test_brief_sample_mentions_brand():
    assert KIT["name"] in (BRAND / "brief_sample.md").read_text(encoding="utf-8")
