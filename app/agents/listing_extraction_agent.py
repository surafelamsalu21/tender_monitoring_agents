"""Fast local step 1: minimal prompt, listing-only extraction from markdown."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.llm_json_io import extract_message_text, parse_json_array
from app.core.config import settings
from app.core.llm_factory import get_chat_llm

logger = logging.getLogger(__name__)

_EXTRACT_SYSTEM = """Extract procurement/tender/RFQ notices from the markdown.
Reply with ONE JSON array only. No markdown code fences. No commentary before or after.
Start with [ end with ].
Each object: {"title","url","date","description"}.

Extraction rules:
- Include one object per distinct tender/procurement notice, RFQ, RFP, EOI, TOR, bid notice, or consulting opportunity.
- title: use the procurement subject. Do not use navigation labels, organization-only headings, or generic page titles.
- url: use the individual notice/detail/PDF URL when present. Make it absolute https. If only the listing page exists, use the listing URL.
- date: use the submission deadline/closing date/due date/opening date when clearly stated. Normalize to YYYY-MM-DD when possible. Leave "" when no deadline-like date is visible.
- description: one short English line summarizing scope, buyer/organization, budget/value, or requirements if visible.
- Use empty string for missing date/description. Do not invent deadlines, budgets, or organizations."""


def _normalize_row_url(href: str, base_url: str) -> str:
    href = (href or "").strip().split()[0].strip('"')
    if href.startswith("//"):
        return "https:" + href
    base = (base_url or "").strip() or ""
    if href.startswith("/") and base:
        return urljoin(base.rstrip("/") + "/", href.lstrip("/"))
    if not href.startswith("http") and base:
        return urljoin(base.rstrip("/") + "/", href)
    return href


def _rows_from_parsed_dicts(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows:
        title = str(r.get("title", "")).strip()
        url = str(
            r.get("url")
            or r.get("link")
            or r.get("href")
            or r.get("detail_url")
            or ""
        ).strip()
        if not title or not url:
            continue
        out.append(
            {
                "title": title,
                "url": url,
                "date": r.get("date") if r.get("date") is not None else "",
                "description": str(r.get("description", "") or "").strip()[:4000],
            }
        )
    return out


def _repair_truncated_json_array(raw: str) -> str:
    """Close a chopped JSON array of URL strings so json.loads may succeed."""
    s = raw.strip()
    if not s.startswith("["):
        return s
    if s.endswith("]"):
        return s
    s = re.sub(r",\s*$", "", s)
    if re.search(r'"https?://[^"]+$', s):
        s += '"]'
    else:
        s += "]"
    return s


def _human_title_from_tender_url(url: str) -> str:
    m = re.search(r"/bid/notice/(\d+)", url)
    if m:
        return f"Bid notice {m.group(1)}"
    m = re.search(r"/index/([^/?\s]+)", url)
    if m:
        return m.group(1).replace("_", " ")[:160]
    tail = url.rstrip("/").split("/")[-1][:120]
    return tail or url


def _plausible_notice_url(href: str) -> bool:
    low = href.lower()
    if "/bid/notice/" in low and "opening" in low:
        return True
    if "/index/" in low and "_egp" in low:
        return True
    if "/index/" in low and re.search(r"/index/\d+", low):
        return True
    return False


def _rows_from_string_url_json(raw: str) -> List[Dict[str, Any]]:
    """When the model returns `[\"https://...\", ...]` instead of objects."""
    if not raw or "[" not in raw:
        return []
    try:
        import json

        payload = json.loads(_repair_truncated_json_array(raw))
    except json.JSONDecodeError:
        payload = re.findall(r"https?://[^\s\"',\]]+", raw)
    if not isinstance(payload, list):
        return []
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for x in payload:
        if not isinstance(x, str) or not x.startswith("http"):
            continue
        href = x.strip().strip('"').rstrip(",").rstrip('"')
        if href in seen or not _plausible_notice_url(href):
            continue
        seen.add(href)
        low = href.lower()
        if "/bid-notices" in low:
            continue
        out.append(
            {
                "title": _human_title_from_tender_url(href),
                "url": href,
                "date": "",
                "description": "",
            }
        )
    return out


def _fallback_markdown_links(md: str, base_url: str) -> List[Dict[str, Any]]:
    """Deterministic backup when the LLM returns nothing parseable (common with format=json on small models)."""
    if not md or len(md) < 20:
        return []
    base = (base_url or "").strip() or "https://invalid.local/"
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for m in re.finditer(r"\[([^\]]{4,800})\]\(([^)]+)\)", md):
        title = re.sub(r"\s+", " ", m.group(1)).strip()
        href = _normalize_row_url(m.group(2), base)
        if not href.startswith("http") or href in seen:
            continue
        tl = title.lower()
        if tl in ("home", "next", "previous", "click here", "more", "»", "«"):
            continue
        seen.add(href)
        out.append({"title": title, "url": href, "date": "", "description": ""})
    bare = re.findall(r"https?://[^\s\)\"'<>]+", md)
    for href in bare:
        href = href.rstrip(").,;]")
        if href in seen or "/index/" not in href and "bid" not in href.lower():
            continue
        seen.add(href)
        out.append({"title": href.split("/")[-1][:120] or href, "url": href, "date": "", "description": ""})
    return out[:100]


class ListingExtractionAgent:
    """Single LLM call: page markdown → flat tender rows."""

    def __init__(self) -> None:
        # Omit Ollama ``format=json`` here: tiny instruct models often return [] or invalid JSON with it.
        self.llm = get_chat_llm(temperature=0.05, ollama_format="none")

    @staticmethod
    def truncate_markdown(page_content: str, max_chars: int) -> str:
        if len(page_content) <= max_chars:
            return page_content
        head = page_content[: max_chars - 220]
        tail = page_content[-180:]
        return f"{head}\n\n[... truncated to {max_chars} chars for speed ...]\n\n{tail}"

    async def extract_listings(
        self,
        page_content: str,
        *,
        page_url: Optional[str] = None,
        keyword_hints: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        max_chars = int(getattr(settings, "AGENT1_FAST_MAX_INPUT_CHARS", 12_000) or 12_000)
        body = self.truncate_markdown(page_content or "", max_chars)
        timeout = int(getattr(settings, "AGENT1_FAST_STEP_TIMEOUT_SEC", 300) or 300)
        base = (page_url or "").strip()

        hint_block = ""
        if keyword_hints:
            hints = ", ".join(str(h).strip() for h in keyword_hints[:40] if str(h).strip())
            if hints:
                hint_block = f"\nWeak keyword hints (optional): {hints}\n"

        ctx = f"\nListing page URL (resolve relative links): {base}\n" if base else ""

        user = f"""{ctx}Page markdown:

{body}
{hint_block}
Output the JSON array only."""

        prompt_chars = len(_EXTRACT_SYSTEM) + len(body) + len(hint_block)
        logger.info(
            "ListingExtractionAgent: prompt≈%s chars (body≤%s) timeout=%ss ollama_format=listing:none",
            prompt_chars,
            max_chars,
            timeout,
        )

        try:
            task = self.llm.ainvoke(
                [SystemMessage(content=_EXTRACT_SYSTEM), HumanMessage(content=user)]
            )
            response = await asyncio.wait_for(task, timeout=timeout)
            raw = extract_message_text(response)
            rows = parse_json_array(raw)
            out = _rows_from_parsed_dicts(rows)
            if not out:
                coerced = _rows_from_string_url_json(raw)
                if coerced:
                    logger.info(
                        "ListingExtractionAgent: coerced %s row(s) from URL-string JSON",
                        len(coerced),
                    )
                    out = coerced
            # Normalize relative URLs from model using page base
            if base:
                fixed: List[Dict[str, Any]] = []
                for item in out:
                    u = item["url"]
                    if not u.startswith("http"):
                        u = _normalize_row_url(u, base)
                    fixed.append({**item, "url": u})
                out = [x for x in fixed if x["url"].startswith("http")]

            if not out and raw.strip():
                logger.warning(
                    "ListingExtractionAgent: 0 rows after parse; model returned %s chars. First 600 chars: %r",
                    len(raw),
                    raw[:600],
                )

            if not out:
                fb = _fallback_markdown_links(body, base)
                if fb:
                    logger.info(
                        "ListingExtractionAgent: LLM empty — using markdown link fallback (%s row(s))",
                        len(fb),
                    )
                    out = fb

            logger.info("ListingExtractionAgent: %s row(s)", len(out))
            return out
        except asyncio.TimeoutError:
            logger.error("ListingExtractionAgent: timeout after %ss", timeout)
            fb = _fallback_markdown_links(body, base)
            return fb
        except Exception as exc:
            logger.error("ListingExtractionAgent failed: %s", exc)
            return _fallback_markdown_links(body, base)
