"""
Harvest orchestrator: crawl4ai today; Playwright/hybrid stubs.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from app.crawl.types import HarvestResult
from app.models.page import MonitoredPage

logger = logging.getLogger(__name__)

_PLAYWRIGHT_SHELL_FALLBACK_HOSTS = {
    "egp.gov.et",
    "www.egp.gov.et",
    "production.egp.gov.et",
    "www.production.egp.gov.et",
}


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


def _host_for_url(url: str) -> str:
    return (urlparse(url or "").netloc or "").lower()


def _is_shell_capture(markdown: str, listing_urls: list[str]) -> bool:
    """
    Heuristic: some JS-heavy pages look successful to crawl4ai but only return
    a tiny shell (very small markdown and no links).

    Applies to any host. Restricting this to a hardcoded allowlist meant a new
    JS-rendered portal silently reported a successful crawl with no content,
    which is indistinguishable from "no opportunities this week".
    """
    text = (markdown or "").strip()
    low = text.lower()

    # Anti-bot / devtools guard pages can exceed the length threshold while still
    # containing no listing content.
    blocked_markers = (
        "inspect is not allowed",
        "developer tools are not permitted",
        "close devtools",
        "inspect close devtools required",
        "enable javascript",
        "javascript is required",
        "please enable js",
        "checking your browser",
        "verify you are human",
    )
    if any(marker in low for marker in blocked_markers):
        return True

    if len(listing_urls or []) > 0:
        return False

    return len(text) < 500


def _should_retry_with_playwright(url: str, markdown: str, listing_urls: list[str]) -> bool:
    """Whether a crawl4ai capture is weak enough to justify a Playwright retry."""
    if not _is_shell_capture(markdown, listing_urls):
        return False
    # Hosts known to need a browser are always retried; everything else is
    # retried too, but the known set is kept for logging clarity.
    host = _host_for_url(url)
    if host in _PLAYWRIGHT_SHELL_FALLBACK_HOSTS:
        logger.info("crawl4ai shell capture on known JS-heavy host %s", host)
    return True


async def harvest_for_page(page: MonitoredPage) -> HarvestResult:
    """
    Run harvest for one monitored page per crawl_strategy.
    """
    url = page.url
    raw = (page.crawl_strategy or "crawl4ai").strip().lower()

    if raw == "un_careers":
        from app.crawl.un_careers import harvest_un_careers

        return await harvest_un_careers(page)

    if raw == "eu_funding":
        from app.crawl.eu_funding import harvest_eu_funding

        return await harvest_eu_funding(page)

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
        markdown = scrape.get("markdown") or ""
        if _should_retry_with_playwright(url, markdown, listing_urls):
            from app.crawl.playwright_harvest import harvest_with_playwright

            logger.info(
                "crawl4ai returned shell-like capture for %s (chars=%s, links=%s); trying Playwright fallback.",
                url,
                len(markdown),
                len(listing_urls),
            )
            playwright_result = await harvest_with_playwright(page)
            if playwright_result.status == "success":
                meta = dict(playwright_result.session_meta or {})
                meta["fallback_from"] = "crawl4ai_shell_capture"
                playwright_result.session_meta = meta
                return playwright_result
            logger.warning(
                "Playwright fallback failed for %s: %s; keeping crawl4ai capture.",
                url,
                playwright_result.error,
            )

        shell_capture = _is_shell_capture(markdown, listing_urls)
        if shell_capture and len((markdown or "").strip()) < 200:
            # An all-but-empty capture reported as success is indistinguishable
            # from a genuinely quiet week. Fail it so the crawl log records the
            # reason and the page's consecutive_failures counter moves.
            return HarvestResult(
                status="failed",
                page_url=url,
                error=(
                    f"Empty capture after crawl4ai and Playwright "
                    f"({len((markdown or '').strip())} chars, {len(listing_urls)} links)"
                ),
                session_meta={"strategy": "crawl4ai", "shell_capture": True},
            )
        if shell_capture:
            logger.warning(
                "Harvest for %s looks shell-like (%s chars, %s links) — downstream yield may be zero.",
                url,
                len((markdown or "").strip()),
                len(listing_urls),
            )

        return HarvestResult(
            status="success",
            page_url=url,
            markdown=markdown,
            html=scrape.get("html"),
            listing_urls=listing_urls,
            session_meta={
                "strategy": "crawl4ai",
                "word_count": scrape.get("word_count", 0),
                "char_count": scrape.get("char_count", 0) or len(markdown),
                "pages_attempted": 1,
                "max_pages": 1,
                "shell_capture": shell_capture,
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
