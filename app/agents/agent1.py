"""
Agent 1 — Tender extraction and Precise screening checklist (v2 - Clean & Robust)

Uses clean markdown from crawl4ai (same as Test Crawler), extracts opportunities,
and applies the Precise screening checklist (Steps 1-3).

Key improvements:
- Simpler, more robust JSON parsing
- Better handling of single-object vs array responses
- Clearer LLM prompting
- Direct markdown input (clean text, not HTML)
"""
from __future__ import annotations

import json
import logging
import re
from hashlib import sha1
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from langchain_core.messages import HumanMessage

from app.agents.page_sanity import markdown_indicates_error_or_empty_notice
from app.agents.screening_prompt import PRECISE_SCREENING_CHECKLIST_MARKDOWN
from app.core.config import settings
from app.core.llm_factory import get_chat_llm
from app.pipeline.progress import pipeline_tty
from app.utils.geo_filter import (
    geo_priority,
    is_geography_allowed,
    is_specific_country_allowed,
    required_country_from_page_url,
)
from app.utils.scope_filter import is_individual_only_role, is_works_supervision_only
from app.utils.url_grounding import build_url_index, is_url_grounded
from app.utils.url_normalize import normalize_fetch_url

logger = logging.getLogger(__name__)


def use_fast_agent1_pipeline() -> bool:
    """Two-step listing + screening (small prompts). ``auto`` → fast only for Ollama."""
    mode = (getattr(settings, "PIPELINE_AGENT1_MODE", "auto") or "auto").strip().lower()
    if mode == "fast":
        return True
    if mode == "legacy":
        return False
    return (settings.LLM_PROVIDER or "").lower().strip() == "ollama"


# Patterns to strip LLM reasoning markup
_REASONING_PATTERNS = [
    re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<thinking>.*?</thinking>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<reasoning>.*?</reasoning>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<redacted_thinking>.*?</redacted_thinking>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<thought>.*?</thought>", re.DOTALL | re.IGNORECASE),
]


class TenderExtractionAgent:
    """
    Extract opportunities from clean markdown content and apply Precise screening.

    Input: Clean markdown text from crawl4ai (same as Test Crawler output)
    Output: List of screened opportunities with Step 1-3 data
    """

    STEP1_KEYS = (
        "mission_alignment",
        "sector_relevance",
        "activity_fit",
        "geographic_fit",
        "eligibility_quick_check",
    )

    def __init__(self) -> None:
        self.llm = get_chat_llm(temperature=0.1)

    async def _run_fast_pipeline(
        self,
        page_content: str,
        keyword_hints: Optional[List[str]],
        page_url: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Local-optimized: tiny listing prompt + batched compact screening (no full checklist in step 1)."""
        from app.agents.listing_extraction_agent import ListingExtractionAgent
        from app.agents.tender_screening_agent import TenderScreeningAgent

        logger.info("Agent 1: fast pipeline (2-step, truncated input)")
        pipeline_tty("[AGENT1] · fast 1/2 listing (≤{}k chars prompt body) …".format(
            max(1, int(getattr(settings, "AGENT1_FAST_MAX_INPUT_CHARS", 12000) / 1000)),
        ))
        listings = await ListingExtractionAgent().extract_listings(
            page_content,
            keyword_hints=keyword_hints,
            page_url=page_url,
        )
        if not listings:
            logger.warning("Agent 1 fast: listing step returned no rows")
            pipeline_tty("[AGENT1] · fast listing returned 0 rows")
            return []
        pipeline_tty(f"[AGENT1] · fast 2/2 screening {len(listings)} row(s) (batched) …")
        merged = await TenderScreeningAgent().screen_items(
            listings, keyword_hints=keyword_hints
        )
        return self._validate_and_enrich(
            merged,
            page_url=page_url,
            source_url_index=build_url_index(page_content, base_url=page_url or ""),
        )

    async def extract_and_screen_opportunities(
        self,
        page_content: str,
        include_all_opportunities: bool = False,
        keyword_hints: Optional[List[str]] = None,
        page_url: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Extract opportunities from clean markdown content.

        Args:
            page_content: Clean markdown text from crawl4ai (NOT raw HTML)
            include_all_opportunities: Deprecated, ignored
            keyword_hints: Optional phrases from Keyword Manager

        Returns:
            List of validated, screened opportunities
        """
        _ = include_all_opportunities  # backward compatibility

        sanity = markdown_indicates_error_or_empty_notice(
            page_content or "", http_status=None
        )
        if sanity:
            logger.info(
                "Agent 1: page looks like an error/empty shell (%s); not extracting tenders",
                sanity,
            )
            pipeline_tty(f"[AGENT1] · skipped ({sanity})")
            return []

        if use_fast_agent1_pipeline():
            try:
                out = await self._run_fast_pipeline(page_content, keyword_hints, page_url=page_url)
                pipeline_tty(f"[AGENT1] · fast mode done | validated={len(out)}")
                return out
            except Exception as exc:
                self._log_error(exc)
                return []

        import asyncio

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(page_content, keyword_hints)

        content_size = len(page_content)
        prompt_size = len(system_prompt) + len(user_prompt)
        logger.info(f"Agent 1: Starting extraction (content={content_size} chars, prompt={prompt_size} chars)")

        # Warn if content is very large (will be slow with local LLMs)
        if content_size > 100_000:
            logger.warning(f"Agent 1: Very large page content ({content_size:,} chars). Extraction may be slow with local LLMs.")

        try:
            llm_timeout = int(getattr(settings, "AGENT1_LLM_TIMEOUT_SEC", 600) or 600)
            logger.info("Agent 1: Calling LLM...")
            if (settings.LLM_PROVIDER or "").lower().strip() == "ollama":
                pipeline_tty(
                    f"[AGENT1] · awaiting Ollama ({settings.OLLAMA_MODEL}) "
                    f"— timeout {llm_timeout}s wall-clock; ensure `ollama serve` and model are pulled"
                )
            llm_task = self.llm.ainvoke(
                [HumanMessage(content=f"{system_prompt}\n\n{user_prompt}")]
            )
            response = await asyncio.wait_for(llm_task, timeout=llm_timeout)
            logger.info("Agent 1: LLM responded")
            if (settings.LLM_PROVIDER or "").lower().strip() == "ollama":
                pipeline_tty("[AGENT1] · Ollama returned — parsing JSON…")

            raw_output = self._extract_content(response)
            logger.debug("Agent 1 raw output (first 500 chars): %s", raw_output[:500])

            # Parse the output
            opportunities = self._parse_llm_output(raw_output)

            if not opportunities:
                logger.warning("Agent 1: No opportunities parsed from output")
                logger.debug("Full raw output: %s", raw_output[:2000])
                # Fallback path: try structure-based extraction so we do not drop
                # valid listing pages when checklist JSON parsing fails.
                if page_url:
                    logger.info("Agent 1: Falling back to listing extraction path for %s", page_url)
                    pipeline_tty("[AGENT1] · fallback to listing extraction")
                return await self._run_fast_pipeline(
                    page_content=page_content,
                    keyword_hints=keyword_hints,
                    page_url=page_url,
                )

            logger.info("Agent 1: extracted %d opportunities", len(opportunities))

            # Validate and enrich
            validated = self._validate_and_enrich(
                opportunities,
                page_url=page_url,
                source_url_index=build_url_index(page_content, base_url=page_url or ""),
            )

            logger.info("Agent 1: validated %d opportunities", len(validated))
            return validated

        except asyncio.TimeoutError:
            logger.error(
                "Agent 1: LLM call timed out after %ss. Content too large or LLM too slow.",
                getattr(settings, "AGENT1_LLM_TIMEOUT_SEC", 600),
            )
            logger.error(
                "Agent 1: Raise AGENT1_LLM_TIMEOUT_SEC, use PIPELINE_AGENT1_MODE=fast with Ollama, "
                "or switch LLM_PROVIDER=openai."
            )
            return []
        except Exception as exc:
            self._log_error(exc)
            return []

    def _build_system_prompt(self) -> str:
        """Build the system prompt with screening checklist."""
        return f"""You are a tender opportunity extraction specialist.

{PRECISE_SCREENING_CHECKLIST_MARKDOWN}

=== EXTRACTION RULES ===
1. Extract ALL tender opportunities visible in the content
2. For each opportunity, complete Step 1 (5 YES/NO criteria) and calculate yes_count
3. Include ONLY opportunities with yes_count >= 3. Drop 0/5, 1/5, and 2/5 rows.
4. Geography is a strict gate: INCLUDE only if geographic_fit=true for one or more of these countries: Burundi, Comoros, Djibouti, Eritrea, Ethiopia, Kenya, Rwanda, Somalia, South Sudan, Sudan, Tanzania, Uganda, Seychelles, Madagascar. Ethiopia is the PRIMARY focus. If geographic_fit=false, OMIT even when yes_count>=3. DO NOT set geographic_fit=true for tenders whose work location is in Europe (e.g. Montenegro, Italy, Serbia), Asia (e.g. Sri Lanka, India, Bangladesh), the Americas, Pacific, Middle East, or non-East-African Africa (e.g. Nigeria, Egypt, South Africa, DRC).
5. Set passes_filter = true for every included row. Do not include low-match rows with passes_filter=false.
6. Complete Step 2 (characteristics, signals, concerns) and Step 3 (title, source, country, type, deadline, budget, link)
7. ALL output text must be in English (use source_language field to tag original language)
8. Prioritize advisory/consulting (TOR, TA, studies, BDS, MEL, strategy, sector-relevant training, policy dialogue). Omit supply-only notices that lack a substantive advisory component. Mixed notices (advisory + supply) may be INCLUDED when the advisory portion satisfies geography, sectors, and activity fit. Generic goods, vehicles, security-only, construction-only, or IT commodity buys remain poor fit unless a substantive advisory workstream in Precise's sectors is clear.
9. NEVER invent opportunities. If the content is an HTTP error page, soft-404, "not found", access denied, login wall, or has no real procurement notices, return an empty JSON array [].
10. Every field in Step 3 must be traceable to text in the content; do not fabricate deadlines, budgets, organizations, or links.

=== OUTPUT FORMAT ===
Return ONLY a JSON array of opportunity objects.
NO markdown code fences, NO explanations, NO reasoning text.
Start with [ and end with ]

URL RULE (strict): copy "url" and "step3.link" verbatim from a link that literally
appears in the page content. Never construct, guess, complete or pattern-match a
URL — do not build one from a reference number, an id you inferred, or a path you
have seen on similar sites. If the page shows no link for a row, use the listing
page URL as-is.

Example structure:
[
  {{
    "title": "Tender Title",
    "url": "https://example.com/tender/123",
    "date": "2024-01-15",
    "description": "Brief description",
    "screening": {{
      "unrelated_to_precise_scope": false,
      "step1": {{
        "mission_alignment": true,
        "sector_relevance": true,
        "activity_fit": true,
        "geographic_fit": true,
        "eligibility_quick_check": true
      }},
      "yes_count": 5,
      "passes_filter": true,
      "source_language": "en",
      "step2": {{
        "opportunity_characteristics": ["characteristic 1"],
        "strategic_signals": ["signal 1"],
        "potential_concerns": ["concern 1"]
      }},
      "step3": {{
        "title": "Tender Title",
        "source": "Organization Name",
        "country": "Country Name",
        "type": "grant|consultancy|tender|other",
        "deadline": "2024-01-30",
        "estimated_budget": "string or null",
        "link": "https://example.com/tender/123"
      }}
    }}
  }}
]
"""

    def _build_user_prompt(
        self,
        page_content: str,
        keyword_hints: Optional[List[str]],
    ) -> str:
        """Build the user prompt with content to analyze."""
        # For local LLMs, be more aggressive with truncation
        max_chars = 60_000 if (settings.LLM_PROVIDER or "").lower() == "ollama" else 120_000

        content = page_content
        if len(page_content) > max_chars:
            # Keep beginning (most important) and a bit of end (for pagination/footer links)
            head = page_content[:50_000]
            tail = page_content[-8_000:]
            omitted = len(page_content) - max_chars
            content = f"{head}\n\n[... {omitted:,} characters omitted for speed ...]\n\n{tail}"
            logger.info(f"Agent 1: Truncated content from {len(page_content):,} to {len(content):,} chars (local LLM optimization)")

        keyword_section = ""
        if keyword_hints:
            hints = ", ".join(str(h).strip() for h in keyword_hints if str(h).strip())
            if hints:
                keyword_section = f"""

Keyword hints (weak signals only):
{hints}"""

        return f"""Analyze this page content and extract all tender opportunities.

CONTENT:
{content}{keyword_section}

Extract opportunities as a JSON array only."""

    def _extract_content(self, response: Any) -> str:
        """Extract text content from LLM response."""
        text = getattr(response, "content", None) or ""

        # Handle Ollama-specific response format
        extra = getattr(response, "additional_kwargs", {}) or {}
        for key in ("answer", "response", "output"):
            chunk = extra.get(key)
            if isinstance(chunk, str) and chunk.strip():
                text = chunk.strip()
                break

        return text.strip()

    def _parse_llm_output(self, raw: str) -> List[Dict[str, Any]]:
        """Parse LLM output into list of opportunities."""
        if not raw:
            return []

        t = raw.strip()

        # 1) Whole-document JSON first (avoids mis-slicing ``[`` inside nested fields).
        try:
            payload = json.loads(t)
        except json.JSONDecodeError:
            payload = None
        if payload is not None:
            as_list = self._json_root_to_opportunity_list(payload)
            if as_list is not None:
                return as_list  # type: ignore[return-value]

        # 2) Bracket slice on raw — JSON may live inside ``<think>`` wrappers; stripping would delete it.
        bracket = self._try_load_bracket_array(t)
        if bracket is not None:
            return bracket  # type: ignore[return-value]

        # 3) Strip reasoning markup, then reuse :meth:`_extract_json`.
        cleaned = self._strip_reasoning(raw)
        json_data = self._extract_json(cleaned)
        if json_data is None:
            logger.warning("Agent 1: Could not extract JSON from output")
            return []

        if isinstance(json_data, list):
            return json_data

        if isinstance(json_data, dict):
            if json_data.get("title") and json_data.get("url"):
                return [json_data]

            for key in ("opportunities", "items", "tenders", "results", "data", "rows"):
                if key in json_data and isinstance(json_data[key], list):
                    return json_data[key]

            return [json_data]

        return []

    def _strip_reasoning(self, text: str) -> str:
        """Remove LLM reasoning markup."""
        result = text
        for pattern in _REASONING_PATTERNS:
            result = pattern.sub("", result)
        return result.strip()

    def _extract_json(self, text: str) -> Optional[Any]:
        """Extract JSON from text, handling various formats."""
        if not text:
            return None

        # Try direct JSON parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Strip markdown code fences
        cleaned = text
        if cleaned.startswith("```"):
            # Remove opening fence
            lines = cleaned.split("\n", 1)
            if len(lines) > 1:
                cleaned = lines[1]
            else:
                cleaned = cleaned[3:]

        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

        # Handle ```json ... ```
        if "```json" in cleaned:
            parts = cleaned.split("```json", 1)
            if len(parts) > 1:
                cleaned = parts[1].split("```", 1)[0].strip()
        elif "```" in cleaned:
            parts = cleaned.split("```", 1)
            if len(parts) > 1:
                cleaned = parts[1].split("```", 1)[0].strip()

        # Try parsing again
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Find array bounds
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass

        # Find object bounds
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass

        return None

    def _validate_and_enrich(
        self,
        items: List[Dict[str, Any]],
        page_url: Optional[str] = None,
        source_url_index: Optional[set] = None,
    ) -> List[Dict[str, Any]]:
        """Validate and enrich opportunity data.

        ``source_url_index`` (see :mod:`app.utils.url_grounding`) lets this method
        detect detail URLs the model invented. When omitted, no grounding check
        runs.
        """
        validated: List[Dict[str, Any]] = []
        parsed_page = urlparse(page_url or "")
        tma_procurement_mode = (
            "trademarkafrica.com" in parsed_page.netloc.lower()
            and "/procurement" in parsed_page.path.lower()
        )
        strict_country = required_country_from_page_url(page_url or "")
        afdb_country_mode = bool(
            strict_country and "afdb.org" in (page_url or "").lower()
        )
        worldbank_procurement_mode = bool(
            strict_country and "worldbank.org" in (page_url or "").lower()
        )
        worldbank_region_mode = bool(
            strict_country == "east_africa" and "worldbank.org" in (page_url or "").lower()
        )
        reject_stats: Dict[str, int] = {
            "missing_required_fields": 0,
            "url_not_in_source": 0,
            "award_notice_reject": 0,
            "unrelated_scope": 0,
            "yes_count_lt3": 0,
            "geographic_fit_false": 0,
            "geo_hard_reject": 0,
            "strict_country_reject": 0,
            "mission_reject": 0,
            "eligibility_reject": 0,
            "individual_only_reject": 0,
            "works_supervision_reject": 0,
            "focus_reject": 0,
            "supply_only_reject": 0,
            "kept": 0,
        }

        for item in items:
            # Required fields
            title = str(item.get("title", "")).strip()
            url = normalize_fetch_url(str(item.get("url", "")).strip())
            description = str(item.get("description", "")).strip()

            # World Bank listing rows can lack direct detail links.
            # Keep such rows with a stable synthetic URL so downstream stages
            # can still persist and deduplicate them.
            if not url and worldbank_region_mode and title:
                digest_src = f"{title}|{description}|{strict_country}".encode("utf-8", "ignore")
                digest = sha1(digest_src).hexdigest()[:12]
                base_url = (page_url or "https://www.worldbank.org/en/projects-operations/procurement").strip()
                url = f"{base_url}#wb-row-{digest}"

            if not title or not url:
                reject_stats["missing_required_fields"] += 1
                continue

            # Guard against invented detail links. The row itself may be real, so
            # point it at the listing page and let Agent 2 report from the listing
            # data rather than fetching a URL that does not exist.
            detail_url_unverified = False
            if source_url_index and not is_url_grounded(url, source_url_index, page_url or ""):
                reject_stats["url_not_in_source"] += 1
                logger.info(
                    "Agent 1: detail URL not found in harvested page, using listing URL: %r (title=%r)",
                    url[:120],
                    title[:60],
                )
                url = (page_url or "").strip() or url
                detail_url_unverified = True

            # Get or create screening data
            screening = item.get("screening", {}) or {}
            low_title = title.lower()
            low_desc = description.lower()

            # WB procurement listing often mixes closed "Contract Award" rows
            # with active opportunities. Drop obvious award rows early so
            # downstream stages stay focused on open opportunities only.
            if worldbank_procurement_mode:
                looks_award = (
                    "contract award" in low_title
                    or "contract award" in low_desc
                    or "award notice" in low_title
                    or "award notice" in low_desc
                )
                if looks_award:
                    reject_stats["award_notice_reject"] += 1
                    continue

            # Check unrelated flag.
            # For AfDB strict-country mode, keep Ethiopia-matching listing rows even if
            # the LLM marks them unrelated from sparse snippet context.
            if (
                not afdb_country_mode
                and not worldbank_region_mode
                and not tma_procurement_mode
                and screening.get("unrelated_to_precise_scope", False)
            ):
                reject_stats["unrelated_scope"] += 1
                continue

            # Calculate yes_count from step1
            step1 = screening.get("step1", {}) or {}
            yes_count = sum(1 for key in self.STEP1_KEYS if step1.get(key))

            # Keep only opportunities that pass the initial checklist threshold.
            if yes_count < 3 and not afdb_country_mode and not worldbank_region_mode and not tma_procurement_mode:
                reject_stats["yes_count_lt3"] += 1
                continue

            # Geography hard gate:
            # - default mode: respect LLM geographic_fit boolean.
            # - AfDB strict-country mode: rely on deterministic geo checks below.
            if (
                not afdb_country_mode
                and not worldbank_region_mode
                and not tma_procurement_mode
                and not bool(step1.get("geographic_fit"))
            ):
                reject_stats["geographic_fit_false"] += 1
                continue

            # Secondary hard geo gate: deterministic allowlist check to catch
            # LLM errors where geographic_fit=true was set for non-EA countries
            # (e.g. Montenegro, Sri Lanka). Checks step3.country first, then
            # falls back to title / description signals.
            #
            # In World Bank strict East-Africa mode we skip this generic gate
            # and rely on `is_specific_country_allowed(east_africa, ...)`
            # below, because WB listing snippets can carry noisy/partial
            # geography text that over-trips the generic blocked-token logic.
            step3_check = screening.get("step3", {}) or {}
            country_check = str(step3_check.get("country", "")).strip()
            if (
                not tma_procurement_mode
                and not worldbank_region_mode
                and not is_geography_allowed(country_check, title=title, description=description)
            ):
                reject_stats["geo_hard_reject"] += 1
                logger.info(
                    "Agent 1 geo hard-reject: country=%r title=%r",
                    country_check, title[:80],
                )
                continue

            if strict_country and not is_specific_country_allowed(
                strict_country,
                country_check,
                title=title,
                description=description,
            ):
                reject_stats["strict_country_reject"] += 1
                logger.info(
                    "Agent 1 strict-country reject: required=%r country=%r title=%r",
                    strict_country, country_check, title[:80],
                )
                continue

            # Mission alignment is mandatory in general, but AfDB strict-country mode
            # intentionally keeps Ethiopia-targeted rows even if the LLM under-scores
            # mission fit on short listing snippets.
            if not afdb_country_mode and not worldbank_region_mode and not tma_procurement_mode:
                if not bool(step1.get("mission_alignment")):
                    reject_stats["mission_reject"] += 1
                    logger.info(
                        "Agent 1 mission-align reject: title=%r", title[:80]
                    )
                    continue

            # Eligibility is mandatory in general; relaxed for AfDB strict-country
            # mode because RSS/listing rows are terse and can be under-scored.
            if not afdb_country_mode and not worldbank_region_mode and not tma_procurement_mode:
                if not bool(step1.get("eligibility_quick_check")):
                    reject_stats["eligibility_reject"] += 1
                    logger.info(
                        "Agent 1 eligibility reject: title=%r", title[:80]
                    )
                    continue

            # Deterministic scope nets: assignments addressed to an individual
            # person (a firm cannot bid) and civil-works supervision dressed up as
            # "consultancy services". Both are narrow by design — see scope_filter.
            if is_individual_only_role(title, description):
                reject_stats["individual_only_reject"] += 1
                logger.info("Agent 1 individual-only reject: title=%r", title[:80])
                continue
            if is_works_supervision_only(title, description):
                reject_stats["works_supervision_reject"] += 1
                logger.info("Agent 1 works-supervision reject: title=%r", title[:80])
                continue

            # Sector / activity focus is mandatory in general. Mission, geography
            # and eligibility are broad enough that all three can hold for a
            # vaguely-worded "development consultancy" with no identifiable
            # sector or advisory activity. Relaxed for the same terse-listing
            # modes as the gates above.
            if (
                settings.SCREENING_REQUIRE_SECTOR_OR_ACTIVITY
                and not afdb_country_mode
                and not worldbank_region_mode
                and not tma_procurement_mode
            ):
                if not (
                    bool(step1.get("sector_relevance")) or bool(step1.get("activity_fit"))
                ):
                    reject_stats["focus_reject"] += 1
                    logger.info(
                        "Agent 1 sector/activity focus reject: title=%r", title[:80]
                    )
                    continue

            # Supply-only engagements are out of scope in general; relaxed for
            # AfDB strict-country mode (user requested Ethiopia-inclusive capture).
            step2_check = screening.get("step2", {}) or {}
            signals = step2_check.get("strategic_signals", []) or []
            if (
                not afdb_country_mode
                and not worldbank_region_mode
                and not tma_procurement_mode
                and "engagement_supply_only" in signals
            ):
                reject_stats["supply_only_reject"] += 1
                logger.info(
                    "Agent 1 supply-only reject: title=%r", title[:80]
                )
                continue

            # Enrich screening data
            screening["yes_count"] = yes_count
            if afdb_country_mode or worldbank_region_mode:
                screening["passes_filter"] = True
            elif tma_procurement_mode:
                screening["passes_filter"] = yes_count >= 1
            else:
                screening["passes_filter"] = yes_count >= 3 and bool(step1.get("geographic_fit"))
            screening["unrelated_to_precise_scope"] = False
            screening.setdefault("step2", {})
            screening.setdefault("step3", {})
            screening["screening_version"] = "v1_checklist"
            # ``step3.link`` is what notifications render, and the model fills it
            # separately from ``url`` — so it needs the same grounding treatment.
            step3_link = str(screening["step3"].get("link") or "").strip()
            if not step3_link or (
                source_url_index
                and not is_url_grounded(step3_link, source_url_index, page_url or "")
            ):
                screening["step3"]["link"] = url
            # Preference signal only (1=Ethiopia, 2=East Africa, 3=regional).
            screening["geo_priority"] = geo_priority(
                country_check, title=title, description=description
            )

            # Handle source language
            raw_lang = screening.get("source_language")
            if isinstance(raw_lang, str) and raw_lang.strip():
                screening["source_language"] = raw_lang.strip()[:32].lower()
            else:
                screening.pop("source_language", None)

            row: Dict[str, Any] = {
                "title": title,
                "url": url,
                "date": item.get("date"),
                "description": description,
                "screening": screening,
                "date_status": "unknown",
            }
            if detail_url_unverified:
                row["detail_url_unverified"] = True
            validated.append(row)
            reject_stats["kept"] += 1
        if items:
            reject_only = {k: v for k, v in reject_stats.items() if k not in ("kept",) and v}
            logger.info(
                "Agent 1 validate summary: total=%s kept=%s rejects=%s strict=%r wb_mode=%s afdb_mode=%s",
                len(items),
                reject_stats.get("kept", 0),
                reject_only,
                strict_country,
                worldbank_region_mode,
                afdb_country_mode,
            )
            pipeline_tty(
                f"[AGENT1] · validate summary | total={len(items)} kept={reject_stats.get('kept', 0)} "
                f"| rejects={json.dumps(reject_only, ensure_ascii=True)}"
            )
        # Ethiopia first, then the rest of East Africa. Ordering only.
        validated.sort(
            key=lambda row: int((row.get("screening") or {}).get("geo_priority") or 3)
        )
        return validated

    def _validate(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Backward-compatible alias for :meth:`_validate_and_enrich` (tests, legacy callers)."""
        return self._validate_and_enrich(items)

    def _parse_json(self, response_text: str) -> List[Dict[str, Any]]:
        """Backward-compatible alias for checklist-shaped JSON (tests, legacy callers)."""
        return self._parse_llm_output(response_text)

    def _try_load_bracket_array(self, text: str) -> Optional[List[Any]]:
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end <= start:
            return None
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, list) else None

    def _json_root_to_opportunity_list(self, payload: Any) -> Optional[List[Any]]:
        """Normalize a JSON root (array or single opportunity object) to a list."""
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            title = str(payload.get("title", "")).strip()
            url = str(payload.get("url", "")).strip()
            if title and url:
                return [payload]
            for key in ("opportunities", "items", "tenders", "results", "data", "rows"):
                inner = payload.get(key)
                if isinstance(inner, list):
                    return inner
        return None

    def _log_error(self, exc: Exception) -> None:
        """Log error with helpful hints."""
        err_msg = str(exc).lower()
        hint = ""

        prov = (settings.LLM_PROVIDER or "").lower().strip()
        if any(word in err_msg for word in ("connection", "connect", "refused", "unreachable")):
            if prov == "ollama":
                hint = (
                    f" [LLM unreachable: OLLAMA_BASE_URL={settings.OLLAMA_BASE_URL!r} — "
                    f"ensure Ollama is running (`ollama serve`)]"
                )
            elif prov in ("openai", "anthropic", "claude"):
                key_hint = (
                    "ANTHROPIC_API_KEY"
                    if prov in ("anthropic", "claude")
                    else "OPENAI_API_KEY"
                )
                hint = f" [LLM unreachable — check {key_hint}]"

        logger.error("Agent 1 extraction failed: %s%s", exc, hint)
