"""
Source adapter scaffold for opportunity ingestion.

Phase 1 purpose: provide a consistent adapter interface that can later be
implemented for authenticated and unauthenticated opportunity sources.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Protocol


@dataclass
class SourceConfig:
    source_id: str
    display_name: str
    base_url: str
    requires_auth: bool = False
    enabled: bool = False


class SourceAdapter(Protocol):
    source_id: str

    async def fetch_raw_opportunities(self, source_config: SourceConfig) -> List[Dict[str, Any]]:
        ...

    def normalize_to_screening_input(self, raw_item: Dict[str, Any]) -> Dict[str, Any]:
        ...


class PlaceholderSourceAdapter:
    """
    Non-functional placeholder implementation.
    Keeps the pipeline ready for source onboarding without breaking runtime.
    """

    def __init__(self, source_id: str):
        self.source_id = source_id

    async def fetch_raw_opportunities(self, source_config: SourceConfig) -> List[Dict[str, Any]]:
        return []

    def normalize_to_screening_input(self, raw_item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "title": raw_item.get("title", ""),
            "url": raw_item.get("url", ""),
            "description": raw_item.get("description", ""),
            "source": raw_item.get("source", self.source_id),
            "country": raw_item.get("country"),
            "type": raw_item.get("type"),
            "deadline": raw_item.get("deadline"),
            "estimated_budget": raw_item.get("estimated_budget"),
            "raw_payload": raw_item,
        }


SOURCE_CONFIGS: Dict[str, SourceConfig] = {
    "linkedin": SourceConfig(
        source_id="linkedin",
        display_name="LinkedIn posts",
        base_url="https://www.linkedin.com/",
        requires_auth=True,
    ),
    "rfxnow_world_bank": SourceConfig(
        source_id="rfxnow_world_bank",
        display_name="RFX Now (World Bank)",
        base_url="https://wbgeprocure-rfxnow.worldbank.org/",
        requires_auth=True,
    ),
    "eu_funding_portal": SourceConfig(
        source_id="eu_funding_portal",
        display_name="EU Funding & Tenders",
        base_url="https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/home",
        requires_auth=False,
    ),
    "usaid": SourceConfig(
        source_id="usaid",
        display_name="USAID",
        base_url="https://www.usaid.gov/",
        requires_auth=False,
    ),
    "gates_foundation": SourceConfig(
        source_id="gates_foundation",
        display_name="Gates Foundation",
        base_url="https://www.gatesfoundation.org/",
        requires_auth=False,
    ),
    "agra": SourceConfig(
        source_id="agra",
        display_name="AGRA",
        base_url="https://agra.org/",
        requires_auth=False,
    ),
    "merkato": SourceConfig(
        source_id="merkato",
        display_name="Merkato",
        base_url="https://merkato.com/",
        requires_auth=False,
    ),
}


SOURCE_ADAPTERS: Dict[str, SourceAdapter] = {
    key: PlaceholderSourceAdapter(source_id=key) for key in SOURCE_CONFIGS
}
