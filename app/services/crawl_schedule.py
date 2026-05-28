"""Weekday-based crawl schedule (e.g. Monday and Thursday only)."""
from __future__ import annotations

import re
from datetime import datetime, time, timedelta, timezone
from typing import Iterable
from zoneinfo import ZoneInfo

from app.core.config import settings

_WEEKDAY_MAP: dict[str, int] = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "tues": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}

_WEEKDAY_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def parse_weekday_tokens(raw: str | None) -> list[int]:
    """Parse comma-separated weekday names into sorted unique weekday indices (Mon=0)."""
    if not raw or not str(raw).strip():
        return []
    indices: set[int] = set()
    for token in str(raw).split(","):
        key = token.strip().lower()
        if not key:
            continue
        if key not in _WEEKDAY_MAP:
            raise ValueError(f"Unknown weekday token: {token!r}")
        indices.add(_WEEKDAY_MAP[key])
    return sorted(indices)


def parse_schedule_time(raw: str | None) -> tuple[int, int]:
    """Parse ``HH:MM`` (24h) schedule time."""
    text = (raw or "09:00").strip()
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
    if not match:
        raise ValueError(f"Invalid CRAWL_SCHEDULE_TIME {text!r}; expected HH:MM")
    hour, minute = int(match.group(1)), int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Invalid CRAWL_SCHEDULE_TIME {text!r}")
    return hour, minute


def configured_weekdays() -> list[int]:
    return parse_weekday_tokens(settings.CRAWL_SCHEDULE_WEEKDAYS)


def uses_weekday_schedule() -> bool:
    return bool(configured_weekdays())


def schedule_timezone() -> ZoneInfo:
    name = (settings.CRAWL_SCHEDULE_TIMEZONE or "UTC").strip() or "UTC"
    return ZoneInfo(name)


def schedule_description(weekdays: Iterable[int] | None = None) -> str:
    days = list(weekdays if weekdays is not None else configured_weekdays())
    if not days:
        hours = int(settings.CRAWL_INTERVAL_HOURS)
        if hours % 24 == 0 and hours >= 24:
            n = hours // 24
            return f"Every {n} day{'s' if n != 1 else ''}"
        return f"Every {hours} hour{'s' if hours != 1 else ''}"
    hour, minute = parse_schedule_time(settings.CRAWL_SCHEDULE_TIME)
    tz_name = (settings.CRAWL_SCHEDULE_TIMEZONE or "UTC").strip() or "UTC"
    day_labels = ", ".join(_WEEKDAY_NAMES[i] for i in days)
    return f"{day_labels} at {hour:02d}:{minute:02d} ({tz_name})"


def next_scheduled_crawl_utc(
    now_utc: datetime | None = None,
    *,
    weekdays: list[int] | None = None,
) -> datetime:
    """
    Return the next UTC datetime when a scheduled crawl should run.

    Skips days not listed in ``weekdays`` (e.g. weekends when only Mon/Thu configured).
    """
    days = weekdays if weekdays is not None else configured_weekdays()
    if not days:
        raise ValueError("Weekday schedule is not configured")

    now_utc = now_utc or datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    tz = schedule_timezone()
    hour, minute = parse_schedule_time(settings.CRAWL_SCHEDULE_TIME)
    local_now = now_utc.astimezone(tz)

    for offset in range(8):
        candidate_date = local_now.date() + timedelta(days=offset)
        if candidate_date.weekday() not in days:
            continue
        slot_local = datetime.combine(
            candidate_date,
            time(hour, minute),
            tzinfo=tz,
        )
        if slot_local > local_now:
            return slot_local.astimezone(timezone.utc)

    # Should not happen when ``days`` is non-empty; safe fallback one week ahead.
    fallback_date = local_now.date() + timedelta(days=7)
    while fallback_date.weekday() not in days:
        fallback_date += timedelta(days=1)
    slot_local = datetime.combine(fallback_date, time(hour, minute), tzinfo=tz)
    return slot_local.astimezone(timezone.utc)


def seconds_until_next_crawl(now_utc: datetime | None = None) -> float:
    """Sleep duration until the next scheduled crawl."""
    if uses_weekday_schedule():
        target = next_scheduled_crawl_utc(now_utc)
        now = now_utc or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return max(0.0, (target - now).total_seconds())
    return max(0.0, float(settings.CRAWL_INTERVAL_HOURS) * 3600)
