from pathlib import Path
from urllib.parse import urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]
MINIWEB = ROOT / "evals" / "miniweb"
TRAP_KINDS = {
    "injection",
    "hidden_injection",
    "wrong_number",
    "fake_source",
    "wrong_year_unit",
    "contradiction",
    "copy_bait",
    "redirect",
    "slow",
    "duplicate",
}


def test_manifest_is_consistent():
    manifest = yaml.safe_load((MINIWEB / "manifest.yaml").read_text(encoding="utf-8"))
    answer_key = yaml.safe_load((MINIWEB / "answer_key.yaml").read_text(encoding="utf-8"))
    pages = manifest["pages"]
    domains = manifest["domains"]

    urls = [page["url"] for page in pages]
    assert len(urls) == len(set(urls))
    assert len(pages) >= 50
    assert len(domains) >= 8
    assert all(tier in {"A", "B", "C"} for tier in domains.values())

    source_pages = [
        page for page in pages if not urlsplit(page["url"]).hostname.endswith(".example")
    ]
    source_hosts = {
        urlsplit(page["url"]).hostname.removeprefix("www.") for page in source_pages
    }
    assert len(source_pages) >= 40
    assert len(source_hosts) >= 8

    for page in pages:
        parsed = urlsplit(page["url"])
        host = (parsed.hostname or "").removeprefix("www.")
        assert parsed.scheme == "https"
        assert host in domains
        assert page["fetched_at"]
        assert page["license"]
        if page.get("redirect_to"):
            assert not page.get("file")
        else:
            assert page["file"].startswith("pages/")
            assert (MINIWEB / page["file"]).is_file()

    traps = answer_key["traps"]
    assert len(traps) >= 10
    assert {trap["kind"] for trap in traps} == TRAP_KINDS
    assert all(trap["url"] in urls for trap in traps)
    assert all(trap["note"].strip() for trap in traps)

    trap_pages = {
        page["url"]: (MINIWEB / page["file"]).read_text(encoding="utf-8").casefold()
        for page in pages
        if page.get("file") and urlsplit(page["url"]).hostname.endswith(".example")
    }
    assert len(trap_pages) >= 10
    manifest_by_url = {page["url"]: page for page in pages}
    contradiction_urls = {
        trap["url"] for trap in traps if trap["kind"] == "contradiction"
    }
    assert len(contradiction_urls) == 2
    for trap in traps:
        assert trap["kind"] in TRAP_KINDS
        page = manifest_by_url[trap["url"]]
        if trap["kind"] == "redirect":
            assert page.get("redirect_to")
            assert "file" not in page
        else:
            assert trap["url"] in trap_pages
