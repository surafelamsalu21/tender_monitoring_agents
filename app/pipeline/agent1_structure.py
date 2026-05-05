"""
Agent 1 (simple pipeline): structure listing markdown into rows — one LLM call, no checklist.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, List, Optional
from urllib.parse import urljoin

from langchain_core.messages import HumanMessage

from app.core.config import settings
from app.core.llm_factory import get_chat_llm
from app.pipeline.progress import active_llm_label, pipeline_tty
from app.pipeline.schemas import ListingRowV1

logger = logging.getLogger(__name__)

_SYSTEM = """You list procurement/tender notices from page text.

Output ONLY a JSON array. No markdown fences, no commentary.
Each element must be an object with keys:
- title (string, required)
- reference (string or null)
- publication_date (string or null, normalize to YYYY-MM-DD when possible)
- deadline (string or null, normalize to YYYY-MM-DD when possible)
- detail_url (string or null, absolute https URL if present in the text; else null)
- country (string or null)
- snippet (short English summary or null)

Rules:
- Include one object per distinct notice/tender row you see in the text.
- Extract deadlines from labels like deadline, closing date, submission deadline, bid closing, due date, opening date, response deadline, application deadline, or proposal submission.
- Do not use publication dates as deadlines unless the text clearly says it is the closing/submission date.
- Prefer the individual notice/PDF/detail URL over the listing page URL.
- Keep title as the procurement subject, not a menu label or organization name.
- Use JSON null, not the strings "null", "N/A", "unknown", or "not specified", when a field is absent.
- Skip navigation, footer, generic page descriptions, and unrelated blurbs."""


def _truncate_for_llm(markdown: str, page_url: str) -> str:
    header = f"Page URL: {page_url}\n\n"
    body = markdown or ""
    max_chars = 60_000 if (settings.LLM_PROVIDER or "").lower() == "ollama" else 120_000
    if len(body) <= max_chars:
        return header + body
    head = body[:50_000]
    tail = body[-8_000:]
    omitted = len(body) - max_chars
    return header + head + f"\n\n[... {omitted:,} chars omitted ...]\n\n" + tail


def _extract_json_array(text: str) -> Optional[list]:
    t = (text or "").strip()
    if not t:
        return None
    try:
        data = json.loads(t)
        return data if isinstance(data, list) else None
    except json.JSONDecodeError:
        pass
    if "```" in t:
        chunk = t
        if "```json" in chunk:
            chunk = chunk.split("```json", 1)[-1].split("```", 1)[0]
        else:
            chunk = chunk.split("```", 1)[-1].split("```", 1)[0]
        try:
            data = json.loads(chunk.strip())
            return data if isinstance(data, list) else None
        except json.JSONDecodeError:
            pass
    start, end = t.find("["), t.rfind("]")
    if start != -1 and end > start:
        try:
            data = json.loads(t[start : end + 1])
            return data if isinstance(data, list) else None
        except json.JSONDecodeError:
            return None
    return None


_NOTICE_HEADING_RE = re.compile(r"^\s{0,3}#{3,6}\s+(.+?)\s*$")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_PROCUREMENT_HINT_RE = re.compile(
    r"\b(tender|procurement|rfp|rfq|quotation|proposal|tor|terms of reference|consulting|consultancy)\b",
    re.IGNORECASE,
)


def _heuristic_rows_from_markdown(markdown: str, page_url: str) -> List[ListingRowV1]:
    """Fallback for simple procurement pages where notices are Markdown headings."""
    rows: List[ListingRowV1] = []
    seen_titles: set[str] = set()
    lines = (markdown or "").splitlines()

    for idx, line in enumerate(lines):
        match = _NOTICE_HEADING_RE.match(line)
        if not match:
            continue

        title = re.sub(r"\s+", " ", match.group(1)).strip(" -*")
        if not title or not _PROCUREMENT_HINT_RE.search(title):
            continue

        normalized_title = title.lower()
        if normalized_title in seen_titles:
            continue

        detail_url = None
        snippet = None
        for next_line in lines[idx + 1 : idx + 5]:
            candidate = next_line.strip()
            if not candidate:
                continue
            if _NOTICE_HEADING_RE.match(candidate):
                break
            link_match = _MARKDOWN_LINK_RE.search(candidate)
            if link_match:
                snippet = re.sub(r"\s+", " ", link_match.group(1)).strip()
                detail_url = urljoin(page_url, link_match.group(2).strip())
                break
            snippet = re.sub(r"\s+", " ", candidate).strip()
            break

        seen_titles.add(normalized_title)
        rows.append(
            ListingRowV1(
                title=title,
                reference=None,
                publication_date=None,
                deadline=None,
                detail_url=detail_url,
                country=None,
                snippet=snippet,
            )
        )

    return rows


class ListingStructureAgent:
    """Turns crawl markdown into :class:`ListingRowV1` rows."""

    def __init__(self) -> None:
        self.llm = get_chat_llm(temperature=0)

    async def structure_listing(self, markdown: str, page_url: str) -> List[ListingRowV1]:
        user = _truncate_for_llm(markdown, page_url)
        llm_lbl = active_llm_label()
        pipeline_tty(f"[AGENT1] .... ↓ structure_llm ({llm_lbl})")
        logger.info(
            "ListingStructureAgent: calling LLM (markdown_chars=%s, prompt_chars≈%s)",
            len(markdown or ""),
            len(user),
        )
        timeout = getattr(settings, "AGENT1_STRUCTURE_LLM_TIMEOUT_SEC", 300)
        t0 = time.perf_counter()
        try:
            msg = HumanMessage(content=f"{_SYSTEM}\n\n--- CONTENT ---\n\n{user}")
            coro = self.llm.ainvoke([msg])
            response = await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            logger.error("ListingStructureAgent: LLM timeout after %ss", timeout)
            pipeline_tty(f"[AGENT1] .... ✗ timeout after {timeout}s")
            return []
        except Exception as exc:
            logger.error("ListingStructureAgent: LLM error: %s", exc)
            pipeline_tty(f"[AGENT1] .... ✗ error: {exc}")
            return []

        raw = (getattr(response, "content", None) or "").strip()
        extra = getattr(response, "additional_kwargs", None) or {}
        for key in ("answer", "response", "output"):
            chunk = extra.get(key)
            if isinstance(chunk, str) and chunk.strip():
                raw = chunk.strip()
                break

        items = _extract_json_array(raw)
        if not items:
            logger.warning("ListingStructureAgent: no JSON array in model output (first 400 chars): %s", raw[:400])
            fallback_rows = _heuristic_rows_from_markdown(markdown, page_url)
            if fallback_rows:
                logger.info(
                    "ListingStructureAgent: heuristic fallback parsed %s row(s)",
                    len(fallback_rows),
                )
                pipeline_tty(
                    f"[AGENT1] .... ✓ {len(fallback_rows)} heuristic row(s) | ⏱: {time.perf_counter() - t0:.1f}s"
                )
                return fallback_rows
            pipeline_tty(f"[AGENT1] .... ✗ no JSON array | ⏱: {time.perf_counter() - t0:.1f}s")
            return []

        rows: List[ListingRowV1] = []
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            try:
                row = ListingRowV1(
                    title=str(item.get("title") or "").strip(),
                    reference=_s(item.get("reference")),
                    publication_date=_s(item.get("publication_date")),
                    deadline=_s(item.get("deadline")),
                    detail_url=_s(item.get("detail_url")),
                    country=_s(item.get("country")),
                    snippet=_s(item.get("snippet")),
                )
                if row.title:
                    rows.append(row)
            except Exception as exc:
                logger.debug("ListingStructureAgent: skip row %s: %s", i, exc)
                continue

        logger.info("ListingStructureAgent: parsed %s row(s)", len(rows))
        pipeline_tty(
            f"[AGENT1] .... ✓ {len(rows)} row(s) | ⏱: {time.perf_counter() - t0:.1f}s"
        )
        return rows


def _s(v: Any) -> Optional[str]:
    if v is None:
        return None
    t = str(v).strip()
    return t if t else None
