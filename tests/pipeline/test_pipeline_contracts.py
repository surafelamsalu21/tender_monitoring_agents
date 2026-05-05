"""Tests for crawl artifact builders and DB-compat adapter."""
from __future__ import annotations

from app.crawl.types import HarvestResult
from app.pipeline.crawl_artifact import crawl_artifact_from_harvest, crawl_artifact_from_scraper_dict
from app.pipeline.legacy_adapter import listing_rows_to_tender_dicts
from app.pipeline.schemas import ListingRowV1


def test_crawl_artifact_from_harvest():
    h = HarvestResult(
        status="success",
        page_url="https://example.com/list",
        markdown="# Hello\n\nRow 1",
        listing_urls=["https://example.com/a", "https://example.com/b"],
        session_meta={"title": "List"},
    )
    a = crawl_artifact_from_harvest(h)
    assert a.url == "https://example.com/list"
    assert "Hello" in a.markdown
    assert len(a.links) == 2
    assert a.title == "List"


def test_crawl_artifact_from_scraper_dict():
    d = {
        "status": "success",
        "url": "https://x.test/p",
        "title": "T",
        "markdown": "body",
        "links": {"internal": ["https://x.test/1"], "external": []},
        "metadata": {"k": 1},
        "word_count": 2,
        "char_count": 4,
    }
    a = crawl_artifact_from_scraper_dict(d)
    assert a.url == "https://x.test/p"
    assert "https://x.test/1" in a.links


def test_listing_rows_to_tender_dicts():
    rows = [
        ListingRowV1(
            title="Supply HVAC",
            reference="REF/1",
            deadline="2026-05-01",
            detail_url="/tenders/1",
            country="Tanzania",
            snippet="Short",
        )
    ]
    out = listing_rows_to_tender_dicts(rows, "https://portal.example/procurement")
    assert len(out) == 1
    t = out[0]
    assert t["title"] == "Supply HVAC"
    assert t["url"].startswith("https://portal.example")
    assert t["screening"]["screening_version"] == "v2_simple"
    assert t["screening"]["step3"]["country"] == "Tanzania"
