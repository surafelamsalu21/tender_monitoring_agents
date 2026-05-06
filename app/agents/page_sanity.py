"""
Detect HTTP errors, soft-404 pages, and empty shells so agents do not invent tenders.
Used by Agent 1/2 listing paths and detail extraction.
"""
from __future__ import annotations

import re
from typing import Optional

_HTTP_BAD_THRESHOLD = 400

_TITLE_ERROR_HINT = re.compile(
    r"(?:^|\n)\s*(?:404|403|500|502|503)\s*[:\-]?\s*(?:not\s+found|forbidden|error)\b|"
    r"\bpage\s+not\s+found\b|"
    r"\bthis\s+page\s+(?:does\s+not\s+exist|could\s+not\s+be\s+found)\b|"
    r"\bthe\s+page\s+you\s+(?:are\s+looking\s+for|requested)\b.{0,80}\b(?:not\s+found|doesn'?t\s+exist)\b|"
    r"\baccess\s+denied\b|"
    r"\bhttp\s+error\s+404\b|"
    r"\berror\s+404\b|"
    r"\b404\s+not\s+found\b|"
    r"\bnot\s+found\s*\(\s*404\s*\)\b|"
    r"\bsorry[,\s].{0,60}\b(?:not\s+found|doesn'?t\s+exist|unavailable)\b|"
    r"\brequested\s+(?:resource|url|page)\s+(?:was\s+)?not\s+found\b|"
    r"\bcontent\s+(?:is\s+)?not\s+available\b|"
    r"\bno\s+results\s+found\b|"
    r"\bsite\s+temporarily\s+unavailable\b|"
    r"\bunder\s+maintenance\b|"
    r"\bnginx\b.{0,40}\b404\b",
    re.I | re.MULTILINE,
)

_AUTH_WALL_HINT = re.compile(
    r"\bsign\s+in\s+to\s+continue\b|\blog\s+in\s+to\s+view\b|\bplease\s+(?:log\s+in|authenticate)\b",
    re.I,
)

_PROCUREMENT_HINT = re.compile(
    r"\b(?:tender|procurement|rfq|rfp|eoi|expression\s+of\s+interest|"
    r"request\s+for\s+(?:proposal|quotation)|bid\s*(?:notice|opening|submission)|"
    r"submission\s+deadline|closing\s+date|procuring\s+entity|invitation\s+to\s+bid|"
    r"contract\s+notice|solicitation)\b",
    re.I,
)


def http_status_is_hard_failure(code: Optional[int]) -> bool:
    if code is None:
        return False
    try:
        return int(code) >= _HTTP_BAD_THRESHOLD
    except (TypeError, ValueError):
        return False


def markdown_indicates_error_or_empty_notice(
    text: str,
    *,
    http_status: Optional[int] = None,
    min_chars_for_keyword_check: int = 600,
) -> Optional[str]:
    """
    Return a short reason if this body is not a real procurement notice page we should
    extract from; otherwise None.

    - Uses HTTP status when provided (e.g. from crawl4ai).
    - Matches common error / soft-404 / maintenance patterns in text.
    - Flags very short bodies with no procurement-related vocabulary.
    """
    if http_status_is_hard_failure(http_status):
        return f"HTTP status {http_status}"
    raw = (text or "").strip()
    if not raw:
        return "empty page body"
    head = raw[:24000]
    low = head.lower()
    if _TITLE_ERROR_HINT.search(low):
        return "error or not-found page (content pattern)"
    if _AUTH_WALL_HINT.search(low) and len(raw) < min_chars_for_keyword_check * 5:
        return "authentication wall with little public content"
    if len(raw) < min_chars_for_keyword_check and not _PROCUREMENT_HINT.search(head):
        return "too little content and no procurement keywords"
    return None
