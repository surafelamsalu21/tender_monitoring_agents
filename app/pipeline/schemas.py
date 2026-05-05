"""Pydantic contracts for the simple pipeline (versioned, traceable)."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class CrawlArtifactV1(BaseModel):
    """
    Normalized crawl payload — same information shape as ``POST /system/test-crawler`` success body.

    Agents consume this model only; they do not import scraper implementations.
    """

    version: str = Field(default="1", description="Artifact schema version")
    url: str
    status: str = Field(default="success")
    title: str = ""
    markdown: str = ""
    links: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    word_count: int = 0
    char_count: int = 0


class ListingRowV1(BaseModel):
    """One row from Agent 1 (structure only — no screening logic)."""

    title: str
    reference: Optional[str] = None
    publication_date: Optional[str] = None
    deadline: Optional[str] = None
    detail_url: Optional[str] = None
    country: Optional[str] = None
    snippet: Optional[str] = None
