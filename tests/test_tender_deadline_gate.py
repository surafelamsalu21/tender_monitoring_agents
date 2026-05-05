"""Unit tests for post–Agent 1 expiry filtering."""

from datetime import date

from app.utils.tender_deadline_gate import (
    extract_listing_closing_cell,
    filter_expired_agent1_items,
    infer_listing_closing_raw,
    parse_date_flexible,
)


def test_parse_iso_and_dd_mm():
    assert parse_date_flexible("2026-03-06") == date(2026, 3, 6)
    assert parse_date_flexible("06-04-2026") == date(2026, 4, 6)
    assert parse_date_flexible("06/04/2026") == date(2026, 4, 6)


def test_extract_closing_cell_shelter_style():
    url = "https://example.org/t.pdf"
    md = f"""
Rubbish line
| Title | Publication Date | Closing Date |
| [RFP EAST]({url}) | 19-03-2026 | 06-04-2026 |
"""
    assert extract_listing_closing_cell(md, url) == "06-04-2026"


def test_infer_closing_when_two_dates_on_same_line_without_pipes():
    url = "https://example.org/note.pdf"
    md = (
        "noise\n"
        f"Something [TITLE]({url}) more text 21-01-2025 20-05-2025 tail\n"
    )
    assert infer_listing_closing_raw(md, url) == "20-05-2025"


def test_infer_closed_after_url_fragment():
    url = "https://example.org/x.pdf"
    md = "\n".join(["", "| [T](" + url + ") | pub | Closed |"])
    assert infer_listing_closing_raw(md, url) == "Closed"


def test_filter_drops_closed_keyword():
    url = "https://example.org/old.pdf"
    md = f"| [TOR]({url}) | 21-01-2025 | Closed |"
    items = [
        {
            "title": "Old survey",
            "url": url,
            "screening": {"step3": {"deadline": "2029-01-01"}},  # model wrong — listing wins first
            "description": "",
        }
    ]
    kept, n = filter_expired_agent1_items(items, md, reference=date(2026, 5, 1))
    assert n == 1
    assert kept == []


def test_filter_drops_past_listing_date():
    url = "https://example.org/a.pdf"
    md = f"| [x]({url}) | 19-03-2026 | 06-04-2026 |"
    items = [{"title": "Bond", "url": url, "screening": {"step3": {}}, "description": ""}]
    kept, n = filter_expired_agent1_items(items, md, reference=date(2026, 5, 1))
    assert n == 1
    assert kept == []


def test_filter_keeps_future_and_unknown():
    fu = "https://example.org/future.pdf"
    md = f"| [x]({fu}) | 17-04-2026 | 25-05-2026 |"
    items_future = [{"title": "Legal", "url": fu, "screening": {"step3": {}}, "description": ""}]
    kept, n = filter_expired_agent1_items(items_future, md, reference=date(2026, 5, 1))
    assert n == 0
    assert len(kept) == 1

    no_row = [{"title": "No table", "url": "https://z.org/x.pdf", "screening": {"step3": {}}, "description": ""}]
    kept2, n2 = filter_expired_agent1_items(no_row, "no url here", reference=date(2026, 5, 1))
    assert n2 == 0
    assert len(kept2) == 1


def test_fallback_model_deadline_when_no_table():
    items = [
        {
            "title": "Parsed only",
            "url": "https://z.org/p.pdf",
            "screening": {"step3": {"deadline": "2025-09-08"}},
            "description": "",
        }
    ]
    kept, n = filter_expired_agent1_items(items, "", reference=date(2026, 5, 1))
    assert n == 1
    assert kept == []
