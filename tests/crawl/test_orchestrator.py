import asyncio
import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.crawl.eligibility import is_monitored_page_due_for_crawl
from app.crawl.orchestrator import harvest_for_page, _flatten_scrape_links
from app.crawl.playwright_harvest import harvest_with_playwright
from app.crawl.types import HarvestResult
from app.models.page import MonitoredPage


def _page(**kwargs):
    p = MonitoredPage(
        name="Test",
        url="https://example.com/tenders",
        crawl_frequency_hours=3,
        crawl_strategy="crawl4ai",
    )
    for k, v in kwargs.items():
        setattr(p, k, v)
    return p


def test_due_when_never_crawled():
    p = _page()
    p.last_crawled = None
    assert is_monitored_page_due_for_crawl(p) is True


def test_not_due_within_frequency_window():
    p = _page(crawl_frequency_hours=6)
    p.last_crawled = datetime.utcnow() - timedelta(hours=2)
    assert is_monitored_page_due_for_crawl(p) is False


def test_due_after_frequency_window():
    p = _page(crawl_frequency_hours=2)
    p.last_crawled = datetime.utcnow() - timedelta(hours=3)
    assert is_monitored_page_due_for_crawl(p) is True


def test_flatten_scrape_links_dict_format():
    links = {
        "internal": [{"href": "https://a/1"}],
        "external": [{"href": "https://b/2"}],
    }
    assert _flatten_scrape_links(links) == ["https://a/1", "https://b/2"]


@patch("app.services.scraper.TenderScraper")
def test_harvest_crawl4ai_success(mock_ts_cls):
    scraper = MagicMock()
    scraper.scrape_page = AsyncMock(
        return_value={
            "status": "success",
            "markdown": "# Tenders",
            "html": "<html/>",
            "links": [{"href": "https://example.com/p/1"}],
        }
    )
    scraper.__aenter__ = AsyncMock(return_value=scraper)
    scraper.__aexit__ = AsyncMock(return_value=None)
    mock_ts_cls.return_value = scraper

    page = _page(url="https://example.com/list", crawl_strategy="crawl4ai")
    r = asyncio.run(harvest_for_page(page))
    assert r.status == "success"
    assert "Tenders" in r.markdown
    assert r.listing_urls == ["https://example.com/p/1"]
    scraper.scrape_page.assert_awaited_once()


@patch("app.crawl.playwright_harvest.harvest_with_playwright", new_callable=AsyncMock)
def test_harvest_playwright_delegates(mock_pw):
    mock_pw.return_value = HarvestResult(
        status="success",
        page_url="https://example.com/tenders",
        markdown="after login",
        listing_urls=["https://example.com/p/1"],
        session_meta={"strategy": "playwright"},
    )
    page = _page(crawl_strategy="playwright")
    r = asyncio.run(harvest_for_page(page))
    assert r.status == "success"
    assert "after login" in r.markdown
    mock_pw.assert_awaited_once()


def test_playwright_missing_credentials_before_browser():
    p = _page(crawl_strategy="playwright")
    p.id = 1
    p.auth_login_url = "https://login.example/o"
    with patch.dict(os.environ, {"CRAWL_AUTH_USERNAME": "", "CRAWL_AUTH_PASSWORD": ""}):
        r = asyncio.run(harvest_with_playwright(p))
    assert r.status == "failed"
    assert "CRAWL_AUTH_USERNAME" in (r.error or "") or "credentials" in (r.error or "").lower()


def test_harvest_unknown_strategy():
    page = _page(crawl_strategy="not-a-strategy")  # type: ignore[arg-type]
    r = asyncio.run(harvest_for_page(page))
    assert r.status == "failed"
    assert "Unknown" in (r.error or "")
