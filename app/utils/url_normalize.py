"""
URL normalization for HTTP fetch and tender link hygiene.

Crawl markdown often introduces spaces before extensions (``file .pdf``) or
literal spaces in paths. Normalizing before fetch avoids false anti-bot failures.
"""
from __future__ import annotations

import re
from urllib.parse import quote, unquote, urlparse, urlunparse

_SPACE_BEFORE_EXT = re.compile(r"\s+\.([a-z0-9]{1,8})\b", re.IGNORECASE)
_COLLAPSE_PATH_SPACES = re.compile(r"\s+")


def normalize_fetch_url(url: str) -> str:
    """
    Fix common crawl/markdown artifacts before HTTP fetch.

    - Trim outer whitespace
    - Remove spaces immediately before file extensions (``file .pdf`` → ``file.pdf``)
    - Percent-encode remaining spaces in the path
    """
    raw = (url or "").strip()
    if not raw:
        return raw

    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return raw

    path = unquote(parsed.path or "")
    path = _SPACE_BEFORE_EXT.sub(r".\1", path)
    path = _COLLAPSE_PATH_SPACES.sub(" ", path).strip()
    if " " in path:
        segs = path.split("/")
        segs = [quote(seg, safe="") if seg else seg for seg in segs]
        path = "/".join(segs)

    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        path,
        parsed.params,
        parsed.query,
        parsed.fragment,
    ))


def fetch_url_candidates(url: str) -> list[str]:
    """Ordered unique URL variants to try when fetching (PDFs, brittle links)."""
    raw = (url or "").strip()
    if not raw:
        return []

    candidates: list[str] = []
    seen: set[str] = set()

    def add(u: str) -> None:
        u = (u or "").strip()
        if not u or u in seen:
            return
        seen.add(u)
        candidates.append(u)

    normalized = normalize_fetch_url(raw)
    add(normalized)
    add(raw)

    if " " in raw and "%20" not in raw:
        add(raw.replace(" ", "%20"))

    fixed_dot = _SPACE_BEFORE_EXT.sub(r".\1", raw)
    if fixed_dot != raw:
        add(fixed_dot)
        add(normalize_fetch_url(fixed_dot))

    return candidates


def looks_like_pdf_url(url: str) -> bool:
    """True when URL path indicates a PDF, including ``file .pdf`` artifacts."""
    path = unquote(urlparse(str(url or "")).path or "").lower()
    path = _COLLAPSE_PATH_SPACES.sub("", path)
    return path.endswith(".pdf")
