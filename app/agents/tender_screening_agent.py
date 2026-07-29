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
from app.utils.geo_filter import geo_priority

logger = logging.getLogger(__name__)

_SCREEN_SYSTEM = """You screen procurement opportunities for Precise, a development consulting firm.
Input is a JSON array of items (title, url, date, description). Output ONLY a JSON array of the SAME length and order.
Each output object:
{"title": same as input, "url": same as input, "yes_count": 0-5, "passes": boolean (true if yes_count>=3), "unrelated": boolean, "engagement": "advisory_only"|"supply_only"|"advisory_and_supply_mixed", "flags": {"mission_alignment":bool,"sector_relevance":bool,"activity_fit":bool,"geographic_fit":bool,"eligibility":bool}}

Advisory vs supply (for engagement and for scoring):
- Advisory / consulting: TOR/ToR, TA, studies/surveys, BDS, MEL, strategy, training on sectors below, policy dialogue — substantive analytical or capacity-building work, not only delivering goods.
- Supply / goods-heavy: primary or sole deliverable is equipment, vehicles, commodities, bulk licensing, materials, etc., with no substantive advisory line items.
- Mixed: both advisory and supply appear — set mission_alignment and activity_fit YES if the advisory part alone would pass; do not fail only because goods are also listed. engagement must be advisory_and_supply_mixed.
- Supply-only notices: engagement supply_only; mission_alignment and activity_fit should normally be NO unless the text is mislabeled.

CRITICAL — "Productive Use of Energy (PUE)" vs water projects:
- PUE = using solar/off-grid/clean energy to POWER productive activities (solar-powered pumps, agro-processing via renewable energy, SME machinery on clean electricity). The ENERGY component is central.
- "Productive Use of Water" / water wells / boreholes / irrigation canals / rural water supply / water resilience = WATER/WASH sector, NOT PUE. Score such items sector_relevance=false, mission_alignment=false.
- Construction supervision of wells/boreholes/water infrastructure = civil-works supervision = NOT advisory consulting in Precise's sectors.

Screening rule:
- A relevant opportunity must score at least 3 YES out of 5.
- Set passes=true only when yes_count>=3. Set passes=false for 0, 1, or 2 YES.
- The `flags` object is what actually decides the outcome — it is re-checked downstream, so set each flag to what the text supports rather than working backwards from a desired verdict.
- Three flags are mandatory: geographic_fit, mission_alignment, and eligibility. If any of them is false the opportunity is rejected regardless of the others.
- At least one of sector_relevance or activity_fit must also be true. A notice that is merely "a consultancy in Ethiopia" with no identifiable sector or advisory activity does NOT qualify.

How to score honestly:
- Each criterion is YES ONLY when there is concrete textual evidence in the title or description.
- Do not assume or infer. If the text is silent on a criterion, it is NO.
- The buyer being a development organization (UN/UNDP/AfDB/etc.) does NOT make any criterion YES on its own.

Step 1 criteria:

1. mission_alignment (MANDATORY — score strictly):
   YES if the core deliverable directly helps firms, farms, or industries operate better, grow, or access markets/finance: SME growth, enterprise development, farm productivity, industrial development, value chains, market systems, access to finance for businesses, agribusiness, energy for productive use, BDS, TA/TOR/study/MEL/strategy/training/policy — ONLY in those economic-development contexts.
   POLICY ADVISORY ALLOWANCE (EA ONLY): For Ethiopia/East-Africa opportunities, treat mission_alignment as YES when the core advisory scope is explicitly about economic policy, financial architecture reform, or public financial management reform with institutional advisory/coordination support (not supply/construction and not generic admin support).
   NO for: pure goods supply (vehicles, tools, equipment, drones, cameras, spare parts, office supplies) with no substantive advisory component; construction/infrastructure (WASH, roads, buildings, wells, boreholes, water infrastructure, renovation); construction supervision/works supervision/site engineering oversight (even when called "consultancy"); monitoring/verification/TPM of water, WASH, infrastructure, or humanitarian projects; "Productive Use of Water" or rural water supply projects (NOT the same as PUE); media/communications; generic buyer services (security, cleaning, catering, recruitment, audit, translation, printing); transport regulation/enforcement; legal/justice sector work; governance reform not targeting private sector; social/inclusion programmes without enterprise focus; environmental/biodiversity work with no private sector lens; general programme evaluations of "development" or "resilience" or WASH programmes where the programme subject is NOT in energy/agri/SME/climate; architecture or construction supervision.
   KEY TEST: "Does the core deliverable help firms, farms, or industries?" If NO → mission_alignment=false.

2. sector_relevance:
   YES if the WORK ITSELF is connected to at least one of:
   - Off-grid energy / solar / mini-grid / distributed renewable / energy access
   - Agriculture / agribusiness (helping FARMERS and AGRIBUSINESSES — NOT water supply infrastructure)
   - Health electrification (solar for clinics, off-grid cold chain)
   - Cross-cutting: SME finance, climate finance, blended finance, MSME/enterprise development, market systems
   POLICY ADVISORY ALLOWANCE (EA ONLY): For Ethiopia/East-Africa opportunities, institutional advisory work on economic policy, macro-financial architecture, or public financial management reform counts as sector_relevance=YES.
   WATER/WASH IS NOT A YES SECTOR: Rural water supply, water resilience, boreholes, wells, irrigation infrastructure, "water for food security", WASH = sector_relevance=false.
   GENERIC "DEVELOPMENT" IS NOT A SECTOR: If the notice only says "development programme", "resilience project", "rural development" without specifying energy/agri/SME/climate, score NO.
   GENERIC ENVIRONMENT IS NOT A SECTOR: EIA/environmental assessment for infrastructure = NO. Biodiversity without enterprise link = NO.
   NO if the work is in WASH/water/sanitation/rural water supply, civil works/construction, well/borehole drilling, humanitarian logistics, peacekeeping, generic IT, media production, transport, legal, governance, or education unrelated to enterprise/finance.

3. activity_fit:
   YES ONLY if the CORE DELIVERABLE (or substantive advisory portion of a mixed notice) is one of the following AND is on a topic relevant to criterion 2 sectors (energy, agriculture, finance, SMEs, climate):
   - Private sector development / SMEs; Business Development Services (BDS); Access to finance; Value chain / market systems; Climate-smart / regenerative agriculture; Productive Use of Energy (PUE — energy, not water)
   - Research / surveys / studies ON CRITERION-2 TOPICS (not WASH, rural water, transport, inclusion, gender, biodiversity, generic development)
   - Capacity building / training ON CRITERION-2 TOPICS
   - Policy / stakeholder engagement ON CRITERION-2 TOPICS
   - TOR-led consulting, TA, MEL, strategy ON CRITERION-2 TOPICS
   POLICY ADVISORY ALLOWANCE (EA ONLY): In Ethiopia/East-Africa, institutional advisory/coordination assignments focused on economic policy, financial architecture, or public financial management reform can be activity_fit=YES.
   EVALUATION/TRACER/VERIFICATION RULE: An impact evaluation, tracer study, independent verification, baseline, or third-party monitoring (TPM) is ONLY YES if the text EXPLICITLY states the programme being evaluated is in energy, agriculture, SME/enterprise, or climate. "Development programme", "resilience programme", "rural programme", "water project" without sector specificity = NO.
   CONSTRUCTION SUPERVISION RULE: Any "consultancy for construction supervision", "works supervision", "engineering oversight", "site supervision" = activity_fit=false regardless of project name.
   WATER MONITORING RULE: Third-party monitoring (TPM), verification, or M&E of a water/WASH/rural-water/well-drilling project = activity_fit=false.
   NO for: pure goods supply/delivery/installation; construction/civil works/well drilling; construction or works supervision; monitoring/verification/TPM of WASH/water/infrastructure/humanitarian projects; graphic design, videography, photography, film/media; recruitment/HR, audit/accounting, legal drafting, translation, printing; vehicle supply, security, cleaning; axle-load/road-transport enforcement; legal aid/rule-of-law; donor portfolio evaluations on social/WASH/generic topics; environmental EIA for infrastructure.

4. geographic_fit:
   YES only when the WORK ITSELF is in one or more of these countries:
   Burundi, Comoros, Djibouti, Eritrea, Ethiopia, Kenya, Rwanda, Somalia, South Sudan, Sudan, Tanzania, Uganda, Seychelles, Madagascar.
   Ethiopia is the PRIMARY focus. East Africa is the SECONDARY focus.
   Africa-wide opportunities are YES only if at least one listed country is explicitly eligible/included.
   NO for work in:
   - Europe: Montenegro, Albania, Serbia, Italy, France, Germany, Spain, UK, Brindisi, or any other European country/city
   - Asia: Sri Lanka, India, Pakistan, Bangladesh, Nepal, Vietnam, Philippines, Indonesia, China, or any other Asian country
   - Pacific: Papua New Guinea, Australia, Fiji, or any other Pacific country
   - Americas: Brazil, Colombia, Mexico, Haiti, United States, Canada, or any other American country
   - Middle East: Yemen, Iraq, Syria, Saudi Arabia, UAE, Jordan, or any other Middle Eastern country
   - West Africa: Nigeria, Ghana, Senegal, Côte d'Ivoire, Mali, or similar
   - Central Africa: DRC, Cameroon, Congo, or similar
   - Southern Africa: South Africa, Zimbabwe, Zambia, Mozambique, Angola, or similar
   - North Africa: Egypt, Libya, Morocco, Algeria, Tunisia, or similar
   STRICT: If the title or description names a non-East-African country/city as the WORK location, geographic_fit is NO regardless of who the buyer is. Do NOT set geographic_fit=true merely because the procurement organization is based in East Africa — what matters is WHERE THE WORK IS DONE.
   geographic_fit is mandatory for final passing.

5. eligibility:
   YES if for-profit consulting firms are eligible, OR eligibility is unclear (not explicitly restricted).
   NO if restricted to: NGOs only, UN agencies only, government only, universities only, or INDIVIDUALS only.
   CRITICAL: "Individual Consultant", "Individual Contractor", "National Individual Consultant", "International Individual Consultant" roles are for INDIVIDUAL PERSONS ONLY, not firms. Score eligibility=false for ALL such roles — a consulting firm cannot apply.
   YES examples: RFP to firms/companies, eligibility not mentioned.
   NO examples: "Individual consultant assignment", "Individual contractor", "National consultant (individual)".

engagement (required on every row):
- advisory_only — advisory/consulting is the core; goods minor or absent.
- supply_only — supply/goods is the core; no substantive TOR/TA/study/BDS/MEL/strategy/training/policy deliverables.
- advisory_and_supply_mixed — both substantive advisory and supply/goods are in scope.

Set unrelated=true only for spam or clearly not a real procurement notice.
Do not invent or expand the title/description: if the row looks like a bogus placeholder (e.g. only a URL slug, error-page text), set unrelated=true and passes=false.
No markdown. Only these keys per object: title, url, yes_count, passes, unrelated, engagement, flags."""


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
    # Always derive the count from the flags. The model's own arithmetic drifts
    # from the flags it just set, which used to let a row through on a claimed
    # yes_count while the individual criteria said otherwise.
    yes_count = sum(1 for v in step1.values() if v)
    yes_llm = row.get("yes_count")
    if isinstance(yes_llm, int) and yes_llm != yes_count:
        logger.info(
            "Screening: model yes_count=%s disagrees with flags (%s) for %r — using flags",
            yes_llm,
            yes_count,
            str(item.get("title") or "")[:80],
        )

    # Derive the verdict too, rather than trusting row["passes"].
    # Geography, mission alignment and firm eligibility are mandatory; the
    # sector/activity requirement is configurable because it lifts the effective
    # bar from 3-of-5 to 4-of-5.
    geographic_fit = bool(step1.get("geographic_fit"))
    passes = (
        yes_count >= 3
        and geographic_fit
        and bool(step1.get("mission_alignment"))
        and bool(step1.get("eligibility_quick_check"))
    )
    if passes and getattr(settings, "SCREENING_REQUIRE_SECTOR_OR_ACTIVITY", True):
        passes = bool(step1.get("sector_relevance")) or bool(step1.get("activity_fit"))

    engagement_raw = str(row.get("engagement") or "").strip().lower().replace("-", "_")
    engagement_token: Optional[str] = None
    if engagement_raw in ("advisory_only", "advisory"):
        engagement_token = "engagement_advisory_only"
    elif engagement_raw in ("supply_only", "supply"):
        engagement_token = "engagement_supply_only"
    elif engagement_raw in (
        "advisory_and_supply_mixed",
        "mixed",
        "advisory_and_supply",
    ):
        engagement_token = "engagement_advisory_and_supply_mixed"

    strategic_signals: List[str] = []
    if engagement_token:
        strategic_signals.append(engagement_token)

    date_s = str(item.get("date") or "").strip()
    existing_step3 = ((item.get("screening") or {}).get("step3") or {})
    source = str(existing_step3.get("source") or item.get("source") or "").strip()
    country = str(existing_step3.get("country") or item.get("country") or "").strip()
    opportunity_type = str(existing_step3.get("type") or item.get("type") or "other").strip()
    link = str(existing_step3.get("link") or item.get("url") or "").strip()
    screening: Dict[str, Any] = {
        "unrelated_to_precise_scope": unrelated,
        "step1": step1,
        "yes_count": yes_count,
        "passes_filter": passes and not unrelated,
        # Preference signal only (1=Ethiopia, 2=East Africa, 3=regional) — used
        # for ordering, never for filtering.
        "geo_priority": geo_priority(
            country,
            title=str(item.get("title") or ""),
            description=str(item.get("description") or ""),
        ),
        "step2": {
            "opportunity_characteristics": [],
            "strategic_signals": strategic_signals,
            "potential_concerns": [],
        },
        "step3": {
            "title": item.get("title", ""),
            "source": source,
            "country": country,
            "type": opportunity_type or "other",
            "deadline": date_s[:64] if date_s else "",
            "estimated_budget": None,
            "link": link,
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
