"""Tests for fetch URL normalization."""

from app.utils.url_normalize import (
    fetch_url_candidates,
    looks_like_pdf_url,
    normalize_fetch_url,
)


def test_normalize_removes_space_before_pdf_extension():
    raw = "https://www.mowe.gov.et/sites/default/files/tender/minigird .pdf"
    assert normalize_fetch_url(raw) == (
        "https://www.mowe.gov.et/sites/default/files/tender/minigird.pdf"
    )


def test_normalize_encodes_internal_path_spaces():
    raw = "https://www.rti.org/sites/default/files/documents/2026-06/SunGold-RFP_OCA -F.pdf"
    out = normalize_fetch_url(raw)
    assert " " not in out
    assert "SunGold-RFP_OCA%20-F.pdf" in out


def test_fetch_url_candidates_include_raw_and_normalized():
    raw = "https://example.com/a .pdf"
    cands = fetch_url_candidates(raw)
    assert raw in cands
    assert "https://example.com/a.pdf" in cands


def test_looks_like_pdf_url_with_space_before_extension():
    assert looks_like_pdf_url("https://x.test/file .pdf")
    assert not looks_like_pdf_url("https://x.test/file.pdfx")
