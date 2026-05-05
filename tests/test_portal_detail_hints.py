"""Unit tests for portal markdown hints and deadline parsing."""
from datetime import datetime

from app.agents.portal_detail_hints import (
    extract_egp_bid_opening_record,
    enrich_detail_from_page_markdown,
    looks_like_procurement_reference,
    parse_opening_datetime_line,
    title_upgrade_warranted,
)
from app.repositories.tender_repository import TenderRepository


def test_looks_like_procurement_reference():
    assert looks_like_procurement_reference("DCIC/NCONS/2025-2026/00672")
    assert not looks_like_procurement_reference("Hotel services for meeting")


def test_extract_egp_subject_and_opening():
    md = """
RECORD OF BID OPENING
Subject of Procurement\tHOTEL SERVICES FOR BREAKFAST MEETING
Procurement Method\tMicro Procurement
Date and Time of bid Opening\t28 Apr 2026 at 15:45
Bids received\t1
"""
    h = extract_egp_bid_opening_record(md)
    assert "HOTEL SERVICES" in h.get("subject", "")
    assert "28 Apr 2026" in h.get("opening_line", "")


def test_enrich_overwrites_placeholder_title():
    md = "Subject of Procurement\tREAL SUBJECT LINE HERE\n"
    di = {"detailed_title": "Complete translated title", "deadline": None}
    basic = {"title": "DCIC/NCONS/2025-2026/00672", "url": "https://x"}
    out = enrich_detail_from_page_markdown(md, di, basic)
    assert out["detailed_title"] == "REAL SUBJECT LINE HERE"


def test_parse_opening_datetime():
    dt = parse_opening_datetime_line("28 Apr 2026 at 15:45")
    assert dt is not None
    assert dt.date().isoformat() == "2026-04-28"
    dt2 = parse_opening_datetime_line("2026-04-28T15:45:00")
    assert dt2 is not None


def test_tender_repo_parse_deadline_datetime():
    repo = TenderRepository()
    assert repo._parse_deadline("2026-04-28T15:45:00") == datetime(2026, 4, 28, 15, 45, 0)
    d = repo._parse_deadline("2026-04-22 14:01")
    assert d is not None and d.date().isoformat() == "2026-04-22"


def test_title_upgrade_warranted():
    assert title_upgrade_warranted("DCIC/NCONS/2025-2026/00672", "Hotel services for event")
    assert not title_upgrade_warranted("Good title", "Complete translated title")
