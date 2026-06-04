"""EU Funding & Tenders Portal public search API harvest helpers."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from app.crawl.types import HarvestResult
from app.models.page import MonitoredPage

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
_API_KEY = "SEDIA"
_DETAIL_URL = (
    "https://ec.europa.eu/info/funding-tenders/opportunities/portal/"
    "screen/opportunities/tender-details/{cft_id}"
)
_DEFAULT_PAGE_SIZE = 50
_MAX_PAGES = 10


def _first(metadata: dict[str, Any], key: str) -> Any:
    value = metadata.get(key)
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _date_only(value: Any) -> str | None:
    if not value:
        return None
    raw = str(value).strip()
    try:
        if raw.endswith("+0000"):
            raw = raw[:-5] + "+00:00"
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return raw[:10] if len(raw) >= 10 else raw


def _list_param(params: dict[str, list[str]], key: str) -> list[str]:
    raw = (params.get(key) or [""])[0]
    return [item.strip() for item in raw.split(",") if item.strip()]


def filter_query_from_url(url: str) -> tuple[dict[str, Any], dict[str, Any], int, int]:
    """Build the portal corporate-search query from a filtered EU portal URL."""
    parsed = urlparse(url or "")
    params = parse_qs(parsed.query)
    status = _list_param(params, "status") or ["31094501", "31094502", "31094503"]
    zones = _list_param(params, "geographicalZones")

    must: list[dict[str, Any]] = [
        {"terms": {"type": ["0"]}},  # Calls for tenders
        {"terms": {"status": status}},
    ]
    if zones:
        must.append({"terms": {"geographicalZones": zones}})

    page_size = int((params.get("pageSize") or [_DEFAULT_PAGE_SIZE])[0] or _DEFAULT_PAGE_SIZE)
    page_number = int((params.get("pageNumber") or [1])[0] or 1)
    sort = {
        "order": (params.get("order") or ["DESC"])[0],
        "field": (params.get("sortBy") or ["startDate"])[0],
    }
    return {"bool": {"must": must}}, sort, page_size, page_number


async def _search_eu_tenders(
    client: httpx.AsyncClient,
    query: dict[str, Any],
    sort: dict[str, Any],
    *,
    page_size: int,
    page_number: int,
) -> dict[str, Any]:
    files = {
        "query": ("query", json.dumps(query), "application/json"),
        "sort": ("sort", json.dumps(sort), "application/json"),
        "languages": ("languages", json.dumps(["en"]), "application/json"),
    }
    response = await client.post(
        _SEARCH_URL,
        params={
            "apiKey": _API_KEY,
            "text": "***",
            "pageSize": page_size,
            "pageNumber": page_number,
        },
        files=files,
    )
    response.raise_for_status()
    body = response.json()
    return body if isinstance(body, dict) else {}


def _result_to_listing(result: dict[str, Any]) -> dict[str, Any] | None:
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    cft_id = _first(metadata, "cftId") or result.get("reference")
    title = _first(metadata, "title") or result.get("summary") or result.get("content")
    if not cft_id or not title:
        return None

    detail_url = _DETAIL_URL.format(cft_id=str(cft_id).strip())
    reference = _first(metadata, "callIdentifier") or str(cft_id)
    description = _first(metadata, "description") or result.get("summary") or ""
    contract_type = _first(metadata, "contractType")
    status = _first(metadata, "status")
    zones = metadata.get("geographicalZones") or []
    if not isinstance(zones, list):
        zones = [zones]
    geography_label = (
        "Sub-Saharan Africa, including East Africa countries"
        if "31085111" in [str(z) for z in zones]
        else ""
    )
    snippet = " | ".join(
        part
        for part in (
            "Source: EU Funding & Tenders Portal",
            f"Reference: {reference}",
            f"Status: {status}" if status else "",
            f"Contract type: {contract_type}" if contract_type else "",
            f"Geographical focus: {geography_label}" if geography_label else "",
            f"Geographical zones: {', '.join(str(z) for z in zones if z)}" if zones else "",
            str(description).strip(),
        )
        if part
    )

    return {
        "title": str(title).strip(),
        "reference": str(reference).strip(),
        "publication_date": _date_only(_first(metadata, "startDate")),
        "deadline": _date_only(_first(metadata, "deadlineDate") or _first(metadata, "twoStageDeadlineDate")),
        "detail_url": detail_url,
        "country": geography_label or None,
        "snippet": snippet,
        "raw": result,
    }


def _markdown_from_rows(rows: list[dict[str, Any]], source_url: str) -> str:
    lines = ["# EU Funding & Tenders Calls for Tenders", "", f"Source listing: {source_url}", ""]
    for row in rows:
        lines.extend(
            [
                f"### EU Tender: {row['title']}",
                f"- Reference: {row.get('reference') or ''}",
                f"- Detail URL: [{row['detail_url']}]({row['detail_url']})",
                f"- Publication date: {row.get('publication_date') or ''}",
                f"- Deadline: {row.get('deadline') or ''}",
                f"- Geography: {row.get('country') or ''}",
                f"- Summary: {row.get('snippet') or ''}",
                "",
            ]
        )
    return "\n".join(lines).strip()


async def harvest_eu_funding(page: MonitoredPage) -> HarvestResult:
    """Fetch filtered EU Funding & Tenders calls via the public corporate search API."""
    source_url = str(page.url)
    base_query, sort, page_size, first_page = filter_query_from_url(source_url)
    page_size = max(1, min(page_size, 100))
    rows: list[dict[str, Any]] = []
    detail_urls: list[str] = []

    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        timeout=30.0,
        follow_redirects=True,
    ) as client:
        for offset in range(_MAX_PAGES):
            body = await _search_eu_tenders(
                client,
                base_query,
                sort,
                page_size=page_size,
                page_number=first_page + offset,
            )
            results = body.get("results") if isinstance(body.get("results"), list) else []
            if not results:
                break
            for result in results:
                if not isinstance(result, dict):
                    continue
                listing = _result_to_listing(result)
                if listing:
                    rows.append(listing)
                    detail_urls.append(str(listing["detail_url"]))

            total = int(body.get("totalResults") or 0)
            if total and len(rows) >= total:
                break
            if len(results) < page_size:
                break

    markdown = _markdown_from_rows(rows, source_url)
    logger.info("EU Funding harvest: %s row(s) from %s", len(rows), source_url)
    return HarvestResult(
        status="success",
        page_url=source_url,
        markdown=markdown,
        listing_urls=detail_urls,
        detail_urls=detail_urls,
        session_meta={
            "strategy": "eu_funding",
            "title": "EU Funding & Tenders Calls for Tenders",
            "source_api": _SEARCH_URL,
            "structured_source": True,
            "filter_query": base_query,
            "listing_rows_v1": [
                {key: value for key, value in row.items() if key != "raw"} for row in rows
            ],
            "raw_count": len(rows),
        },
    )
