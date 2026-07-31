import sys
import types

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

if "langchain_openai" not in sys.modules:
    mod = types.ModuleType("langchain_openai")
    mod.ChatOpenAI = object
    sys.modules["langchain_openai"] = mod

if "langchain_ollama" not in sys.modules:
    mod = types.ModuleType("langchain_ollama")
    mod.ChatOllama = object
    sys.modules["langchain_ollama"] = mod

import app.models  # noqa: F401 - register SQLAlchemy models
from app.core.database import Base
from app.crawl.playwright_harvest import _is_egp_bids_url, _undp_region_filter_id
from app.models.page import MonitoredPage
from app.pipeline.simple_orchestrator import _batch_identity_key
from app.pipeline.agent1_structure import _heuristic_rows_from_markdown
from app.repositories.tender_repository import TenderRepository


def test_heading_fallback_extracts_tdb_procurement_notices():
    markdown = """
# Consulting & Procurement

##### (TOR) ANNUAL VERIFICATION OF PERFORMANCE FOR SUSTAINABILITY-LINKED LOAN

[Sustainability Linked Loan - TOR - April 2026](/wp-content/uploads/tor.pdf)

##### REQUEST FOR QUOTATION (RFQ) - 300 Mbps 100% Dedicated Internet Connection

Dedicated Internet 300 Mbps procurement- extension
"""

    rows = _heuristic_rows_from_markdown(
        markdown,
        "https://www.tdbgroup.org/consulting-procurement/",
    )

    assert [row.title for row in rows] == [
        "(TOR) ANNUAL VERIFICATION OF PERFORMANCE FOR SUSTAINABILITY-LINKED LOAN",
        "REQUEST FOR QUOTATION (RFQ) - 300 Mbps 100% Dedicated Internet Connection",
    ]
    assert rows[0].detail_url == "https://www.tdbgroup.org/wp-content/uploads/tor.pdf"


def test_undp_africa_region_filter_url_convention():
    assert (
        _undp_region_filter_id("https://procurement-notices.undp.org/?region=RAF")
        == "region_RAF"
    )
    assert (
        _undp_region_filter_id("https://procurement-notices.undp.org/?region=africa")
        == "region_RAF"
    )
    assert _undp_region_filter_id("https://example.com/?region=africa") is None


def test_egp_bids_url_detects_production_host():
    assert _is_egp_bids_url("https://production.egp.gov.et/egp/bids/all")
    assert _is_egp_bids_url("https://www.production.egp.gov.et/egp/bids/all")
    assert _is_egp_bids_url("https://egp.gov.et/egp/bids/all")
    assert not _is_egp_bids_url("https://production.egp.gov.et/egp/home")


def test_duplicate_check_uses_detail_url_when_llm_wording_changes():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    repo = TenderRepository()
    try:
        page = MonitoredPage(
            name="eGP",
            url="https://egpuganda.go.ug/bid-notices",
            is_active=True,
        )
        db.add(page)
        db.commit()
        db.refresh(page)

        first = repo.save_tender(
            db,
            page_id=page.id,
            title="Request for Quotation Notice for Agricultural Inputs, Equipment and Seedlings",
            url="https://egpuganda.go.ug/index/370642518_egp",
            tender_date="2026-05-22",
            description="",
            screening_result={
                "step3": {
                    "source": "Ministry of Agriculture, Animal Industry and Fisheries",
                    "deadline": "2026-05-22",
                    "type": "other",
                    "country": "Uganda",
                },
                "yes_count": 5,
                "passes_filter": True,
            },
        )

        assert first is not None
        assert repo.check_duplicate_tender(
            db,
            title="Agricultural Inputs and Seedlings",
            url="https://egpuganda.go.ug/index/370642518_egp/",
            page_id=page.id,
            screening_result={
                "step3": {
                    "source": "MAAIF",
                    "deadline": "2026-05-22",
                    "type": "other",
                    "country": "Uganda",
                }
            },
            tender_date="2026-05-22",
        )
    finally:
        db.close()


def test_duplicate_check_ignores_tracking_query_and_fragment():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    repo = TenderRepository()
    try:
        page = MonitoredPage(
            name="WB",
            url="https://example.org/notices",
            is_active=True,
        )
        db.add(page)
        db.commit()
        db.refresh(page)

        first = repo.save_tender(
            db,
            page_id=page.id,
            title="Road Corridor Technical Advisor",
            url="https://example.org/notices/123?utm_source=mail#section",
            tender_date="2026-07-31",
            description="",
            screening_result={
                "step3": {
                    "source": "World Bank",
                    "deadline": "2026-07-31",
                    "type": "consulting",
                    "country": "Ethiopia",
                },
                "yes_count": 5,
                "passes_filter": True,
            },
        )

        assert first is not None
        assert repo.check_duplicate_tender(
            db,
            title="Road Corridor Technical Advisor",
            url="https://example.org/notices/123?utm_medium=weekly",
            page_id=page.id,
            screening_result={
                "step3": {
                    "source": "World Bank",
                    "deadline": "2026-07-31",
                    "type": "consulting",
                    "country": "Ethiopia",
                }
            },
            tender_date="2026-07-31",
        )
    finally:
        db.close()


def test_batch_identity_key_collapses_whitespace_and_tracking_params():
    repo = TenderRepository()
    t1 = {
        "title": "  Economic   Policy Advisory  ",
        "url": "https://example.org/notices/777?utm_source=mail",
        "date": "2026-08-05",
        "screening": {
            "step3": {
                "source": "AfDB",
                "deadline": "2026-08-05",
                "type": "consulting",
                "country": "Ethiopia",
            }
        },
    }
    t2 = {
        "title": "economic policy advisory",
        "url": "https://example.org/notices/777?utm_medium=digest#top",
        "date": "2026-08-05",
        "screening": {
            "step3": {
                "source": "afdb",
                "deadline": "2026-08-05",
                "type": "consulting",
                "country": "ethiopia",
            }
        },
    }

    assert _batch_identity_key(t1, page_id=42, tender_repo=repo) == _batch_identity_key(
        t2, page_id=42, tender_repo=repo
    )


def test_detailed_tender_save_normalizes_placeholder_strings():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    repo = TenderRepository()
    try:
        page = MonitoredPage(
            name="eGP",
            url="https://egpuganda.go.ug/bid-notices",
            is_active=True,
        )
        db.add(page)
        db.commit()
        db.refresh(page)

        tender = repo.save_tender(
            db,
            page_id=page.id,
            title="Procurement of Frame Work Contract for Electrification",
            url="https://egpuganda.go.ug/index/371927002_egp",
            tender_date="2026-05-14",
            description="",
            screening_result={"step3": {"deadline": "2026-05-14"}, "passes_filter": True},
        )

        detail = repo.save_detailed_tender(
            db,
            tender_id=tender.id,
            detailed_info={
                "detailed_title": "Procurement of Frame Work Contract for Electrification",
                "detailed_description": "null",
                "requirements": "N/A",
                "deadline": "2026-05-14",
                "tender_value": "Budget/estimated value with currency",
                "duration": "null",
                "contact_info": {
                    "organization": "Kampala Capital City Authority",
                    "contact_person": "null",
                    "phone": "N/A",
                    "email": "Email address",
                    "address": "not specified",
                },
                "additional_details": "null",
            },
        )

        assert detail.detailed_description == ""
        assert detail.requirements is None
        assert detail.tender_value is None
        assert detail.duration is None
        assert detail.additional_details is None
        assert detail.contact_info == (
            '{"organization": "Kampala Capital City Authority", '
            '"contact_person": null, "phone": null, "email": null, "address": null}'
        )
    finally:
        db.close()
