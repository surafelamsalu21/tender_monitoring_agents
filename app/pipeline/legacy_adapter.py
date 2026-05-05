"""Map structured listing rows to legacy tender dicts expected by Agent 2 / repositories."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

from app.pipeline.schemas import ListingRowV1


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
) -> list[dict[str, Any]]:
    """Convert Agent 1 structural output into the dict shape used downstream."""
    tenders: list[dict[str, Any]] = []
    for row in rows:
        title = (row.title or "").strip()
        if not title:
            continue
        detail = _absolute_url(page_url, row.detail_url) or page_url
        deadline_norm = _normalize_deadline(row.deadline)
        pub_norm = _normalize_deadline(row.publication_date)

        step3: dict[str, Any] = {
            "title": title,
            "source": "",
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
        tenders.append(
            {
                "title": title,
                "url": detail,
                "date": deadline_norm or pub_norm,
                "description": description.strip(),
                "screening": screening,
                "date_status": "unknown",
                "reference": reference or None,
            }
        )
    return tenders
