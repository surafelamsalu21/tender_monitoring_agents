"""UN Careers public API harvest helpers."""
from __future__ import annotations

import html
import json
import logging
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from app.crawl.types import HarvestResult
from app.models.page import MonitoredPage

logger = logging.getLogger(__name__)

_API_URL = "https://careers.un.org/api/public/opening/jo/list/filteredV2/en"
_DETAIL_URL = "https://careers.un.org/jobSearchDescription/{job_id}?language=en"
_DEFAULT_ITEM_PER_PAGE = 50
_MAX_PAGES = 10
_MIN_PAGE_ATTEMPTS = 2


def _default_filter_config() -> dict[str, list[str]]:
    return {
        "aoe": [],
        "aoi": [],
        "el": [],
        "ct": [],
        "ds": ["ADDISABABA", "ASMARA", "CAIRO", "NAIROBI", "KAMPALA", "KIGALI"],
        "jn": [],
        "jf": [],
        "jc": ["CON"],
        "jle": [],
        "dept": [],
        "span": [],
    }


def filter_config_from_url(url: str) -> dict[str, list[str]]:
    """
    Extract the Angular `data=` filter payload from a UN Careers filtered URL.

    The value is commonly encoded twice, e.g. `%257B%2522jc%2522...`, so the
    parser progressively decodes before falling back to the default CON filter.
    """
    parsed = urlparse(url or "")
    raw_values = parse_qs(parsed.query).get("data") or []
    if not raw_values:
        return _default_filter_config()

    raw = raw_values[0]
    candidates = [raw]
    for _ in range(3):
        decoded = unquote(candidates[-1])
        if decoded == candidates[-1]:
            break
        candidates.append(decoded)

    for candidate in reversed(candidates):
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            cfg = _default_filter_config()
            for key in cfg:
                value = payload.get(key)
                cfg[key] = [str(v).strip() for v in value if str(v).strip()] if isinstance(value, list) else []
            return cfg

    logger.warning("UN Careers: could not decode filter data from %s", url)
    return _default_filter_config()


def _iso_date(value: Any) -> str | None:
    if not value:
        return None
    raw = str(value).strip()
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return raw[:10] if len(raw) >= 10 else raw


def _plain_text_from_html(value: Any, *, limit: int = 900) -> str:
    text = html.unescape(str(value or ""))
    soup = BeautifulSoup(text, "html.parser")
    plain = " ".join(soup.get_text(" ", strip=True).split())
    return plain[:limit].strip()


def _duty_stations(row: dict[str, Any]) -> list[str]:
    stations = row.get("dutyStation") or []
    if not isinstance(stations, list):
        return []
    out: list[str] = []
    for station in stations:
        if not isinstance(station, dict):
            continue
        name = str(station.get("description") or "").strip()
        if name:
            out.append(name)
    return out


def _row_to_listing(row: dict[str, Any]) -> dict[str, Any] | None:
    job_id = row.get("jobId")
    title = str(row.get("postingTitle") or row.get("jobTitle") or "").strip()
    if not job_id or not title:
        return None

    stations = _duty_stations(row)
    dept = row.get("dept") if isinstance(row.get("dept"), dict) else {}
    category = row.get("jc") if isinstance(row.get("jc"), dict) else {}
    detail_url = _DETAIL_URL.format(job_id=job_id)
    snippet_parts = [
        f"Source: {dept.get('name')}" if dept.get("name") else "Source: UN Careers",
        f"Type: {category.get('name')}" if category.get("name") else "Type: Consultants",
        f"Duty station: {', '.join(stations)}" if stations else "",
        _plain_text_from_html(row.get("jobDescription")),
    ]
    snippet = " | ".join(part for part in snippet_parts if part)

    return {
        "title": title,
        "reference": str(job_id),
        "publication_date": _iso_date(row.get("startDate")),
        "deadline": _iso_date(row.get("endDate")),
        "detail_url": detail_url,
        "country": ", ".join(stations) or None,
        "snippet": snippet,
        "raw": row,
    }


def _markdown_from_rows(rows: list[dict[str, Any]], source_url: str) -> str:
    lines = [
        "# UN Careers Consulting Opportunities",
        "",
        f"Source listing: {source_url}",
        "",
    ]
    for row in rows:
        lines.extend(
            [
                f"### Consultancy: {row['title']}",
                f"- Reference: {row.get('reference') or ''}",
                f"- Detail URL: [{row['detail_url']}]({row['detail_url']})",
                f"- Publication date: {row.get('publication_date') or ''}",
                f"- Application deadline: {row.get('deadline') or ''}",
                f"- Duty station: {row.get('country') or ''}",
                f"- Summary: {row.get('snippet') or ''}",
                "",
            ]
        )
    return "\n".join(lines).strip()


async def harvest_un_careers(page: MonitoredPage) -> HarvestResult:
    """Fetch filtered UN Careers consultant opportunities via the public JSON API."""
    source_url = str(page.url)
    filter_config = filter_config_from_url(source_url)
    all_rows: list[dict[str, Any]] = []
    detail_urls: list[str] = []
    pages_fetched = 0
    pages_budget = max(_MIN_PAGE_ATTEMPTS, _MAX_PAGES)

    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        timeout=30.0,
        follow_redirects=True,
    ) as client:
        for page_index in range(pages_budget):
            payload = {
                "filterConfig": filter_config,
                "pagination": {
                    "page": page_index,
                    "itemPerPage": _DEFAULT_ITEM_PER_PAGE,
                    "sortBy": "startDate",
                    "sortDirection": -1,
                },
            }
            response = await client.post(_API_URL, json=payload)
            response.raise_for_status()
            body = response.json()
            pages_fetched += 1
            data = body.get("data") if isinstance(body, dict) else {}
            items = data.get("list") if isinstance(data, dict) else []
            if not isinstance(items, list) or not items:
                break

            for item in items:
                if not isinstance(item, dict):
                    continue
                listing = _row_to_listing(item)
                if listing:
                    all_rows.append(listing)
                    detail_urls.append(str(listing["detail_url"]))

            total_count = int(data.get("count") or data.get("totalCount") or 0) if isinstance(data, dict) else 0
            if total_count and len(all_rows) >= total_count and pages_fetched >= _MIN_PAGE_ATTEMPTS:
                break
            if len(items) < _DEFAULT_ITEM_PER_PAGE and pages_fetched >= _MIN_PAGE_ATTEMPTS:
                break

    markdown = _markdown_from_rows(all_rows, source_url)
    logger.info("UN Careers harvest: %s row(s) from %s", len(all_rows), source_url)
    return HarvestResult(
        status="success",
        page_url=source_url,
        markdown=markdown,
        html=None,
        listing_urls=detail_urls,
        detail_urls=detail_urls,
        session_meta={
            "strategy": "un_careers",
            "title": "UN Careers Consulting Opportunities",
            "source_api": _API_URL,
            "structured_source": True,
            "filter_config": filter_config,
            "listing_rows_v1": [
                {key: value for key, value in row.items() if key != "raw"} for row in all_rows
            ],
            "raw_count": len(all_rows),
            "max_pages": pages_budget,
            "pages_attempted": pages_fetched,
            "min_page_attempts": _MIN_PAGE_ATTEMPTS,
        },
    )
