"""
Checklist-based Agent 1 for opportunity screening.
"""
import json
import logging
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage

from app.core.llm_factory import get_chat_llm

logger = logging.getLogger(__name__)


class ScreeningExtractionAgent:
    """
    Extract opportunities from page content and apply the screening checklist.
    """

    def __init__(self):
        self.llm = get_chat_llm(temperature=0.1)

    async def extract_and_screen_opportunities(
        self,
        page_content: str,
        include_all_opportunities: bool = False,
    ) -> List[Dict[str, Any]]:
        system_prompt = self._build_prompt(include_all_opportunities)
        user_prompt = f"""
Analyze this content and return opportunities in JSON only.

CONTENT:
{page_content}
"""
        try:
            response = await self.llm.ainvoke(
                [HumanMessage(content=f"{system_prompt}\n\n{user_prompt}")]
            )
            raw = response.content.strip()
            parsed = self._parse_json(raw)
            return self._validate(parsed, include_all_opportunities)
        except Exception as exc:
            logger.error("Checklist extraction failed: %s", exc)
            return []

    def _build_prompt(self, include_all_opportunities: bool) -> str:
        pass_rule = (
            "Apply pass/fail rule: keep only opportunities where at least 3 of 5 Step 1 criteria are YES."
            if not include_all_opportunities
            else "Include all opportunities; still compute step1 yes_count and passes_filter."
        )
        return f"""You are an opportunity screening analyst.

Purpose:
- Identify and shortlist relevant opportunities for further review.

Follow this Screening Checklist exactly:
Step 1: Quick Relevance Filter (Yes/No, 5 criteria):
1) mission_alignment: relates to economic development of firms/farms/industries
2) sector_relevance: off-grid energy OR agriculture/agribusiness OR health electrification OR cross-cutting (finance/climate/SMEs)
3) activity_fit: includes at least one (private sector/SMEs, BDS, access to finance, value chains/market systems, climate-smart/regenerative agriculture, PUE, research/surveys/studies, capacity building/training, policy/stakeholder engagement)
4) geographic_fit: Ethiopia OR East Africa
5) eligibility_quick_check: for-profit eligible OR unclear but not explicitly restricted

Step 2: Quick Flags (non-blocking tags, never used to eliminate):
- opportunity_characteristics: large_program, small_quick_assignment, research_heavy, implementation_heavy, consortium_likely_required
- strategic_signals: new_donor_for_precise, repeat_known_donor, government_led, private_sector_focused
- potential_concerns: very_short_deadline_lt_2_weeks, broad_or_unclear_scope, heavy_compliance_language

Step 3: Basic Information Capture:
- title, source, country, type (grant|consultancy|other), deadline, estimated_budget, link, description

{pass_rule}

Preferred source hints when inferable from text:
- LinkedIn
- RFX Now (World Bank)
- EU Funding & Tenders Portal
- USAID
- Gates Foundation
- AGRA
- Merkato

Return ONLY JSON array in this exact structure:
[
  {{
    "title": "string",
    "url": "string",
    "date": "YYYY-MM-DD or null",
    "description": "string",
    "screening": {{
      "step1": {{
        "mission_alignment": true/false,
        "sector_relevance": true/false,
        "activity_fit": true/false,
        "geographic_fit": true/false,
        "eligibility_quick_check": true/false
      }},
      "yes_count": 0,
      "passes_filter": true/false,
      "step2": {{
        "opportunity_characteristics": ["..."],
        "strategic_signals": ["..."],
        "potential_concerns": ["..."]
      }},
      "step3": {{
        "title": "string",
        "source": "string",
        "country": "string",
        "type": "grant|consultancy|other",
        "deadline": "YYYY-MM-DD or null",
        "estimated_budget": "string|null",
        "link": "string"
      }}
    }}
  }}
]
"""

    def _parse_json(self, response_text: str) -> List[Dict[str, Any]]:
        cleaned = response_text
        if response_text.startswith("```json"):
            cleaned = response_text.replace("```json", "").replace("```", "").strip()
        elif response_text.startswith("```"):
            cleaned = response_text.replace("```", "").strip()
        payload = json.loads(cleaned)
        if not isinstance(payload, list):
            return []
        return payload

    def _validate(
        self,
        items: List[Dict[str, Any]],
        include_all_opportunities: bool,
    ) -> List[Dict[str, Any]]:
        validated: List[Dict[str, Any]] = []
        for item in items:
            title = str(item.get("title", "")).strip()
            url = str(item.get("url", "")).strip()
            if not title or not url:
                continue

            screening = item.get("screening", {}) or {}
            step1 = screening.get("step1", {}) or {}
            yes_count = sum(
                1
                for key in [
                    "mission_alignment",
                    "sector_relevance",
                    "activity_fit",
                    "geographic_fit",
                    "eligibility_quick_check",
                ]
                if bool(step1.get(key))
            )
            passes_filter = yes_count >= 3
            if not include_all_opportunities and not passes_filter:
                continue

            screening["yes_count"] = yes_count
            screening["passes_filter"] = passes_filter
            screening.setdefault("step2", {})
            screening.setdefault("step3", {})
            screening["screening_version"] = "v1_checklist"

            validated.append(
                {
                    "title": title,
                    "url": url,
                    "date": item.get("date"),
                    "description": str(item.get("description", "")).strip(),
                    "screening": screening,
                    "date_status": "unknown",
                }
            )
        return validated
