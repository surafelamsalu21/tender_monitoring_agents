"""Map structured listing rows to legacy tender dicts expected by Agent 2 / repositories."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

from app.pipeline.schemas import ListingRowV1
from app.utils.url_grounding import is_url_grounded

logger = logging.getLogger(__name__)


def _normalize_deadline(raw: Optional[str]) -> Optional[str]:
    if not raw or not str(raw).strip():
        return None
    s = str(raw).strip()
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:20], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Loose: 30-Apr-2026 style with abbreviated month
    try:
        return datetime.strptime(s, "%d-%b-%Y").strftime("%Y-%m-%d")
    except ValueError:
        pass
    return None


def _absolute_url(base: str, candidate: Optional[str]) -> Optional[str]:
    if not candidate or not str(candidate).strip():
        return None
    c = str(candidate).strip()
    if c.startswith("#") or c.lower().startswith("javascript:"):
        return None
    if c.startswith("//"):
        c = "https:" + c
    if not c.startswith("http"):
        c = urljoin(base, c)
    if not urlparse(c).scheme.startswith("http"):
        return None
    return c


def listing_rows_to_tender_dicts(
    rows: list[ListingRowV1],
    page_url: str,
    source_url_index: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
    """Convert Agent 1 structural output into the dict shape used downstream.

    Pass ``source_url_index`` (see :mod:`app.utils.url_grounding`) for rows the LLM
    produced, so an invented ``detail_url`` falls back to the listing page instead
    of becoming a dead link in a notification. Rows from structured API sources
    carry real URLs and need no index.
    """
    tenders: list[dict[str, Any]] = []
    source = ""
    host = urlparse(page_url or "").netloc.lower()
    if "careers.un.org" in host:
        source = "UN Careers"
    elif "ec.europa.eu" in host and "funding-tenders" in (page_url or ""):
        source = "EU Funding & Tenders Portal"
    elif "worldbank.org" in host:
        source = "World Bank Procurement"
    for row in rows:
        title = (row.title or "").strip()
        if not title:
            continue
        detail = _absolute_url(page_url, row.detail_url) or page_url
        detail_unverified = False
        if source_url_index and not is_url_grounded(detail, source_url_index, page_url):
            logger.info(
                "legacy_adapter: detail URL absent from harvested page, using listing URL: "
                "%r (title=%r)",
                detail[:120],
                title[:60],
            )
            detail = page_url
            detail_unverified = True
        deadline_norm = _normalize_deadline(row.deadline)
        pub_norm = _normalize_deadline(row.publication_date)

        step3: dict[str, Any] = {
            "title": title,
            "source": source,
            "country": (row.country or "").strip(),
            "type": "other",
            "deadline": deadline_norm,
            "estimated_budget": None,
            "link": detail,
        }
        reference = (row.reference or "").strip()
        desc_parts = [p for p in (row.snippet, f"Reference: {reference}" if reference else "") if p]
        description = "\n".join(desc_parts) if desc_parts else (row.snippet or "")

        screening: dict[str, Any] = {
            "screening_version": "v2_simple",
            "unrelated_to_precise_scope": False,
            "step1": {
                "mission_alignment": True,
                "sector_relevance": True,
                "activity_fit": True,
                "geographic_fit": True,
                "eligibility_quick_check": True,
            },
            "yes_count": 3,
            "passes_filter": True,
            "step2": {"pipeline": "simple"},
            "step3": step3,
        }
        tender: dict[str, Any] = {
            "title": title,
            "url": detail,
            "date": deadline_norm or pub_norm,
            "description": description.strip(),
            "screening": screening,
            "date_status": "unknown",
            "reference": reference or None,
        }
        if detail_unverified:
            tender["detail_url_unverified"] = True
        tenders.append(tender)
    return tenders
