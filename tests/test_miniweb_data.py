"""Kho mini-web (Phase 2, Task 2): manifest, trang và đáp án bẫy khớp nhau."""

from pathlib import Path
from urllib.parse import urlsplit

import yaml

MINIWEB = Path(__file__).resolve().parents[1] / "evals" / "miniweb"
TRAP_KINDS = {
    "injection", "hidden_injection", "wrong_number", "fake_source", "wrong_year_unit",
    "contradiction", "copy_bait", "redirect", "slow", "duplicate",
}
# Trang bẫy không được tự khai là bẫy, nếu không agent né được mà eval vẫn báo đạt.
GIVEAWAYS = ("synthetic", "fabricated", "test data", "data-suspicious", "mô phỏng", "hư cấu")


def _load(name: str) -> dict:
    return yaml.safe_load((MINIWEB / name).read_text(encoding="utf-8"))


def _host(url: str) -> str:
    return urlsplit(url).hostname.removeprefix("www.")


def test_manifest_is_consistent():
    manifest, traps = _load("manifest.yaml"), _load("answer_key.yaml")["traps"]
    pages, domains = manifest["pages"], manifest["domains"]
    urls = [p["url"] for p in pages]

    assert len(urls) == len(set(urls))
    assert set(domains.values()) <= {"A", "B", "C"}
    for p in pages:
        assert p["fetched_at"] and p["license"], p["url"]
        assert _host(p["url"]) in domains, p["url"]
        if p.get("redirect_to"):
            assert not p.get("file"), p["url"]
        else:
            assert (MINIWEB / p["file"]).is_file(), p["file"]
    assert all(t["url"] in urls for t in traps)


def test_miniweb_meets_task2_size():
    pages = _load("manifest.yaml")["pages"]
    real = [p for p in pages if not _host(p["url"]).endswith(".example")]
    traps = _load("answer_key.yaml")["traps"]
    assert len(real) >= 40
    assert len({_host(p["url"]) for p in real}) >= 8
    assert len(traps) >= 10
    assert {t["kind"] for t in traps} == TRAP_KINDS


def test_traps_match_roadmap():
    manifest, traps = _load("manifest.yaml"), _load("answer_key.yaml")["traps"]
    by_url = {p["url"]: p for p in manifest["pages"]}
    for t in traps:
        page = by_url[t["url"]]
        if t["kind"] == "redirect":
            assert _host(page["redirect_to"]) not in manifest["domains"]
        if t["kind"] == "slow":
            assert page["delay_s"] > 15
        if page.get("file") and _host(t["url"]).endswith(".example"):
            html = (MINIWEB / page["file"]).read_text(encoding="utf-8").casefold()
            assert not [w for w in GIVEAWAYS if w in html], t["url"]
    injection = next(by_url[t["url"]] for t in traps if t["kind"] == "injection")
    assert "khuyen-mai-x.example" in (MINIWEB / injection["file"]).read_text(encoding="utf-8")
