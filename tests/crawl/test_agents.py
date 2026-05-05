import asyncio

from app.crawl.agents.attachment_agent import AttachmentAgent
from app.crawl.agents.detail_fetcher_agent import DetailFetcherAgent
from app.crawl.agents.listing_agent import ListingAgent
from app.crawl.agents.session_agent import SessionAgent
from app.models.page import MonitoredPage


def _sample_page():
    return MonitoredPage(
        name="Fixture",
        url="https://example.com",
        crawl_frequency_hours=3,
        crawl_strategy="crawl4ai",
    )


def test_session_agent_establish_session_returns_none():
    agent = SessionAgent()
    p = _sample_page()
    assert asyncio.run(agent.establish_session(p)) is None


def test_listing_agent_returns_empty():
    agent = ListingAgent()
    p = _sample_page()
    md, urls = asyncio.run(agent.collect_listings(p, None))
    assert md == ""
    assert urls == []


def test_attachment_agent_returns_empty():
    agent = AttachmentAgent()
    p = _sample_page()
    assert asyncio.run(agent.collect_attachments(p, None, [])) == []


def test_detail_fetcher_returns_empty():
    agent = DetailFetcherAgent()
    p = _sample_page()
    assert asyncio.run(agent.fetch_details(p, ["https://x"], None)) == []
