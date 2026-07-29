"""
Deadline gate for the notification boundary.

:mod:`app.utils.tender_deadline_gate` filters at extraction time, which is not
enough on its own: a tender saved on the 4th with a deadline on the 17th is
perfectly valid then, but if it sits unnotified — waiting on an Agent 2 retry, or
because a send failed — it is dead by the time the next digest goes out. The
fallback digest selects on ``is_notified == False`` alone, so a backlog that
unblocks weeks later is mailed out wholesale with every deadline in the past.

So expiry is re-checked here, against today, immediately before sending.

Unknown deadlines are kept, matching the extraction-time gate; a row with no
deadline at all is only dropped once its single known date is older than
``NOTIFY_MAX_STALE_DAYS``.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# Deadline strings reach this module from several places: ISO from the APIs,
# ``2026-06-16 00:00:00.000000`` from the detail table, and day-first or
# month-name forms from listing markdown.
_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%Y/%m/%d",
    "%d-%b-%Y",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d.%m.%Y",
)


def parse_deadline(value: Any) -> Optional[date]:
    """Parse a deadline from the shapes actually stored in this system."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "n/a", "not specified", "unknown"}:
        return None

    # ``2026-06-16 00:00:00.000000`` and ``2026-06-16T09:00:00Z`` both start with
    # a usable ISO date.
    head = text[:10]
    try:
        return datetime.strptime(head, "%Y-%m-%d").date()
    except ValueError:
        pass

    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _first_parseable(*values: Any) -> Optional[date]:
    for value in values:
        parsed = parse_deadline(value)
        if parsed is not None:
            return parsed
    return None


def deadline_from_detailed_info(detailed_info: Any) -> Optional[date]:
    """Deadline from an Agent 2 result dict."""
    if not isinstance(detailed_info, dict):
        return None
    return _first_parseable(
        detailed_info.get("deadline"),
        detailed_info.get("submission_deadline"),
    )


def resolve_tender_deadline(tender: Any, detailed: Any = None) -> tuple[Optional[date], str]:
    """
    Best-known deadline for a saved tender, plus where it came from.

    Order matters. The detail page is the most reliable source, then the listing
    row. ``Tender.tender_date`` is deliberately last and reported separately as
    ``"ambiguous_date"``: it is populated as ``step3.deadline or date``, so when
    the first two are missing it may well hold a *publication* date, and treating
    that as a deadline would drop live opportunities.
    """
    detailed_deadline = None
    if detailed is not None:
        detailed_deadline = _first_parseable(getattr(detailed, "deadline", None))
    if detailed_deadline is not None:
        return detailed_deadline, "detail_page"

    step3 = getattr(tender, "screening_step3", None)
    if isinstance(step3, dict):
        step3_deadline = _first_parseable(step3.get("deadline"))
        if step3_deadline is not None:
            return step3_deadline, "listing_row"

    ambiguous = _first_parseable(getattr(tender, "tender_date", None))
    if ambiguous is not None:
        return ambiguous, "ambiguous_date"

    return None, "unknown"


def is_tender_expired(
    tender: Any,
    detailed: Any = None,
    reference: Optional[date] = None,
) -> tuple[bool, str]:
    """
    Whether a saved tender is too old to notify, plus a human-readable reason.

    Returns ``(False, "")`` when the tender is still worth sending.
    """
    ref = reference or datetime.utcnow().date()
    deadline, source = resolve_tender_deadline(tender, detailed)

    if deadline is None:
        return False, ""

    if source == "ambiguous_date":
        # No real deadline anywhere. This date could be a publication date, so it
        # only justifies dropping the row once it is stale beyond any usefulness.
        max_stale = int(getattr(settings, "NOTIFY_MAX_STALE_DAYS", 90) or 90)
        age_days = (ref - deadline).days
        if age_days > max_stale:
            return True, f"no deadline found and only known date is {age_days} days old"
        return False, ""

    if deadline < ref:
        days_past = (ref - deadline).days
        return True, f"deadline {deadline.isoformat()} passed {days_past} day(s) ago"

    return False, ""


def partition_notifiable(
    tenders: list[Any],
    detailed_by_tender_id: Optional[dict[int, Any]] = None,
    reference: Optional[date] = None,
) -> tuple[list[Any], list[Any]]:
    """
    Split saved tenders into ``(open, expired)`` for the send path.

    Returns everything as open when ``NOTIFY_SKIP_EXPIRED`` is disabled, so the
    behaviour can be reverted with one setting.
    """
    if not getattr(settings, "NOTIFY_SKIP_EXPIRED", True):
        return list(tenders), []

    lookup = detailed_by_tender_id or {}
    open_rows: list[Any] = []
    expired_rows: list[Any] = []

    for tender in tenders:
        detailed = lookup.get(getattr(tender, "id", None))
        if detailed is None:
            detailed = getattr(tender, "detailed_tender", None)
        expired, reason = is_tender_expired(tender, detailed, reference)
        if expired:
            expired_rows.append(tender)
            logger.info(
                "Notification expiry gate: suppressing tender id=%s (%s) — %s",
                getattr(tender, "id", "?"),
                (getattr(tender, "title", "") or "")[:60],
                reason,
            )
        else:
            open_rows.append(tender)

    return open_rows, expired_rows


def is_composition_expired(
    composition: Any,
    reference: Optional[date] = None,
) -> tuple[bool, str]:
    """
    Whether an Agent 3 composition describes an opportunity that already closed.

    Compositions are plain dicts (``tender_data`` plus ``email_content``) built in
    the same run, so the Agent 2 deadline is the authority here.
    """
    if not isinstance(composition, dict):
        return False, ""

    tender_data = composition.get("tender_data")
    if not isinstance(tender_data, dict):
        return False, ""

    ref = reference or datetime.utcnow().date()

    deadline = deadline_from_detailed_info(tender_data.get("detailed_info"))
    if deadline is None:
        screening = tender_data.get("screening")
        step3 = screening.get("step3") if isinstance(screening, dict) else None
        if isinstance(step3, dict):
            deadline = parse_deadline(step3.get("deadline"))

    if deadline is None:
        return False, ""

    if deadline < ref:
        return True, f"deadline {deadline.isoformat()} passed {(ref - deadline).days} day(s) ago"
    return False, ""


def filter_expired_compositions(
    compositions: list[Any],
    reference: Optional[date] = None,
) -> tuple[list[Any], int]:
    """Drop closed opportunities from an Agent 3 digest. Returns (kept, dropped)."""
    if not getattr(settings, "NOTIFY_SKIP_EXPIRED", True):
        return list(compositions), 0

    kept: list[Any] = []
    dropped = 0
    for composition in compositions:
        expired, reason = is_composition_expired(composition, reference)
        if expired:
            dropped += 1
            title = ""
            if isinstance(composition, dict):
                title = str((composition.get("tender_data") or {}).get("title") or "")
            logger.info(
                "Notification expiry gate: dropping composition %r — %s", title[:60], reason
            )
            continue
        kept.append(composition)
    return kept, dropped
