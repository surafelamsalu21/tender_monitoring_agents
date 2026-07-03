"""World Bank procurement API helpers: consulting pre-filter and structured rows."""
from __future__ import annotations

import re
from typing import Any

_WB_DETAIL_URL = (
    "https://projects.worldbank.org/en/projects-operations/procurement-detail/{notice_id}"
)

_WB_BLOCKED_NOTICE_TYPES = (
    "contract award",
    "goods and works award",
    "small contracts award",
)

_WB_BLOCKED_PROCUREMENT_GROUPS = frozenset({"GO", "CW"})

_WB_CONSULTING_METHOD_TOKENS = (
    "individual consultant",
    "quality and cost-based",
    "quality based selection",
    "consultant qualification",
    "request for proposals",
    "fixed budget selection",
    "least cost selection",
)

_WB_CONSULTING_NOTICE_TYPES = (
    "request for expression of interest",
    "invitation for prequalification",
    "general procurement notice",
)


def worldbank_notice_detail_url(notice_id: str) -> str:
    return _WB_DETAIL_URL.format(notice_id=(notice_id or "").strip())


def worldbank_notice_passes_consulting_prefilter(notice: dict[str, Any]) -> bool:
    """
    Conservative consulting-only filter for scoped World Bank harvests.

    Drops contract awards, goods (GO), and works (CW). Keeps consultant services
    and consulting-selection methods on open notice types.
    """
    if not isinstance(notice, dict):
        return False

    notice_type = str(notice.get("notice_type") or "").strip().lower()
    group = str(notice.get("procurement_group") or "").strip().upper()
    method = str(notice.get("procurement_method_name") or "").strip().lower()

    if any(blocked in notice_type for blocked in _WB_BLOCKED_NOTICE_TYPES):
        return False
    if group in _WB_BLOCKED_PROCUREMENT_GROUPS:
        return False
    if group == "CS":
        return True
    if any(token in method for token in _WB_CONSULTING_METHOD_TOKENS):
        if any(token in notice_type for token in _WB_CONSULTING_NOTICE_TYPES):
            return True
        if "invitation for bids" in notice_type and "consultant" in method:
            return True
    return False


def worldbank_notice_to_listing_row(notice: dict[str, Any]) -> dict[str, Any] | None:
    notice_id = str(notice.get("id") or "").strip()
    title = str(notice.get("bid_description") or notice.get("project_name") or notice_id).strip()
    if not title:
        return None

    country = str(notice.get("project_ctry_name") or "").strip()
    project = str(notice.get("project_name") or "").strip()
    project_id = str(notice.get("project_id") or "").strip()
    notice_type = str(notice.get("notice_type") or "").strip()
    notice_date = str(notice.get("noticedate") or "").strip()
    method = str(notice.get("procurement_method_name") or "").strip()
    reference = str(notice.get("bid_reference_no") or notice_id).strip()
    detail_url = worldbank_notice_detail_url(notice_id) if notice_id else None

    snippet_parts = [
        "Source: World Bank Procurement",
        f"Country: {country}" if country else "",
        f"Project: {project} ({project_id})" if project or project_id else "",
        f"Notice type: {notice_type}" if notice_type else "",
        f"Method: {method}" if method else "",
    ]
    snippet = " | ".join(part for part in snippet_parts if part)

    return {
        "title": title,
        "reference": reference or None,
        "publication_date": notice_date or None,
        "deadline": str(notice.get("submission_deadline_date") or "").strip()[:10] or None,
        "detail_url": detail_url,
        "country": country or None,
        "snippet": snippet,
    }


def parse_worldbank_api_markdown(markdown: str) -> list[dict[str, Any]]:
    """
    Deterministic parser for markdown emitted by ``_worldbank_api_harvest_sync``.

    Used when structured ``listing_rows_v1`` is unavailable (e.g. langgraph path).
    """
    md = markdown or ""
    if "World Bank procurement API harvest." not in md:
        return []

    rows: list[dict[str, Any]] = []
    blocks = re.split(r"\n(?=- )", md)
    for block in blocks:
        block = block.strip()
        if not block.startswith("- "):
            continue
        title_line = block.splitlines()[0][2:].strip()
        if not title_line or title_line.startswith("Country:"):
            continue

        fields: dict[str, str] = {}
        for line in block.splitlines()[1:]:
            line = line.strip()
            m = re.match(r"^-?\s*([^:]+):\s*(.+)$", line)
            if m:
                fields[m.group(1).strip().lower()] = m.group(2).strip()

        url = fields.get("link", "")
        if not url.startswith("http"):
            continue

        rows.append(
            {
                "title": title_line,
                "url": url,
                "date": fields.get("date", ""),
                "description": " | ".join(
                    part
                    for part in (
                        f"Country: {fields.get('country', '')}" if fields.get("country") else "",
                        f"Project: {fields.get('project', '')}" if fields.get("project") else "",
                        f"Notice type: {fields.get('notice type', '')}" if fields.get("notice type") else "",
                    )
                    if part
                ),
            }
        )
    return rows
