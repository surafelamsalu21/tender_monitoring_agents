import asyncio
import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.crawl.eligibility import is_monitored_page_due_for_crawl
from app.crawl.eu_funding import filter_query_from_url
from app.crawl.orchestrator import harvest_for_page, _flatten_scrape_links, _should_retry_with_playwright
from app.crawl.playwright_harvest import harvest_with_playwright
from app.crawl.types import HarvestResult
from app.crawl.un_careers import filter_config_from_url
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


def test_egp_shell_guard_text_triggers_playwright_retry():
    url = "https://production.egp.gov.et/egp/bids/all"
    shell = (
        "Inspect is not allowed in this application. "
        "Developer tools are not permitted on this application for security reasons. "
        "Please close the browser developer tools, then click Go Back to continue."
    )
    assert _should_retry_with_playwright(url, shell, []) is True


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


def test_un_careers_filter_config_from_filtered_url():
    url = (
        "https://careers.un.org/jobopening?"
        "data=%257B%2522ds%2522%253A%255B%2522ADDISABABA%2522%252C%2522NAIROBI%2522%255D%252C"
        "%2522jc%2522%253A%255B%2522CON%2522%255D%257D&language=en"
    )

    cfg = filter_config_from_url(url)

    assert cfg["ds"] == ["ADDISABABA", "NAIROBI"]
    assert cfg["jc"] == ["CON"]
    assert cfg["aoe"] == []


@patch("app.crawl.un_careers.httpx.AsyncClient")
def test_harvest_un_careers_api_success(mock_client_cls):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "status": 1,
                "data": {
                    "count": 1,
                    "list": [
                        {
                            "jobId": 278501,
                            "postingTitle": "Monitoring and Evaluation Specialist",
                            "startDate": "2026-06-04T04:00:00.000Z",
                            "endDate": "2026-06-12T03:59:59.000Z",
                            "dept": {"name": "United Nations Human Settlements Programme"},
                            "jc": {"name": "Consultants"},
                            "dutyStation": [{"description": "NAIROBI"}],
                            "jobDescription": "<div>Result of Service: baseline report</div>",
                        }
                    ],
                },
            }

    client = MagicMock()
    client.post = AsyncMock(return_value=FakeResponse())
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    mock_client_cls.return_value = client

    page = _page(url="https://careers.un.org/jobopening", crawl_strategy="un_careers")
    r = asyncio.run(harvest_for_page(page))

    assert r.status == "success"
    assert "Monitoring and Evaluation Specialist" in r.markdown
    assert r.detail_urls == ["https://careers.un.org/jobSearchDescription/278501?language=en"]
    assert r.session_meta["strategy"] == "un_careers"
    assert r.session_meta["listing_rows_v1"][0]["deadline"] == "2026-06-12"


def test_eu_funding_filter_query_from_url():
    url = (
        "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/"
        "calls-for-tenders?order=DESC&pageNumber=1&pageSize=50&sortBy=startDate"
        "&status=31094502,31094501&geographicalZones=31085111"
    )

    query, sort, page_size, page_number = filter_query_from_url(url)

    assert {"terms": {"type": ["0"]}} in query["bool"]["must"]
    assert {"terms": {"status": ["31094502", "31094501"]}} in query["bool"]["must"]
    assert {"terms": {"geographicalZones": ["31085111"]}} in query["bool"]["must"]
    assert sort == {"order": "DESC", "field": "startDate"}
    assert page_size == 50
    assert page_number == 1


@patch("app.crawl.eu_funding.httpx.AsyncClient")
def test_harvest_eu_funding_api_success(mock_client_cls):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "totalResults": 1,
                "results": [
                    {
                        "reference": "98a56ee5-bec7-4944-9589-373d609cf350-CN",
                        "summary": "AAP2022 Support Measures Regional MIP Sub-Saharan Africa",
                        "metadata": {
                            "title": ["AAP2022 Support Measures Regional MIP Sub-Saharan Africa"],
                            "cftId": ["98a56ee5-bec7-4944-9589-373d609cf350-CN"],
                            "callIdentifier": ["EC-INTPA/JIB/2026/EA-RP/0070"],
                            "status": ["31094502"],
                            "contractType": ["31095498"],
                            "startDate": ["2026-05-18T00:00:00.000+0000"],
                            "deadlineDate": ["2026-06-17T00:00:59.000+0000"],
                            "geographicalZones": ["31085111"],
                            "description": ["Strengthen IGAD institutional effectiveness."],
                        },
                    }
                ],
            }

    client = MagicMock()
    client.post = AsyncMock(return_value=FakeResponse())
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    mock_client_cls.return_value = client

    page = _page(
        url=(
            "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/"
            "calls-for-tenders?status=31094502,31094501&geographicalZones=31085111"
        ),
        crawl_strategy="eu_funding",
    )
    r = asyncio.run(harvest_for_page(page))

    assert r.status == "success"
    assert "AAP2022 Support Measures" in r.markdown
    assert r.detail_urls == [
        "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/"
        "tender-details/98a56ee5-bec7-4944-9589-373d609cf350-CN"
    ]
    assert r.session_meta["strategy"] == "eu_funding"
    assert r.session_meta["listing_rows_v1"][0]["deadline"] == "2026-06-17"


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
