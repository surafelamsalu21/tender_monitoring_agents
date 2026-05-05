"""Tests for generic harvest → Agent 1 listing preparation."""

from app.utils.listing_prep import (
    _is_au_bid_detail_url,
    _trim_au_bids_listing,
    dual_markdown_for_agent1_and_expiry,
)


PAGE = "https://portal.example.org/listing"


def test_dual_includes_page_header_and_raw_markdown():
    md = "## Notices\n\n[Award](https://portal.example.org/notices/award-1.pdf)\n"
    a1, exp = dual_markdown_for_agent1_and_expiry(PAGE, md)
    assert exp == md
    assert a1.startswith("Page URL (context): https://portal.example.org/listing")
    assert "## Notices" in a1
    assert "award-1.pdf" in a1


def test_dual_appends_supplement_from_crawl_links_and_filters_social():
    md = "One line RFQ for workshop.\n"
    html = '<a href="/docs/rfq-99.pdf">pdf</a><a href="https://facebook.com/foo">x</a>'
    links_raw = [
        "https://portal.example.org/detail/rfq-99",
        "//portal.example.org/other",
        "https://facebook.com/track",
    ]
    a1, exp = dual_markdown_for_agent1_and_expiry(PAGE, md, links_raw, html=html)
    assert exp == md
    assert "Supplement" in a1
    assert "rfq-99" in a1
    assert "facebook.com" not in a1.lower()


def test_dual_truncates_huge_markdown_but_expiry_preserves_full():
    raw = "X" * 150_000
    a1, exp = dual_markdown_for_agent1_and_expiry(PAGE, raw, None, html=None)
    assert exp == raw
    assert len(a1) < len(raw)
    assert "character limit" in a1


def test_dual_expiry_none_when_markdown_empty():
    a1, exp = dual_markdown_for_agent1_and_expiry(PAGE, "", [])
    assert exp is None
    assert "Page URL" in a1


def test_au_bids_listing_is_trimmed_to_bid_table_and_detail_links():
    markdown = """
## News
* unrelated news

# All Bids

##  Complaints Submission by Bidders

Complaint text

##  All Bids

| Deadline | Bid Title | Bid Type |
| --- | --- | --- |
| May 18, 2026 | [Real Bid](/en/bids/20260416/real-bid) | [Procurement/ Bids](/en/procurement-bids) |

## Adverts

[Annual Procurement Plan](https://au.int/en/documents/20260101/annual-plan)
"""

    agent_md, expiry_md = dual_markdown_for_agent1_and_expiry(
        "https://au.int/en/bids/",
        markdown,
        [
            "https://au.int/en/bids/20260416/real-bid",
            "https://au.int/en/procurement-bids",
            "https://au.int/en/documents/20260101/annual-plan",
        ],
    )

    assert "Real Bid" in agent_md
    assert "Annual Procurement Plan" not in agent_md
    assert "https://au.int/en/bids/20260416/real-bid" in agent_md
    assert "https://au.int/en/procurement-bids" not in agent_md
    assert expiry_md is not None and "Real Bid" in expiry_md
    assert "Annual Procurement Plan" not in expiry_md


def test_au_bid_detail_url_filter():
    assert _is_au_bid_detail_url("https://au.int/en/bids/20260416/real-bid")
    assert not _is_au_bid_detail_url("https://au.int/en/procurement-bids")
    assert not _is_au_bid_detail_url("https://au.int/en/documents/20260101/annual-plan")


def test_trim_au_bids_listing_removes_topic_resources():
    trimmed = _trim_au_bids_listing(
        "# All Bids\n\n##  All Bids\n\n| Deadline | Bid Title |\n| --- | --- |\n"
        "| May 18, 2026 | [Real Bid](/en/bids/20260416/real-bid) |\n\n"
        "## Topic Resources\n\n[Speech](https://au.int/en/speeches/example)"
    )
    assert "Real Bid" in trimmed
    assert "Speech" not in trimmed
