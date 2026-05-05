"""
Harvest → Agent 1: generic presentation (same idea as Test Crawler).

Feeds **crawl markdown** (readable text/tables — not raw HTML) to Agent 1, plus a **deduped URL
supplement** built from Crawl4AI `links`, raw `href="..."` snippets in markdown/HTML when present,
and bare `https://…` spans. No hostname-specific rules.

Expiry / deadline parsing keeps the **original** harvest markdown unchanged on a parallel channel.
"""

from __future__ import annotations

import logging
import re
from typing import Any, List, Optional, Tuple
from urllib.parse import unquote, urljoin, urlparse

from app.crawl.orchestrator import _flatten_scrape_links

logger = logging.getLogger(__name__)

# Keep Agent 1 input bounded for local LLMs; expiry gate still sees full markdown separately.
_MAX_MARKDOWN_CHARS = 120_000
_HEAD_CHARS = 78_000
_TAIL_CHARS = 38_000
_MAX_SUPPLEMENT_URLS = 400
_HTML_HREF_SCAN_CAP = 600_000  # chars of HTML to scan for href=

_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".bmp")
_NOISE_HOST_SUBSTRINGS = (
    "facebook.com",
    "twitter.com",
    "twimg.com",
    "linkedin.com",
    "instagram.com",
    "youtube.com",
    "ytimg.com",
    "vimeo.com",
    "pinterest.com",
    "tiktok.com",
    "googletagmanager.com",
    "google-analytics.com",
    "doubleclick.net",
    "gstatic.com",
    "gravatar.com",
)

_MD_PAREN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)", re.MULTILINE)
_MD_BARE_URL = re.compile(r"https?://[^\s\)\]<>\"'`]+", re.IGNORECASE)
_HTML_HREF = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
_AU_BID_DETAIL_PATH = re.compile(r"^/en/bids/\d{8}/[^/?#]+/?$", re.IGNORECASE)
_EU_PORTAL_HOST = "ec.europa.eu"
_EU_PORTAL_PATH_PREFIX = "/info/funding-tenders"
_EU_TENDER_DETAIL_SEGMENTS = ("opportunity-detail", "grant-detail", "competitive-calls-detail")
_UNGM_NOTICE_DETAIL_PATH = re.compile(r"^/Public/Notice/\d+/?$", re.IGNORECASE)


def _coerce_links(raw: Any) -> List[str]:
    """Normalize Crawl4AI `links` (dict/list/str/hrefs) into strings."""
    if raw is None:
        return []
    if isinstance(raw, dict):
        return _flatten_scrape_links(raw)
    if isinstance(raw, list):
        out: List[str] = []
        for item in raw:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            elif isinstance(item, dict):
                href = item.get("href") or item.get("url")
                if href:
                    out.append(str(href).strip())
        return list(dict.fromkeys(out))
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    return []


def _strip_url_trailing_junk(u: str) -> str:
    return u.rstrip(".,;:\"')]>")


def _safe_url(base: str, candidate: str) -> Optional[str]:
    c = candidate.strip()
    if not c or c.startswith("#") or c.lower().startswith("javascript:"):
        return None
    if c.startswith("mailto:") or c.startswith("tel:"):
        return None
    if c.startswith("//"):
        c = "https:" + c
    if not c.startswith("http"):
        c = urljoin(base, c)
    c = _strip_url_trailing_junk(unquote(c.split("#", 1)[0]))
    if len(c) < 8 or not c.startswith("http"):
        return None
    return c


def _is_noise_url(url: str) -> bool:
    u = url.lower()
    host = urlparse(url).netloc.lower()
    if any(s in host or s in u for s in _NOISE_HOST_SUBSTRINGS):
        return True
    path = urlparse(url).path.lower()
    low_path = path
    if low_path.endswith(_IMAGE_SUFFIXES) and ".pdf" not in low_path:
        return True
    return False


def _is_eu_tenders_listing(page_url: str) -> bool:
    parsed = urlparse(page_url or "")
    return (
        parsed.netloc.lower() in (_EU_PORTAL_HOST, f"www.{_EU_PORTAL_HOST}")
        and parsed.path.startswith(_EU_PORTAL_PATH_PREFIX)
    )


def _is_eu_tender_detail_url(url: str) -> bool:
    """
    Accept only proper EU portal opportunity/grant detail SPA routes.
    Example: .../portal/screen/opportunities/opportunity-detail/12345678
    """
    parsed = urlparse(url or "")
    if parsed.netloc.lower() not in (_EU_PORTAL_HOST, f"www.{_EU_PORTAL_HOST}"):
        return False
    path = parsed.path.lower()
    return any(seg in path for seg in _EU_TENDER_DETAIL_SEGMENTS)


def _is_eu_tenders_noise_url(url: str) -> bool:
    """
    Reject EU portal URLs that are navigation/filter/search pages rather than
    individual tender details.
    """
    parsed = urlparse(url or "")
    if parsed.netloc.lower() not in (_EU_PORTAL_HOST, f"www.{_EU_PORTAL_HOST}"):
        return False
    # only filter EC domain URLs
    path = parsed.path.lower()
    # keep detail pages
    if any(seg in path for seg in _EU_TENDER_DETAIL_SEGMENTS):
        return False
    # reject everything else from the portal (listing pages, filter pages, etc.)
    if "funding-tenders" in path and "opportunities" in path:
        return True
    return False


def _is_ungm_listing(page_url: str) -> bool:
    return "ungm.org" in urlparse(page_url or "").netloc.lower()


def _is_ungm_notice_detail_url(url: str) -> bool:
    """Accept only /Public/Notice/<numeric-id> — reject filters, login pages, etc."""
    parsed = urlparse(url or "")
    return "ungm.org" in parsed.netloc.lower() and bool(
        _UNGM_NOTICE_DETAIL_PATH.match(parsed.path)
    )


def _is_au_bids_listing(page_url: str) -> bool:
    parsed = urlparse(page_url or "")
    return parsed.netloc.lower().endswith("au.int") and parsed.path.rstrip("/") == "/en/bids"


def _is_au_bid_detail_url(url: str) -> bool:
    parsed = urlparse(url or "")
    return parsed.netloc.lower().endswith("au.int") and bool(
        _AU_BID_DETAIL_PATH.match(parsed.path)
    )


def _trim_au_bids_listing(markdown: str) -> str:
    """
    AU `/en/bids/` includes menus, topic resources, adverts and speeches after the
    table. Keep only the actual All Bids section so Agent1 does not extract resources.
    """
    if not markdown:
        return ""

    start_patterns = (
        r"\n##\s+All Bids\s*\n",
        r"\n#\s+All Bids\s*\n",
    )
    start = -1
    for pat in start_patterns:
        match = re.search(pat, markdown, re.IGNORECASE)
        if match:
            start = match.start()

    if start == -1:
        start = 0

    end_candidates = []
    for pat in (
        r"\n##\s+Adverts\s*\n",
        r"\n##\s+Topic Resources\s*\n",
        r"\n##\s+Resources\s*\n",
        r"\n##\s+Opportunities\s*\n",
    ):
        match = re.search(pat, markdown[start:], re.IGNORECASE)
        if match:
            end_candidates.append(start + match.start())

    end = min(end_candidates) if end_candidates else len(markdown)
    trimmed = markdown[start:end].strip()
    return (
        "Source URL: https://au.int/en/bids/\n"
        "Only extract rows from the All Bids table below. Ignore sorting links, "
        "procurement category links, topic resources, adverts, documents, speeches, "
        "menus, and footer content.\n\n"
        f"{trimmed}"
    )


def _gather_urls_from_markdown(md: str, base: str) -> List[str]:
    found: List[str] = []
    for m in _MD_PAREN_LINK.finditer(md or ""):
        inner = (m.group(1) or "").strip().split()[0]
        nu = _safe_url(base, inner)
        if nu:
            found.append(nu)
    for m in _MD_BARE_URL.finditer(md or ""):
        nu = _safe_url(base, m.group(0))
        if nu:
            found.append(nu)
    return found


def _gather_urls_from_html(html: Optional[str], base: str) -> List[str]:
    if not html:
        return []
    chunk = html[:_HTML_HREF_SCAN_CAP]
    found: List[str] = []
    for m in _HTML_HREF.finditer(chunk):
        cand = (m.group(1) or "").strip()
        nu = _safe_url(base, cand)
        if nu:
            found.append(nu)
    return found


def _maybe_truncate_body(md: str) -> Tuple[str, bool]:
    if len(md) <= _MAX_MARKDOWN_CHARS:
        return md, False
    head = md[:_HEAD_CHARS]
    tail = md[-_TAIL_CHARS:]
    joined = (
        f"{head}\n\n"
        f"[... {_MAX_MARKDOWN_CHARS} character limit: middle omitted; "
        f"URLs below may still contain detail/pdf links …]\n\n"
        f"{tail}"
    )
    return joined, True


def dual_markdown_for_agent1_and_expiry(
    page_url: str,
    harvest_markdown: str,
    crawl_links: Optional[Any] = None,
    *,
    html: Optional[str] = None,
) -> Tuple[str, Optional[str]]:
    """
    `(page_content_for_agent1, listing_markdown_for_expiry_gate)`.

    - Agent 1: page URL header + truncated-if-needed crawl **markdown** + URL supplement section.
    - Expiry: **original** `harvest_markdown` when non-empty so table rows / dates survive unchanged.
      Callers pass this as ``listing_markdown_for_expiry``; workflow uses Agent 1 text only when None.
    """
    base = (page_url or "").strip() or "https://example.com/"
    is_au_bids = _is_au_bids_listing(base)
    is_eu_portal = _is_eu_tenders_listing(base)
    is_ungm = _is_ungm_listing(base)
    raw_md = _trim_au_bids_listing(harvest_markdown or "") if is_au_bids else (harvest_markdown or "")

    pooled: List[str] = []
    pooled.extend(_coerce_links(crawl_links))
    pooled.extend(_gather_urls_from_markdown(raw_md, base))
    pooled.extend(_gather_urls_from_html(html, base))

    dedup: List[str] = []
    seen: set[str] = set()
    for u in pooled:
        if is_au_bids and not _is_au_bid_detail_url(u):
            continue
        if is_eu_portal and not _is_eu_tender_detail_url(u):
            continue
        if is_ungm and not _is_ungm_notice_detail_url(u):
            continue
        if _is_noise_url(u):
            continue
        if u in seen:
            continue
        seen.add(u)
        dedup.append(u)
    dedup.sort()

    truncated_body, truncated = _maybe_truncate_body(raw_md)
    appendix_lines = dedup[:_MAX_SUPPLEMENT_URLS]

    supplement = ""
    if appendix_lines:
        supplement = (
            "\n\n---\n\n"
            "### Supplement — URLs gathered from this crawl\n\n"
            "Use **exact URLs** below in JSON `url` / `step3.link` when they belong to one of the "
            "notices described above (matching title, reference, or nearby row).\n\n"
            + "\n".join(f"- {u}" for u in appendix_lines)
        )

    header = f"Page URL (context): {base.strip()}\n\n---\n\n"
    agent_payload = header + truncated_body + supplement

    expiry_channel: Optional[str] = raw_md if raw_md.strip() else None

    logger.info(
        "Listing prep (generic): raw_md_chars=%s truncated=%s supplement_urls=%s",
        len(raw_md),
        truncated,
        len(appendix_lines),
    )

    return agent_payload, expiry_channel

