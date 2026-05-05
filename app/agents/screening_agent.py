"""
Backward-compatible name for Agent 1.

The screening checklist implementation lives in ``agent1.TenderExtractionAgent``.
"""
from .agent1 import TenderExtractionAgent as ScreeningExtractionAgent

__all__ = ["ScreeningExtractionAgent"]
