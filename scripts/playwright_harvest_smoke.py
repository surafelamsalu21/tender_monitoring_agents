#!/usr/bin/env python3
"""Run Playwright harvest for one monitored page id (for testing real logins).

  python scripts/playwright_harvest_smoke.py <page_id>

Requires: pip install playwright && playwright install chromium
Put credentials in .env (e.g. CRAWL_AUTH_USERNAME / CRAWL_AUTH_PASSWORD) and
set auth_login_url / selectors on the page or use PLAYWRIGHT_* settings in .env.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# project root on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal, create_tables
from app.crawl.playwright_harvest import harvest_with_playwright
from app.repositories.page_repository import PageRepository


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("page_id", type=int, help="Monitored page PK")
    args = parser.parse_args()

    create_tables()
    db = SessionLocal()
    try:
        repo = PageRepository()
        page = repo.get_page_by_id(db, args.page_id)
        if not page:
            print(f"No monitored page id={args.page_id}")
            sys.exit(1)
        print(f"Harvesting: {page.name} ({page.url}) strategy={page.crawl_strategy}")
        result = await harvest_with_playwright(page)
        print("status:", result.status)
        if result.error:
            print("error:", result.error)
        print("links:", len(result.listing_urls))
        text = result.markdown or ""
        print("--- body (first 4000 chars) ---")
        print(text[:4000])
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
