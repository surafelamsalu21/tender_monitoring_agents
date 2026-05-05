"""Fast local step 2: compact screening on extracted rows only (no full page)."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.llm_json_io import extract_message_text, parse_json_array
from app.core.config import settings
from app.core.llm_factory import get_chat_llm

logger = logging.getLogger(__name__)

_SCREEN_SYSTEM = """You screen procurement opportunities for Precise, a development consulting firm.
Input is a JSON array of items (title, url, date, description). Output ONLY a JSON array of the SAME length and order.
Each output object:
{"title": same as input, "url": same as input, "yes_count": 0-5, "passes": boolean (true if yes_count>=3), "unrelated": boolean, "flags": {"mission_alignment":bool,"sector_relevance":bool,"activity_fit":bool,"geographic_fit":bool,"eligibility":bool}}

Screening rule:
- A relevant opportunity must score at least 3 YES out of 5.
- Set passes=true only when yes_count>=3. Set passes=false for 0, 1, or 2 YES.

How to score honestly:
- Each criterion is YES ONLY when there is concrete textual evidence in the title or description.
- Do not assume or infer. If the text is silent on a criterion, it is NO.
- The buyer being a development organization (UN/UNDP/AfDB/etc.) does NOT make any criterion YES on its own.

Step 1 criteria:

1. mission_alignment:
   YES if it relates to economic development of firms, farms, or industries (SME growth, enterprise development, farm productivity, industrial development, value chains, market systems, access to finance for businesses, agribusiness, energy for productive use).
   NO for: pure goods supply (vehicles, spare parts, equipment, calibration systems, office supplies), construction/infrastructure (water/sanitation/WASH, roads, buildings), media/communications (graphic design, videography, photography), and generic services for the buyer (security, cleaning, catering, recruitment, audit, translation, printing).

2. sector_relevance:
   YES if the WORK ITSELF is connected to at least one of:
   - Off-grid energy
   - Agriculture / agribusiness
   - Health electrification
   - Cross-cutting (finance, climate, SMEs)
   NO if the work is in WASH/water/sanitation infrastructure, civil works, generic IT, humanitarian logistics, peacekeeping, media production, or education unrelated to enterprise/finance.

3. activity_fit:
   YES if the CORE DELIVERABLE is one of:
   - Private sector development / SMEs
   - Business Development Services (BDS)
   - Access to finance
   - Value chain / market systems
   - Climate-smart / regenerative agriculture
   - Productive Use of Energy (PUE)
   - Research / surveys / studies (on a topic in criterion 2's sectors)
   - Capacity building / training (in criterion 2's sectors — NOT graphic design, photography, communications, generic IT, language, or driving)
   - Policy / stakeholder engagement
   NO for: pure goods supply/delivery/installation, construction/civil works, graphic design, videography, photography, film/media production, recruitment/HR, audit/accounting, legal drafting, translation, printing, vehicle supply, security, cleaning.

4. geographic_fit:
   YES only when the WORK ITSELF is in Ethiopia OR East Africa (Ethiopia, Kenya, Uganda, Tanzania, Rwanda, Burundi, South Sudan, Somalia, Djibouti, Eritrea, Sudan).
   Africa-wide opportunities are YES only if Ethiopia or East Africa is explicitly eligible/included.
   NO for work in: Asia, Pacific Islands (e.g. Papua New Guinea), Americas, Caribbean, Europe (e.g. Italy/Brindisi), Middle East, or West/Central/Southern/North Africa only (e.g. Nigeria, Ghana, Senegal, Egypt, South Africa, DRC).
   If the title or description names a non-East-African country/city as the place of work, geographic_fit is NO regardless of who the buyer is.

5. eligibility:
   YES if for-profit consulting firms are eligible OR eligibility is unclear (and not explicitly restricted).
   NO if explicitly restricted to NGOs only, UN agencies only, government only, universities only, or individuals only.

Set unrelated=true only for spam or clearly not a real procurement notice.
No markdown. No extra keys."""


def _chunk(items: List[Dict[str, Any]], n: int) -> List[List[Dict[str, Any]]]:
    return [items[i : i + n] for i in range(0, len(items), n)]


def _merge_legacy_screening(
    item: Dict[str, Any],
    row: Dict[str, Any],
) -> Dict[str, Any]:
    """Map flat screening row to legacy screening dict for DB/workflow."""
    flags = row.get("flags") or {}
    unrelated = bool(row.get("unrelated") or row.get("unrelated_to_precise_scope"))

    step1 = {
        "mission_alignment": bool(flags.get("mission_alignment")),
        "sector_relevance": bool(flags.get("sector_relevance")),
        "activity_fit": bool(flags.get("activity_fit")),
        "geographic_fit": bool(flags.get("geographic_fit")),
        "eligibility_quick_check": bool(flags.get("eligibility", flags.get("eligibility_quick_check"))),
    }
    yes_llm = row.get("yes_count")
    if isinstance(yes_llm, int) and 0 <= yes_llm <= 5:
        yes_count = yes_llm
    else:
        yes_count = sum(1 for v in step1.values() if v)

    passes = bool(row.get("passes", yes_count >= 3))

    date_s = str(item.get("date") or "").strip()
    screening: Dict[str, Any] = {
        "unrelated_to_precise_scope": unrelated,
        "step1": step1,
        "yes_count": yes_count,
        "passes_filter": passes and not unrelated,
        "step2": {
            "opportunity_characteristics": [],
            "strategic_signals": [],
            "potential_concerns": [],
        },
        "step3": {
            "title": item.get("title", ""),
            "source": "",
            "country": "",
            "type": "other",
            "deadline": date_s[:64] if date_s else "",
            "estimated_budget": None,
            "link": item.get("url", ""),
        },
        "screening_version": "v2_fast_local",
    }
    return {
        "title": item["title"],
        "url": item["url"],
        "date": item.get("date"),
        "description": item.get("description", ""),
        "screening": screening,
        "date_status": "unknown",
    }


class TenderScreeningAgent:
    """Batched LLM calls: extracted rows → same rows with screening filled."""

    def __init__(self) -> None:
        self.llm = get_chat_llm(temperature=0.05)

    async def screen_items(
        self,
        items: List[Dict[str, Any]],
        *,
        keyword_hints: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        if not items:
            return []

        batch_size = int(getattr(settings, "AGENT1_FAST_SCREEN_BATCH", 5) or 5)
        batch_size = max(1, min(batch_size, 12))
        timeout = int(getattr(settings, "AGENT1_FAST_STEP_TIMEOUT_SEC", 300) or 300)

        hint = ""
        if keyword_hints:
            h = ", ".join(str(x).strip() for x in keyword_hints[:20] if str(x).strip())
            if h:
                hint = f"\nFirm keyword hints (weak tie-break): {h}\n"

        merged: List[Dict[str, Any]] = []
        for batch_idx, batch in enumerate(_chunk(items, batch_size)):
            payload = [
                {
                    "title": b["title"],
                    "url": b["url"],
                    "date": b.get("date") or "",
                    "description": (b.get("description") or "")[:1200],
                }
                for b in batch
            ]
            user = f"""{hint}INPUT (screen each, preserve order, {len(payload)} items):

{json.dumps(payload, ensure_ascii=False)}

Output JSON array only, length {len(payload)}."""

            prompt_len = len(_SCREEN_SYSTEM) + len(user)
            logger.info(
                "TenderScreeningAgent: batch %s size=%s prompt≈%s chars timeout=%ss",
                batch_idx + 1,
                len(batch),
                prompt_len,
                timeout,
            )
            try:
                task = self.llm.ainvoke(
                    [
                        SystemMessage(content=_SCREEN_SYSTEM),
                        HumanMessage(content=user),
                    ]
                )
                response = await asyncio.wait_for(task, timeout=timeout)
                raw = extract_message_text(response)
                parsed = parse_json_array(raw)
            except asyncio.TimeoutError:
                logger.error("TenderScreeningAgent: batch %s timeout", batch_idx + 1)
                parsed = []
            except Exception as exc:
                logger.error("TenderScreeningAgent batch failed: %s", exc)
                parsed = []

            by_url: Dict[str, Dict[str, Any]] = {}
            by_title: Dict[str, Dict[str, Any]] = {}
            for p in parsed:
                if not isinstance(p, dict):
                    continue
                u = str(p.get("url", "")).strip()
                if u:
                    by_url[u] = p
                t = str(p.get("title", "")).strip().lower()
                if t:
                    by_title[t] = p

            for it in batch:
                row = by_url.get(it["url"])
                if row is None:
                    row = by_title.get(str(it.get("title", "")).strip().lower())
                if row is None:
                    row = {}
                merged.append(_merge_legacy_screening(it, row))

        return merged
