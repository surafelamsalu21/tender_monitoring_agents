"""
Playwright-backed session / login (stub until Phase C).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from app.models.page import MonitoredPage

logger = logging.getLogger(__name__)


class SessionAgent:
    """Authenticates and holds browser context for one harvest run (implementation pending)."""

    async def establish_session(self, page: MonitoredPage) -> Optional[Any]:
        """Return a Playwright context or handle; None when not implemented."""
        logger.debug(
            "SessionAgent.establish_session not implemented (page_id=%s)",
            getattr(page, "id", None),
        )
        return None
