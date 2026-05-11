"""Windows-only asyncio policy for subprocess-based libraries (Playwright).

On macOS and Linux, `apply()` does nothing — safe to import from shared repos.

On Windows, SelectorEventLoop does not implement subprocess transport; Playwright
then fails with NotImplementedError in create_subprocess_exec. Proactor does.
Call apply() once at process startup before the event loop is created.
"""

from __future__ import annotations

import asyncio
import sys


def apply() -> None:
    """No-op except on Windows, where Proactor is required for Playwright."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
