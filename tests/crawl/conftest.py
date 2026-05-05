"""Allow `tests/crawl` to import `app.services.scraper` in environments without crawl4ai."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock


def pytest_configure(config) -> None:
    if "crawl4ai" in sys.modules:
        return
    cm = MagicMock()
    cm.AsyncWebCrawler = MagicMock
    sys.modules["crawl4ai"] = cm
