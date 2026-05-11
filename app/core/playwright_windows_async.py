"""Windows + uvicorn: reload/workers force SelectorEventLoop, which cannot spawn Playwright's driver.

Run the coroutine on a dedicated thread with a new Proactor loop instead.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Awaitable, TypeVar

_T = TypeVar("_T")


def needs_windows_playwright_thread() -> bool:
    if sys.platform != "win32":
        return False
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    return not isinstance(loop, asyncio.ProactorEventLoop)


def run_coro_on_windows_playwright_loop(coro: Awaitable[_T]) -> _T:
    """Run *coro* to completion on a fresh Proactor loop (call from a worker thread)."""
    from app.core.asyncio_windows import apply as _apply_windows_asyncio_policy

    _apply_windows_asyncio_policy()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()
        asyncio.set_event_loop(None)
