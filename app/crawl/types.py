"""
Shared types for the hybrid harvest layer (crawl4ai + Playwright).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Literal, Optional

CrawlStrategy = Literal["crawl4ai", "playwright", "hybrid"]


@dataclass
class HarvestResult:
    """Normalized harvest output for TenderAgent.process_page and CrawlLog diagnostics."""

    status: Literal["success", "failed"]
    page_url: str
    markdown: str = ""
    error: Optional[str] = None
    html: Optional[str] = None
    listing_urls: List[str] = field(default_factory=list)
    detail_urls: List[str] = field(default_factory=list)
    attachments: List[dict[str, Any]] = field(default_factory=list)
    session_meta: dict[str, Any] = field(default_factory=dict)
