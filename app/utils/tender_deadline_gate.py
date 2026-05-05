"""
Post–Agent 1 deadline gate: drop opportunities that are clearly closed by listing or parsed dates.

Designed for portals like Shelter Afrique where each notice links to a PDF but the markdown
often still contains a pipe table row with Publication / Closing columns.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_CLOSED_WORD = re.compile(r"^\s*closed\s*$", re.I)
_DATE_DD_MM_YYYY = re.compile(r"^(\d{1,2})[\-/](\d{1,2})[\-/](\d{4})\s*$")
_DATE_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_INLINE_DDMMYYYY = re.compile(r"\b(\d{2}-\d{2}-\d{4})\b")


def _split_table_row_cells(line: str) -> List[str]:
    raw = [p.strip() for p in line.strip().split("|")]
    return [x for x in raw if x]


def infer_listing_closing_raw(page_markdown: str, tender_url: str) -> Optional[str]:
    """
    Best-effort closing hint where the tender PDF appears in full listing markdown:

    - Pipe table: ``| ...PDF... | Publication | Closing |`` → last cell
    - Same line contains URL plus **≥2** ``DD-MM-YYYY`` spans → assume last is closing (Shelter-style)
    - Trailing segment after URL contains literal ``Closed`` → treat as closed
    """
    if not page_markdown or not tender_url:
        return None
    url = tender_url.strip()
    if url not in page_markdown:
        return None

    for ln in page_markdown.splitlines():
        if url not in ln:
            continue

        if "|" in ln:
            cells = _split_table_row_cells(ln)
            if len(cells) >= 3:
                return cells[-1]

        dates = _INLINE_DDMMYYYY.findall(ln)
        if len(dates) >= 2:
            return dates[-1]

        tail = ln.split(url, 1)[-1]
        if _CLOSED_WORD.match(tail.strip()):
            return "Closed"
        if re.search(r"\|\s*[Cc]losed\s*\|?", tail):
            return "Closed"
        if re.search(r"\b[Cc]losed\b\s*$", tail.strip()):
            return "Closed"
    return None


def extract_listing_closing_cell(page_markdown: str, tender_url: str) -> Optional[str]:
    """Backward-compatible wrapper for infer_listing_closing_raw."""
    return infer_listing_closing_raw(page_markdown, tender_url)


def parse_date_flexible(value: Optional[str]) -> Optional[date]:
    """ISO YYYY-MM-DD first, then day-first DD-MM-YYYY / DD/MM/YYYY."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None

    iso_m = _DATE_ISO.match(s[:10])
    if iso_m:
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").date()
        except ValueError:
            pass

    dm = _DATE_DD_MM_YYYY.match(s)
    if dm:
        d, mo, y = int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
        try:
            return date(y, mo, d)
        except ValueError:
            return None

    for fmt in ("%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _closing_signals_expired(cell: Optional[str]) -> bool:
    if not cell:
        return False
    return bool(_CLOSED_WORD.match(cell.strip()))


def _deadline_for_item(
    item: Dict[str, Any],
    page_markdown: str,
) -> Tuple[str, Optional[date], bool]:
    """
    Returns (source, parsed_deadline_or_none, closed_keyword).

    closed_keyword True when listing cell is literally "Closed".
    """
    url = (item.get("url") or "").strip()
    step3 = (item.get("screening") or {}).get("step3") or {}
    model_deadline = parse_date_flexible(step3.get("deadline"))

    listing_cell = infer_listing_closing_raw(page_markdown, url)
    if _closing_signals_expired(listing_cell):
        return ("listing_closed_keyword", None, True)

    listing_date = parse_date_flexible(listing_cell) if listing_cell else None
    if listing_date is not None:
        return ("listing_date", listing_date, False)

    if model_deadline is not None:
        return ("model_deadline", model_deadline, False)

    return ("unknown", None, False)


def filter_expired_agent1_items(
    items: List[Dict[str, Any]],
    page_markdown: str,
    reference: Optional[date] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Drop items past closing when we can infer it from (1) listing table closing cell,
    or (2) Agent 1 step3.deadline. Unknown → keep (conservative).

    Returns (kept, dropped_count).
    """
    ref = reference or datetime.utcnow().date()
    kept: List[Dict[str, Any]] = []
    dropped = 0

    for item in items:
        source, d, closed_kw = _deadline_for_item(item, page_markdown)

        if closed_kw:
            logger.info(
                "Expiry gate: drop (listing Closed) title=%s",
                (item.get("title") or "")[:60],
            )
            dropped += 1
            continue

        if d is None:
            kept.append(item)
            continue

        if d < ref:
            logger.info(
                "Expiry gate: drop deadline=%s (source=%s) title=%s",
                d.isoformat(),
                source,
                (item.get("title") or "")[:60],
            )
            dropped += 1
            continue

        kept.append(item)

    return kept, dropped
