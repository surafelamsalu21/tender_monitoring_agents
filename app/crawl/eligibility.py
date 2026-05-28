"""
Per-page crawl eligibility (crawl_frequency_hours vs last_crawled).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from app.models.page import MonitoredPage


def is_monitored_page_due_for_crawl(
    page: MonitoredPage,
    now: datetime | None = None,
) -> bool:
    """
    True if this page should run in a scheduled extraction tick (not manual force).
    Never crawled => due. Otherwise require >= crawl_frequency_hours since last_crawled.
    """
    now = now or datetime.utcnow()
    if page.last_crawled is None:
        return True
    freq_hours = page.crawl_frequency_hours or settings.CRAWL_INTERVAL_HOURS
    freq_hours = max(1, int(freq_hours))
    delta = now - page.last_crawled
    return delta >= timedelta(hours=freq_hours)
