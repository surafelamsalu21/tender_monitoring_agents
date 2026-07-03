import asyncio
import json
from unittest.mock import MagicMock, patch

from app.crawl.playwright_harvest import (
    _worldbank_api_country_names,
    _worldbank_api_harvest_sync,
    _worldbank_notice_detail_url,
    _worldbank_scope_filter_value,
    harvest_with_playwright,
)
from app.crawl.worldbank_procurement import (
    parse_worldbank_api_markdown,
    worldbank_notice_passes_consulting_prefilter,
    worldbank_notice_to_listing_row,
)
from app.models.page import MonitoredPage

ETHIOPIA_URL = (
    "https://www.worldbank.org/en/projects-operations/procurement"
    "?srce=both&geo_scope=ethiopia"
)

SAMPLE_PAYLOAD = {
    "total": 14561,
    "procnotices": [
        {
            "id": "OP00453371",
            "bid_description": "Procurement of poly bag for woreda nursery management",
            "noticedate": "24-Jun-2026",
            "notice_type": "Contract Award",
            "notice_lang_name": "English",
            "project_ctry_name": "Ethiopia",
            "project_id": "P174385",
            "project_name": "Second Ethiopia Resilient Landscapes and Livelihoods Project",
            "procurement_group": "GO",
            "procurement_method_name": "Request for Quotations",
        },
        {
            "id": "OP00450001",
            "bid_description": "Institutional capacity assessment for rural finance",
            "noticedate": "23-Jun-2026",
            "notice_type": "Request for Expression of Interest",
            "notice_lang_name": "English",
            "project_ctry_name": "Ethiopia",
            "project_id": "P174386",
            "project_name": "Ethiopia Rural Finance Project",
            "procurement_group": "CS",
            "procurement_method_name": "Quality And Cost-Based Selection",
            "bid_reference_no": "ET-MOFED-123-CS-RFQ",
        },
    ],
}


def test_worldbank_scope_filter_value_parses_ethiopia():
    assert _worldbank_scope_filter_value(ETHIOPIA_URL) == "ethiopia"


def test_worldbank_api_country_names_ethiopia():
    assert _worldbank_api_country_names("ethiopia") == ["Ethiopia"]


def test_worldbank_notice_detail_url():
    assert _worldbank_notice_detail_url("OP00453371") == (
        "https://projects.worldbank.org/en/projects-operations/procurement-detail/OP00453371"
    )


def test_consulting_prefilter_drops_awards_and_goods():
    assert worldbank_notice_passes_consulting_prefilter(SAMPLE_PAYLOAD["procnotices"][0]) is False
    assert worldbank_notice_passes_consulting_prefilter(SAMPLE_PAYLOAD["procnotices"][1]) is True


def test_worldbank_notice_to_listing_row():
    row = worldbank_notice_to_listing_row(SAMPLE_PAYLOAD["procnotices"][1])
    assert row is not None
    assert row["title"] == "Institutional capacity assessment for rural finance"
    assert row["country"] == "Ethiopia"
    assert "procurement-detail/OP00450001" in (row["detail_url"] or "")


@patch("app.crawl.playwright_harvest.urlopen")
def test_worldbank_api_harvest_applies_consulting_prefilter(mock_urlopen):
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(SAMPLE_PAYLOAD).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None
    mock_urlopen.return_value = mock_resp

    body, links, raw_json, pages, structured_rows, stats = _worldbank_api_harvest_sync(
        "ethiopia",
        max_pages=1,
    )

    assert pages == 1
    assert stats["raw_seen"] == 2
    assert stats["prefilter_kept"] == 1
    assert stats["prefilter_dropped"] == 1
    assert len(structured_rows) == 1
    assert "Institutional capacity assessment" in body
    assert "poly bag" not in body
    assert len(links) == 1
    meta = json.loads(raw_json)
    assert meta["notice_count"] == 1


def test_parse_worldbank_api_markdown():
    sample_body = (
        "World Bank procurement API harvest.\n\n"
        "- Institutional capacity assessment for rural finance\n"
        "  - Country: Ethiopia\n"
        "  - Project: Ethiopia Rural Finance Project - P174386\n"
        "  - Notice type: Request for Expression of Interest\n"
        "  - Date: 23-Jun-2026\n"
        "  - Link: https://projects.worldbank.org/en/projects-operations/procurement-detail/OP00450001\n"
    )
    rows = parse_worldbank_api_markdown(sample_body)
    assert len(rows) == 1
    assert rows[0]["title"] == "Institutional capacity assessment for rural finance"
    assert "OP00450001" in rows[0]["url"]


@patch("app.crawl.playwright_harvest._worldbank_api_harvest_sync")
def test_harvest_with_playwright_uses_api_for_scoped_worldbank_url(mock_sync):
    mock_sync.return_value = (
        "World Bank procurement API harvest.\n\n- Sample notice",
        ["https://projects.worldbank.org/en/projects-operations/procurement-detail/OP1"],
        '{"scope":"ethiopia"}',
        1,
        [{"title": "Sample notice", "detail_url": "https://projects.worldbank.org/en/projects-operations/procurement-detail/OP1"}],
        {"raw_seen": 1, "prefilter_kept": 1, "prefilter_dropped": 0},
    )
    page = MonitoredPage(
        name="WB Ethiopia",
        url=ETHIOPIA_URL,
        crawl_strategy="playwright",
    )

    result = asyncio.run(harvest_with_playwright(page))

    assert result.status == "success"
    assert result.session_meta["backend"] == "worldbank_procnotices_api"
    assert result.session_meta["applied_filter"] == "wb_api:ethiopia"
    assert result.session_meta["listing_rows_v1"][0]["title"] == "Sample notice"
    assert "Sample notice" in (result.markdown or "")
    mock_sync.assert_called_once()
