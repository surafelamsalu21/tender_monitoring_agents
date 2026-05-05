"""
Heuristic field extraction from known portal layouts (e.g. eGP Uganda bid opening records).
Fills Agent 2 gaps when local LLMs echo prompt placeholders.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, Optional

# Prompt echo / template strings from Agent 2 system message
_PLACEHOLDER_TITLE_PHRASES = frozenset(
    (
        "complete translated title",
        "tender title",
        "n/a",
    )
)
_PLACEHOLDER_DESC_PHRASES = frozenset(
    (
        "full translated description",
        "technical requirements and qualifications",
    )
)


def looks_like_procurement_reference(title: Optional[str]) -> bool:
    """True if title looks like a ref code (e.g. DCIC/NCONS/2025-2026/00672) not a subject line."""
    if not title or not str(title).strip():
        return False
    s = str(title).strip()
    if re.match(r"^[A-Z0-9]{2,10}/[A-Z0-9_/\-]+/\d{4}-\d{4}/\d{3,10}$", s, re.I):
        return True
    if re.match(r"^\d{4,10}$", s):
        return True
    return False


def _is_placeholder_title(text: Optional[str]) -> bool:
    if not text or not str(text).strip():
        return True
    t = str(text).strip().lower()
    return any(p in t for p in _PLACEHOLDER_TITLE_PHRASES) or len(t) < 6


def _is_placeholder_description(text: Optional[str]) -> bool:
    if not text or not str(text).strip():
        return True
    t = str(text).strip().lower()
    return any(p in t for p in _PLACEHOLDER_DESC_PHRASES)


def extract_egp_bid_opening_record(markdown: str) -> Dict[str, str]:
    """
    Parse 'Record of bid opening' style markdown (eGP Uganda and similar table dumps).
    Returns best-effort keys: subject, opening_line, procurement_method, bid_amount_line.
    """
    out: Dict[str, str] = {}
    if not markdown:
        return out

    md = markdown.replace("\r\n", "\n")

    # Tab-separated labels (Crawl4AI markdown often preserves tabs)
    m = re.search(
        r"Subject\s+of\s+Procurement\s+([^\n]+)",
        md,
        re.IGNORECASE,
    )
    if m:
        subj = re.sub(r"\s+", " ", m.group(1)).strip()
        if subj and len(subj) > 5:
            out["subject"] = subj[:2000]

    m = re.search(
        r"Date\s+and\s+Time\s+of\s+bid\s+Opening\s+([^\n]+)",
        md,
        re.IGNORECASE,
    )
    if m:
        out["opening_line"] = m.group(1).strip()[:200]

    m = re.search(
        r"Procurement\s+Method\s+([^\n]+)",
        md,
        re.IGNORECASE,
    )
    if m:
        out["procurement_method"] = m.group(1).strip()[:500]

    # First data row under bidder table: line starting with "1" then tab
    m = re.search(
        r"(?:^|\n)\s*1\s*\t+([^\n]+)",
        md,
    )
    if m:
        out["bidder_line"] = re.sub(r"\s+", " ", m.group(1).strip())[:1500]

    return out


def parse_opening_datetime_line(line: str) -> Optional[datetime]:
    """e.g. '28 Apr 2026 at 15:45' or '2026-04-28T15:45:00'."""
    if not line:
        return None
    s = line.strip()

    if "T" in s and re.match(r"\d{4}-\d{2}-\d{2}T", s):
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            try:
                base = s.split(".")[0].split("+")[0]
                return datetime.fromisoformat(base)
            except ValueError:
                pass

    for fmt in (
        "%d %b %Y at %H:%M",
        "%d %B %Y at %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def enrich_detail_from_page_markdown(
    markdown: str,
    detailed_info: Dict[str, Any],
    basic_tender: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge portal hints into Agent 2 JSON."""
    if not detailed_info:
        detailed_info = {}
    merged = dict(detailed_info)
    hints = extract_egp_bid_opening_record(markdown)
    if not hints:
        return merged

    bt = (basic_tender.get("title") or "").strip()
    need_title = _is_placeholder_title(merged.get("detailed_title")) or looks_like_procurement_reference(
        merged.get("detailed_title")
    ) or looks_like_procurement_reference(bt)

    if hints.get("subject") and need_title:
        merged["detailed_title"] = hints["subject"]

    if hints.get("opening_line"):
        odt = parse_opening_datetime_line(hints["opening_line"])
        if odt:
            date_only = odt.strftime("%Y-%m-%d")
            if _is_placeholder_or_missing_date(merged.get("deadline")):
                merged["deadline"] = date_only
            if _is_placeholder_or_missing_date(merged.get("submission_deadline")):
                merged["submission_deadline"] = date_only

    if hints.get("procurement_method"):
        if not merged.get("procurement_method") or _is_placeholder_org(
            str(merged.get("procurement_method"))
        ):
            merged["procurement_method"] = hints["procurement_method"]

    if hints.get("bidder_line"):
        desc = merged.get("detailed_description") or ""
        if _is_placeholder_description(desc):
            merged["detailed_description"] = (
                f"Successful bidder / bid row (from notice):\n{hints['bidder_line']}"
            )

        ci = merged.get("contact_info")
        if not isinstance(ci, dict):
            ci = {}
        org_guess = hints["bidder_line"].split("(")[0].strip()
        if org_guess and len(org_guess) > 5:
            if _is_placeholder_org(str(ci.get("organization", ""))):
                ci = {**ci, "organization": org_guess[:500]}
            merged["contact_info"] = ci

    return merged


def _is_placeholder_or_missing_date(val) -> bool:
    if val is None or str(val).strip().lower() in ("", "null", "n/a", "none"):
        return True
    return False


def _is_placeholder_org(s: str) -> bool:
    t = s.strip().lower()
    return t in ("", "issuing organization", "n/a", "not processed")


def title_upgrade_warranted(current_title: Optional[str], detailed_title: Optional[str]) -> bool:
    if not detailed_title or not str(detailed_title).strip():
        return False
    dt = str(detailed_title).strip()
    if _is_placeholder_title(dt):
        return False
    if len(dt) < 12:
        return False
    ct = (current_title or "").strip()
    if looks_like_procurement_reference(ct) and not looks_like_procurement_reference(dt):
        return True
    if len(dt) > len(ct) + 10 and ct.upper() != dt.upper():
        return True
    return False
