"""Hybrid harvest package (crawl4ai + future Playwright).

Avoid importing `orchestrator` at package import time so tests can import
`app.crawl.agents` without requiring crawl4ai.
"""
from app.crawl.eligibility import is_monitored_page_due_for_crawl
from app.crawl.types import CrawlStrategy, HarvestResult

__all__ = [
    "HarvestResult",
    "CrawlStrategy",
    "is_monitored_page_due_for_crawl",
    "harvest_for_page",
]


def __getattr__(name: str):
    if name == "harvest_for_page":
        from app.crawl.orchestrator import harvest_for_page as _harvest_for_page

        return _harvest_for_page
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
