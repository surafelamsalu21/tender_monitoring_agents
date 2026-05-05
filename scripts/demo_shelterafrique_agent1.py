#!/usr/bin/env python3
"""
Smoke-test Shelter Afrique listing -> generic listing prep -> Agent 1 -> optional expiry gate.

Uses the same **generic** harvest → Agent 1 path as the scheduler (markdown + URL supplement from
links/HTML, not hostname-specific code).

Usage (from repo root, `.venv` active):

  LLM_PROVIDER=ollama ./.venv/bin/python scripts/demo_shelterafrique_agent1.py

Listing: https://www.shelterafrique.org/en/tenders
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LISTING_URL = "https://www.shelterafrique.org/en/tenders"


async def main() -> None:
    from app.agents.agent1 import TenderExtractionAgent
    from app.core.config import settings
    from app.crawl.orchestrator import _flatten_scrape_links
    from app.services.scraper import TenderScraper
    from app.utils.listing_prep import dual_markdown_for_agent1_and_expiry
    from app.utils.tender_deadline_gate import filter_expired_agent1_items

    async with TenderScraper() as scraper:
        r = await scraper.scrape_page(LISTING_URL)
    if r.get("status") != "success":
        print("SCRAPE_FAILED", r.get("error"))
        sys.exit(1)

    md = r.get("markdown") or ""
    links = _flatten_scrape_links(r.get("links"))
    payload, full_for_expiry = dual_markdown_for_agent1_and_expiry(
        LISTING_URL,
        md,
        r.get("links"),
        html=r.get("html"),
    )
    expiry_md = full_for_expiry if full_for_expiry is not None else md

    items = await TenderExtractionAgent().extract_and_screen_opportunities(page_content=payload)

    print("scrape_markdown_chars:", len(md))
    print("flattened_crawl_links:", len(links))
    print("after_agent1_validation:", len(items))

    expiry_dropped = 0
    if settings.SKIP_EXPIRED_AFTER_AGENT1:
        kept, expiry_dropped = filter_expired_agent1_items(items, expiry_md)
        print(
            "after_expiry_gate (SKIP_EXPIRED_AFTER_AGENT1=true, full scrape markdown for dates):",
            len(kept),
            "dropped_past_or_closed:",
            expiry_dropped,
        )
        items = kept
    else:
        print("after_expiry_gate: skipped (SKIP_EXPIRED_AFTER_AGENT1=false)")
    print("final_rows_printed_below:", len(items))
    for it in items:
        sc = it.get("screening") or {}
        print(
            json.dumps(
                {
                    "title": it.get("title"),
                    "url": it.get("url"),
                    "yes_count": sc.get("yes_count"),
                    "passes_filter": sc.get("passes_filter"),
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
