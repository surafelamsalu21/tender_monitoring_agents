"""
Attachment download pipeline (stub until Phase D).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from app.models.page import MonitoredPage

logger = logging.getLogger(__name__)


class AttachmentAgent:
    """Downloads tender attachments with an authenticated session (implementation pending)."""

    async def collect_attachments(
        self,
        page: MonitoredPage,
        session_context: object | None = None,
        source_urls: List[str] | None = None,
    ) -> list[dict]:
        logger.debug(
            "AttachmentAgent.collect_attachments not implemented (page_id=%s)",
            getattr(page, "id", None),
        )
        return []
