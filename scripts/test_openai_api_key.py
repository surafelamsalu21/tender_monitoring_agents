#!/usr/bin/env python3
"""Ping OpenAI with a tiny chat completion (gpt-4o-mini) to verify OPENAI_API_KEY.

  set OPENAI_API_KEY=sk-...   # Windows PowerShell: $env:OPENAI_API_KEY="sk-..."
  python scripts/test_openai_api_key.py

Requires: pip install openai  (already pulled in via langchain-openai in this repo)
"""
from __future__ import annotations

import os
import sys

# Change here if you want another small model (e.g. "o4-mini").
MODEL = "gpt-4o-mini"


def main() -> None:
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        print("ERROR: OPENAI_API_KEY is empty or not set.", file=sys.stderr)
        sys.exit(1)

    try:
        from openai import OpenAI
    except ImportError:
        print("ERROR: install the SDK: pip install openai", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(api_key=key)
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": 'Reply with exactly one word: "pong".'}],
            max_tokens=32,
        )
    except Exception as e:
        print("ERROR: API call failed:", e, file=sys.stderr)
        sys.exit(1)

    text = (resp.choices[0].message.content or "").strip()
    print("OK — key works.")
    print("  model:", MODEL)
    print("  reply:", repr(text))


if __name__ == "__main__":
    main()
