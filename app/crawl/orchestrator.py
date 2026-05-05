"""
Harvest orchestrator: crawl4ai today; Playwright/hybrid stubs.
"""
from __future__ import annotations

import logging
from typing import Any

from app.crawl.types import HarvestResult
from app.models.page import MonitoredPage

logger = logging.getLogger(__name__)


def _flatten_scrape_links(links: Any) -> list[str]:
    """Normalize crawl4ai `links` into unique href strings."""
    if not links:
        return []
    items: list[Any]
    if isinstance(links, dict):
        internal = links.get("internal") or []
        external = links.get("external") or []
        items = list(internal) + list(external)
    elif isinstance(links, list):
        items = links
    else:
        return []

    out: list[str] = []
    for item in items:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            href = item.get("href") or item.get("url")
            if href:
                out.append(str(href))
    return list(dict.fromkeys(out))


async def harvest_for_page(page: MonitoredPage) -> HarvestResult:
    """
    Run harvest for one monitored page per crawl_strategy.
    """
    url = page.url
    raw = (page.crawl_strategy or "crawl4ai").strip().lower()

    if raw == "crawl4ai":
        from app.services.scraper import TenderScraper

        async with TenderScraper() as scraper:
            scrape = await scraper.scrape_page(url)
        if scrape.get("status") != "success":
            return HarvestResult(
                status="failed",
                page_url=url,
                error=scrape.get("error") or "scrape failed",
                session_meta={"strategy": "crawl4ai"},
            )
        listing_urls = _flatten_scrape_links(scrape.get("links"))
        return HarvestResult(
            status="success",
            page_url=url,
            markdown=scrape.get("markdown") or "",
            html=scrape.get("html"),
            listing_urls=listing_urls,
            session_meta={
                "strategy": "crawl4ai",
                "word_count": scrape.get("word_count", 0),
                "char_count": scrape.get("char_count", 0),
            },
        )

    if raw in ("playwright", "hybrid"):
        from app.crawl.playwright_harvest import harvest_with_playwright

        # hybrid: same as playwright for now (login + listing in one browser session)
        return await harvest_with_playwright(page)

    return HarvestResult(
        status="failed",
        page_url=url,
        error=f"Unknown crawl_strategy: {raw!r}",
        session_meta={},
    )
