"""
Listing pagination and markdown aggregation (stub until Phase C).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Tuple

if TYPE_CHECKING:
    from app.models.page import MonitoredPage

logger = logging.getLogger(__name__)


class ListingAgent:
    """Walks listing pages and collects markdown + URLs (implementation pending)."""

    async def collect_listings(
        self,
        page: MonitoredPage,
        session_context: object | None = None,
    ) -> Tuple[str, List[str]]:
        """Return (aggregated_markdown, discovered_detail_urls)."""
        logger.debug(
            "ListingAgent.collect_listings not implemented (page_id=%s)",
            getattr(page, "id", None),
        )
        return "", []
