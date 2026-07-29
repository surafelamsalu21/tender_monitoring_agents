"""
Verify that a model-supplied detail URL actually occurs in the harvested page.

The extraction prompts ask for the notice URL "if present in the text", but
nothing enforced it, so the model sometimes produced a plausible-looking link
that does not exist. Two real examples from UNDP's portal:

* ``procurement-notices.undp.org/injected.cfm`` — a path that appears nowhere on
  the site.
* ``view_negotiation.cfm?nego_id=UNDP-ETH-00762`` — the right page but with the
  notice *reference* substituted for the numeric ``nego_id`` the site expects.

Both return a 34-character error page ("It appears that there is an issue."),
which downstream code mistook for anti-bot blocking. Grounding a URL against the
harvest means an invented link never reaches a notification.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional
from urllib.parse import urljoin, urlparse

# Absolute http(s) URLs, stopping before characters that usually close a link in
# markdown or HTML.
_URL_RE = re.compile(r"https?://[^\s)\]\}\"'<>|]+", re.IGNORECASE)

# Link targets that may be relative: markdown ``[label](target)`` and ``href="target"``.
_MARKDOWN_TARGET_RE = re.compile(r"\]\(\s*([^)\s]+)")
_HREF_RE = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.IGNORECASE)

_TRAILING_PUNCTUATION = ".,;:!?'\"`*_"


def normalize_url_key(url: str) -> str:
    """
    Reduce a URL to a comparison key: host + path + query, scheme-insensitive.

    Deliberately lenient about the things that differ harmlessly between a link
    in the page and the same link echoed by a model — scheme, ``www.``, trailing
    slash, fragment, and case in the host.
    """
    raw = (url or "").strip().rstrip(_TRAILING_PUNCTUATION)
    if not raw:
        return ""
    if raw.startswith("//"):
        raw = "https:" + raw
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")

    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = (parsed.path or "").rstrip("/")
    key = f"{host}{path}"
    if parsed.query:
        key = f"{key}?{parsed.query}"
    return key.lower()


def build_url_index(
    source_text: str = "",
    extra_urls: Optional[Iterable[str]] = None,
    base_url: str = "",
) -> set[str]:
    """
    Collect normalized keys for every URL the harvest actually saw.

    ``source_text`` is the page markdown; ``extra_urls`` is the crawler's link
    list, which catches links that survive in the DOM but not in the markdown.
    ``base_url`` resolves relative link targets — worth passing, because a missing
    entry here rewrites a perfectly good detail URL to the listing page.
    """
    index: set[str] = set()

    def _add(candidate: str) -> None:
        key = normalize_url_key(candidate)
        if key:
            index.add(key)

    text = source_text or ""

    for match in _URL_RE.finditer(text):
        _add(match.group(0))

    if base_url:
        for pattern in (_MARKDOWN_TARGET_RE, _HREF_RE):
            for match in pattern.finditer(text):
                target = match.group(1).strip()
                if not target or target.startswith(("#", "mailto:", "javascript:")):
                    continue
                _add(target if target.startswith(("http", "//")) else urljoin(base_url, target))

    for url in extra_urls or ():
        _add(str(url))

    return index


def is_url_grounded(url: str, index: set[str], page_url: str = "") -> bool:
    """
    True when ``url`` was present in the harvest (or is the listing page itself).

    Returns ``True`` for an empty index so callers that cannot supply the source
    text keep their previous behaviour rather than dropping every link.
    """
    if not index:
        return True

    key = normalize_url_key(url)
    if not key:
        return False

    if key in index:
        return True

    page_key = normalize_url_key(page_url)
    if page_key and key == page_key:
        return True

    # Only relax to a path comparison when the candidate carries no query of its
    # own — that covers a page link decorated with tracking parameters. When the
    # candidate does have a query it must match exactly, because on portals like
    # UNDP the query (``nego_id``) is the notice identity, and ignoring it is
    # precisely how an invented id would slip through.
    if "?" not in key:
        return any(candidate.split("?", 1)[0] == key for candidate in index)

    return False
