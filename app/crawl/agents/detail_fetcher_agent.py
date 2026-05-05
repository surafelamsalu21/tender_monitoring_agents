"""
Optional per-detail-page fetch (stub until Phase C).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Tuple

if TYPE_CHECKING:
    from app.models.page import MonitoredPage

logger = logging.getLogger(__name__)


class DetailFetcherAgent:
    """Fetches additional markdown for individual tender URLs (implementation pending)."""

    async def fetch_details(
        self,
        page: MonitoredPage,
        detail_urls: List[str],
        session_context: object | None = None,
    ) -> List[Tuple[str, str]]:
        """Return list of (url, markdown) pairs."""
        logger.debug(
            "DetailFetcherAgent.fetch_details not implemented (page_id=%s)",
            getattr(page, "id", None),
        )
        return []
