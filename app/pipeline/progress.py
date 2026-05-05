"""TTY-friendly progress lines (stacked like Crawl4AI) for long-running pipelines."""
from __future__ import annotations

import logging

from app.core.config import settings

_log = logging.getLogger(__name__)


def pipeline_tty(msg: str) -> None:
    """
    Echo one progress line to the terminal.

    When ``PIPELINE_TTY_PROGRESS`` is False, the same line goes to the logger at INFO
    (for log files / non-interactive runs).
    """
    if getattr(settings, "PIPELINE_TTY_PROGRESS", True):
        print(msg, flush=True)
    else:
        _log.info("%s", msg)


def active_llm_label() -> str:
    prov = (settings.LLM_PROVIDER or "").lower().strip()
    if prov == "ollama":
        return f"ollama/{settings.OLLAMA_MODEL}"
    if prov == "openai":
        return f"openai/{settings.OPENAI_MODEL}"
    return prov or "llm"
