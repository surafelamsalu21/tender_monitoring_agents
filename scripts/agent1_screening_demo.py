#!/usr/bin/env python3
"""
Run Agent 1 (real LLM) on a text file — no API auth, no DB.

Usage (from repo root, with .env loaded):

  ./.venv/bin/python scripts/agent1_screening_demo.py path/to/page.md

Requires the same LLM config as the app: LLM_PROVIDER=openai + OPENAI_API_KEY, or LLM_PROVIDER=ollama (+ Ollama daemon and OLLAMA_MODEL).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent 1 screening demo on a markdown/text file")
    parser.add_argument("file", type=Path, help="Path to scraped markdown or pasted notices")
    parser.add_argument("--page-url", default="", help="Optional URL context for the model")
    args = parser.parse_args()

    if not args.file.is_file():
        print(f"Not a file: {args.file}", file=sys.stderr)
        sys.exit(1)

    text = args.file.read_text(encoding="utf-8")
    if args.page_url:
        text = f"Page URL (context): {args.page_url}\n\n{text}"

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    async def run():
        from app.agents.agent1 import TenderExtractionAgent

        agent = TenderExtractionAgent()
        return await agent.extract_and_screen_opportunities(page_content=text)

    items = asyncio.run(run())

    for i, item in enumerate(items, 1):
        scr = item.get("screening") or {}
        print(f"\n--- Opportunity {i} ---")
        print(f"title: {item.get('title')}")
        print(f"url: {item.get('url')}")
        print(f"yes_count: {scr.get('yes_count')}  passes_filter (recommended): {scr.get('passes_filter')}")

    print("\nJSON:\n")
    print(json.dumps(items, indent=2, default=str))


if __name__ == "__main__":
    main()
