"""Build :class:`CrawlArtifactV1` from harvest/scraper outputs (single source of truth)."""
from __future__ import annotations

from typing import Any, Mapping

from app.crawl.types import HarvestResult
from app.pipeline.schemas import CrawlArtifactV1


def crawl_artifact_from_harvest(h: HarvestResult) -> CrawlArtifactV1:
    """Map hybrid harvest result to the crawl artifact (no scraper imports in agents)."""
    md = h.markdown or ""
    meta = dict(h.session_meta or {})
    title = ""
    if isinstance(meta.get("title"), str):
        title = meta["title"]
    return CrawlArtifactV1(
        url=h.page_url,
        status=h.status,
        title=title,
        markdown=md,
        links=list(h.listing_urls or []),
        metadata=meta,
        word_count=len(md.split()) if md else 0,
        char_count=len(md),
    )


def crawl_artifact_from_scraper_dict(d: Mapping[str, Any]) -> CrawlArtifactV1:
    """
    Map ``TenderScraper.scrape_page`` / test-crawler API result dict to artifact.

    Expected keys: url, title, markdown, links, metadata, word_count, char_count, status.
    """
    url = str(d.get("url") or "")
    md = str(d.get("markdown") or "")
    links_raw = d.get("links")
    links = _normalize_links(links_raw)
    meta = d.get("metadata") if isinstance(d.get("metadata"), dict) else {}
    return CrawlArtifactV1(
        url=url,
        status=str(d.get("status") or "success"),
        title=str(d.get("title") or ""),
        markdown=md,
        links=links,
        metadata=dict(meta),
        word_count=int(d.get("word_count") or (len(md.split()) if md else 0)),
        char_count=int(d.get("char_count") or len(md)),
    )


def _normalize_links(links_raw: Any) -> list[str]:
    if not links_raw:
        return []
    if isinstance(links_raw, list):
        out: list[str] = []
        for item in links_raw:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            elif isinstance(item, dict):
                href = item.get("href") or item.get("url")
                if href:
                    out.append(str(href).strip())
        return list(dict.fromkeys(out))
    if isinstance(links_raw, dict):
        internal = links_raw.get("internal") or []
        external = links_raw.get("external") or []
        return _normalize_links(list(internal) + list(external))
    return []
