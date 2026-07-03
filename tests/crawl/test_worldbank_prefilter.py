"""Unit tests for World Bank consulting pre-filter rules."""
from app.crawl.worldbank_procurement import worldbank_notice_passes_consulting_prefilter


def test_rejects_contract_award():
    notice = {
        "notice_type": "Contract Award",
        "procurement_group": "CS",
        "procurement_method_name": "Quality And Cost-Based Selection",
    }
    assert worldbank_notice_passes_consulting_prefilter(notice) is False


def test_rejects_goods_group():
    notice = {
        "notice_type": "Invitation for Bids",
        "procurement_group": "GO",
        "procurement_method_name": "Request for Bids",
    }
    assert worldbank_notice_passes_consulting_prefilter(notice) is False


def test_keeps_consultant_services_group():
    notice = {
        "notice_type": "Request for Expression of Interest",
        "procurement_group": "CS",
        "procurement_method_name": "Individual Consultant Selection",
    }
    assert worldbank_notice_passes_consulting_prefilter(notice) is True
