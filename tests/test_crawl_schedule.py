from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.core.config import settings
from app.services import crawl_schedule as cs


@pytest.fixture(autouse=True)
def _schedule_env(monkeypatch):
    monkeypatch.setattr(settings, "CRAWL_SCHEDULE_TIME", "09:00")
    monkeypatch.setattr(settings, "CRAWL_SCHEDULE_TIMEZONE", "Africa/Addis_Ababa")


def test_parse_weekday_tokens_monday_thursday():
    assert cs.parse_weekday_tokens("monday,thursday") == [0, 3]


def test_next_run_on_monday_before_slot():
    # Monday 2026-05-25 05:59 UTC = 08:59 Addis; next slot is 09:00 same day
    now = datetime(2026, 5, 25, 5, 59, tzinfo=timezone.utc)
    nxt = cs.next_scheduled_crawl_utc(now, weekdays=[0, 3])
    assert nxt.astimezone(ZoneInfo("Africa/Addis_Ababa")).strftime("%A %H:%M") == "Monday 09:00"


def test_next_run_skips_weekend_from_friday():
    # Friday 2026-05-29 07:00 UTC = 10:00 Addis (after slot) -> Monday
    now = datetime(2026, 5, 29, 7, 0, tzinfo=timezone.utc)
    nxt = cs.next_scheduled_crawl_utc(now, weekdays=[0, 3])
    assert nxt.astimezone(ZoneInfo("Africa/Addis_Ababa")).weekday() == 0


def test_next_run_thursday_after_slot_goes_to_monday():
    # Thursday 2026-05-28 07:00 UTC = 10:00 Addis (after 09:00 slot)
    now = datetime(2026, 5, 28, 7, 0, tzinfo=timezone.utc)
    nxt = cs.next_scheduled_crawl_utc(now, weekdays=[0, 3])
    assert nxt.astimezone(ZoneInfo("Africa/Addis_Ababa")).strftime("%A") == "Monday"


def test_invalid_weekday_raises():
    with pytest.raises(ValueError, match="Unknown weekday"):
        cs.parse_weekday_tokens("notaday")
