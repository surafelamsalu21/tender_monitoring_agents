"""Linear pipeline: crawl artifact → structure → DB (compat) → Agent 2 → Agent 3."""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional

from app.agents.agent2 import TenderDetailAgent
from app.agents.agent3 import EmailComposerAgent
from app.agents.tender_screening_agent import TenderScreeningAgent
from app.core.config import settings
from app.pipeline.agent1_structure import ListingStructureAgent
from app.pipeline.legacy_adapter import listing_rows_to_tender_dicts
from app.pipeline.progress import active_llm_label, pipeline_tty
from app.pipeline.schemas import CrawlArtifactV1, ListingRowV1
from app.utils.geo_filter import (
    geo_priority,
    is_geography_allowed,
    is_specific_country_allowed,
    required_country_from_page_url,
)
from app.utils.scope_filter import is_individual_only_role, is_works_supervision_only
from app.utils.tender_deadline_gate import filter_expired_agent1_items
from app.utils.url_grounding import build_url_index

logger = logging.getLogger(__name__)


_EA_POLICY_TERMS = (
    "economic policy",
    "financial architecture",
    "public financial management",
    "pfm",
    "macroeconomic",
    "economic modeling",
)


def _is_ea_policy_advisory_allowance(tender: Dict[str, Any]) -> bool:
    """Allow specific EA policy advisory opportunities to pass mission/sector/activity gates."""
    screening = tender.get("screening") or {}
    step3 = screening.get("step3") or {}
    country = str(step3.get("country") or "").lower()
    title = str(tender.get("title") or "").lower()
    description = str(tender.get("description") or "").lower()
    hay = f"{title}\n{description}"

    # Must still be geographically valid and consultancy-like.
    if not is_geography_allowed(country, title=title, description=description):
        return False
    if not any(term in hay for term in _EA_POLICY_TERMS):
        return False
    # "supply" on its own also matches "supply chain", which is ordinary value
    # chain language in exactly the notices this allowance exists to rescue.
    if re.search(r"\bsupply\b(?!\s+chain)", hay):
        return False
    if any(bad in hay for bad in ("equipment", "construction", "works supervision")):
        return False
    return True


def _normalize_identity_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _batch_identity_key(tender: Dict[str, Any], *, page_id: int, tender_repo: Any) -> str:
    screening = tender.get("screening") or {}
    step3 = screening.get("step3") or {}
    normalized_url = tender_repo._normalize_url(tender.get("url", ""))
    return "|".join(
        [
            f"page:{page_id}",
            f"url:{normalized_url}",
            f"title:{_normalize_identity_text(tender.get('title'))}",
            f"deadline:{_normalize_identity_text(step3.get('deadline') or tender.get('date'))}",
            f"source:{_normalize_identity_text(step3.get('source'))}",
            f"type:{_normalize_identity_text(step3.get('type'))}",
            f"country:{_normalize_identity_text(step3.get('country'))}",
        ]
    )


def _empty_result(enable_date_filtering: bool, error: str = "") -> Dict[str, Any]:
    failed = bool(error)
    return {
        "filtered_tenders": [],
        "detailed_tenders": [],
        "email_compositions": [],
        "duplicates_checked": False,
        "duplicate_count": 0,
        "filtered_count": 0,
        "agent1_completed": not failed,
        "agent2_completed": False,
        "agent3_completed": False,
        "workflow_failed": failed,
        "error": error,
        "total_found": 0,
        "total_saved_basic": 0,
        "total_saved_detailed": 0,
        "total_email_compositions": 0,
        "date_filtering_enabled": enable_date_filtering,
        "processing_summary": {
            "all_tenders_found": 0,
            "after_date_filtering": 0,
            "after_duplicate_removal": 0,
            "processed_by_agent2": 0,
            "skipped_by_agent2": 0,
        },
    }


async def run_simple_pipeline(
    *,
    page_content: str,
    page_url: str,
    page_id: int,
    listing_markdown_for_expiry: str,
    tender_repo: Any,
    db: Any,
    enable_date_filtering: bool,
    crawl_artifact: Optional[CrawlArtifactV1],
    agent2: TenderDetailAgent,
    agent3: EmailComposerAgent,
    identity_key_fn: Callable[[Dict[str, Any]], str],
) -> Dict[str, Any]:
    """
    Crawler-centric flow without LangGraph.

    - Agent 1 = :class:`ListingStructureAgent` only.
    - Duplicate check + DB1/DB2 + Agent 2/3 reuse existing modules.
    """
    md_source = (crawl_artifact.markdown if crawl_artifact is not None else None) or page_content
    strict_country = required_country_from_page_url(page_url or "")
    if not (md_source or "").strip():
        return _empty_result(enable_date_filtering, "No markdown content from crawl")

    logger.info("Simple pipeline: start page_id=%s url=%s", page_id, page_url)
    pipeline_tty(f"[PIPELINE] .... page_id={page_id}")
    pipeline_tty(f"[PIPELINE] .... │ {page_url}")
    pipeline_tty(
        f"[PIPELINE] .... │ markdown {len(md_source):,} chars | llm={active_llm_label()}"
    )

    structured_rows = []
    if crawl_artifact is not None and isinstance(crawl_artifact.metadata, dict):
        structured_rows = crawl_artifact.metadata.get("listing_rows_v1") or []

    if structured_rows:
        rows = []
        for row in structured_rows:
            if not isinstance(row, dict):
                continue
            try:
                rows.append(ListingRowV1(**row))
            except Exception as exc:
                logger.debug("Simple pipeline: skipped invalid structured row: %s", exc)
        pipeline_tty(f"[AGENT1] .... ✓ {len(rows)} structured source row(s)")
        logger.info("Simple pipeline: using %s structured source row(s)", len(rows))
        source_url_index = None
    else:
        struct_agent = ListingStructureAgent()
        rows = await struct_agent.structure_listing(md_source, page_url)
        # Only LLM-produced rows need grounding; structured sources carry real URLs.
        source_url_index = build_url_index(
            md_source,
            (crawl_artifact.links if crawl_artifact is not None else None) or [],
            base_url=page_url or "",
        )
    all_tenders = listing_rows_to_tender_dicts(rows, page_url, source_url_index)

    if not all_tenders:
        logger.warning("Simple pipeline: 0 tenders after structure + adapter")
        pipeline_tty("[PIPELINE] .... ✗ 0 tenders after structure — check LLM JSON")
        out = _empty_result(enable_date_filtering)
        out["agent1_completed"] = True
        return out

    expiry_dropped = 0
    ex_src = listing_markdown_for_expiry if listing_markdown_for_expiry.strip() else md_source
    # AfDB strict-country (RSS fallback) rows only carry a publication date, and WB
    # listing rows expose publication/contract dates too, so reading their last
    # table column as a closing date would discard live notices. Only the listing
    # heuristic is unsafe there — an explicit step3.deadline is still honoured, so
    # World Bank notices that really have closed no longer reach the database.
    page_url_l = (page_url or "").lower()
    listing_dates_ambiguous = bool(
        strict_country
        and (
            "afdb.org" in page_url_l
            or "worldbank.org" in page_url_l
        )
    )
    if settings.SKIP_EXPIRED_AFTER_AGENT1:
        all_tenders, expiry_dropped = filter_expired_agent1_items(
            all_tenders,
            ex_src,
            use_listing_inference=not listing_dates_ambiguous,
        )
        if expiry_dropped:
            logger.info("Simple pipeline: expiry gate dropped %s row(s)", expiry_dropped)

    pipeline_tty(
        f"[PIPELINE] .... │ rows {len(all_tenders)} | expiry dropped {expiry_dropped}"
    )

    if structured_rows:
        pipeline_tty(f"[PIPELINE] .... ↓ checklist screening (structured source) | {len(all_tenders)} row(s)")
    else:
        pipeline_tty(f"[PIPELINE] .... ↓ checklist screening | {len(all_tenders)} row(s)")
    screened_tenders = await TenderScreeningAgent().screen_items(all_tenders)
    if screened_tenders:
        all_tenders = [
            tender
            for tender in screened_tenders
            if bool((tender.get("screening") or {}).get("passes_filter"))
        ]
        for tender in screened_tenders:
            if bool((tender.get("screening") or {}).get("passes_filter")):
                continue
            if _is_ea_policy_advisory_allowance(tender):
                screening = tender.setdefault("screening", {})
                step1 = screening.setdefault("step1", {})
                step1["mission_alignment"] = True
                step1["sector_relevance"] = True
                step1["activity_fit"] = True
                if "yes_count" not in screening or int(screening.get("yes_count") or 0) < 3:
                    screening["yes_count"] = max(3, int(screening.get("yes_count") or 0))
                screening["passes_filter"] = True
                all_tenders.append(tender)
    else:
        all_tenders = []
    pipeline_tty(
        f"[PIPELINE] .... │ checklist kept {len(all_tenders)} relevant row(s)"
    )

    # Hard geo gate: deterministic allowlist check after LLM screening.
    # Catches cases where the LLM incorrectly set geographic_fit=true for
    # non-East-African tenders (e.g. Montenegro, Sri Lanka).
    if all_tenders:
        geo_before = len(all_tenders)
        all_tenders = [
            tender for tender in all_tenders
            if is_geography_allowed(
                (tender.get("screening") or {}).get("step3", {}).get("country", ""),
                title=tender.get("title", ""),
                description=tender.get("description", ""),
            )
        ]
        geo_dropped = geo_before - len(all_tenders)
        if geo_dropped:
            pipeline_tty(
                f"[PIPELINE] .... │ geo hard-gate dropped {geo_dropped} non-EA tender(s)"
            )
            logger.info("Simple pipeline: geo hard-gate dropped %s tender(s)", geo_dropped)

    if all_tenders and strict_country:
        strict_before = len(all_tenders)
        all_tenders = [
            tender for tender in all_tenders
            if is_specific_country_allowed(
                strict_country,
                (tender.get("screening") or {}).get("step3", {}).get("country", ""),
                title=tender.get("title", ""),
                description=tender.get("description", ""),
            )
        ]
        strict_dropped = strict_before - len(all_tenders)
        if strict_dropped:
            pipeline_tty(
                f"[PIPELINE] .... │ strict country gate ({strict_country}) dropped {strict_dropped} tender(s)"
            )
            logger.info(
                "Simple pipeline: strict country=%s dropped %s tender(s)",
                strict_country,
                strict_dropped,
            )

    # Mission alignment mandatory gate.
    # Tenders not about economic development of firms/farms/industries are
    # outside Precise's core scope (e.g. transport enforcement, legal aid,
    # governance, UNCT config, pure construction, gender/social evaluations).
    if all_tenders:
        mission_before = len(all_tenders)
        all_tenders = [
            tender for tender in all_tenders
            if bool(
                (tender.get("screening") or {}).get("step1", {}).get("mission_alignment")
            )
        ]
        mission_dropped = mission_before - len(all_tenders)
        if mission_dropped:
            pipeline_tty(
                f"[PIPELINE] .... │ mission gate dropped {mission_dropped} non-aligned tender(s)"
            )
            logger.info("Simple pipeline: mission gate dropped %s tender(s)", mission_dropped)

    # Eligibility mandatory gate.
    # Individual Consultant / Individual Contractor roles are for individual
    # persons only — a consulting firm cannot apply.
    if all_tenders:
        elig_before = len(all_tenders)
        all_tenders = [
            tender for tender in all_tenders
            if bool(
                (tender.get("screening") or {}).get("step1", {}).get("eligibility_quick_check")
            )
        ]
        elig_dropped = elig_before - len(all_tenders)
        if elig_dropped:
            pipeline_tty(
                f"[PIPELINE] .... │ eligibility gate dropped {elig_dropped} individual-only tender(s)"
            )
            logger.info("Simple pipeline: eligibility gate dropped %s tender(s)", elig_dropped)

    # Sector / activity focus gate.
    # Mission alignment, geography and eligibility are broad enough that a
    # vaguely-worded "development consultancy in Ethiopia" satisfies all three.
    # Require at least one of the two criteria that actually identify the work as
    # Precise's kind of advisory assignment. OR rather than AND, so a notice that
    # names a relevant sector OR a relevant activity still gets through.
    if all_tenders and settings.SCREENING_REQUIRE_SECTOR_OR_ACTIVITY:
        focus_before = len(all_tenders)
        all_tenders = [
            tender for tender in all_tenders
            if bool((tender.get("screening") or {}).get("step1", {}).get("sector_relevance"))
            or bool((tender.get("screening") or {}).get("step1", {}).get("activity_fit"))
        ]
        focus_dropped = focus_before - len(all_tenders)
        if focus_dropped:
            pipeline_tty(
                f"[PIPELINE] .... │ focus gate dropped {focus_dropped} tender(s) with no sector/activity fit"
            )
            logger.info("Simple pipeline: focus gate dropped %s tender(s)", focus_dropped)

    # Supply-only gate.
    # Precise works on consulting/TA/BDS/research — not on goods procurement.
    if all_tenders:
        supply_before = len(all_tenders)
        all_tenders = [
            tender for tender in all_tenders
            if "engagement_supply_only" not in (
                (tender.get("screening") or {}).get("step2", {}).get("strategic_signals", [])
                or []
            )
        ]
        supply_dropped = supply_before - len(all_tenders)
        if supply_dropped:
            pipeline_tty(
                f"[PIPELINE] .... │ supply gate dropped {supply_dropped} supply-only tender(s)"
            )
            logger.info("Simple pipeline: supply gate dropped %s tender(s)", supply_dropped)

    # Deterministic scope nets.
    # Rule-based backstops for the two cases the checklist calls out repeatedly
    # but the model still mislabels: assignments addressed to an individual
    # person (a firm cannot bid) and civil-works supervision advertised as
    # "consultancy services". Both are narrow by design — see scope_filter.
    if all_tenders:
        scope_before = len(all_tenders)
        all_tenders = [
            tender for tender in all_tenders
            if not is_individual_only_role(
                tender.get("title", ""), tender.get("description", "")
            )
            and not is_works_supervision_only(
                tender.get("title", ""), tender.get("description", "")
            )
        ]
        scope_dropped = scope_before - len(all_tenders)
        if scope_dropped:
            pipeline_tty(
                f"[PIPELINE] .... │ scope net dropped {scope_dropped} individual-only/works tender(s)"
            )
            logger.info("Simple pipeline: scope net dropped %s tender(s)", scope_dropped)

    if not all_tenders:
        logger.info("Simple pipeline: nothing relevant after checklist screening")
        out = _empty_result(enable_date_filtering)
        out["agent1_completed"] = True
        out["duplicates_checked"] = True
        return out

    # Order Ethiopia first, then the rest of East Africa, then regional/ambiguous.
    # Purely a preference ordering: nothing is dropped, but the highest-value
    # tenders reach Agent 2 first and lead the email digest.
    for tender in all_tenders:
        screening = tender.setdefault("screening", {})
        if not screening.get("geo_priority"):
            screening["geo_priority"] = geo_priority(
                (screening.get("step3") or {}).get("country", ""),
                title=tender.get("title", ""),
                description=tender.get("description", ""),
            )
    all_tenders.sort(key=lambda t: int((t.get("screening") or {}).get("geo_priority") or 3))
    ethiopia_count = sum(
        1 for t in all_tenders if int((t.get("screening") or {}).get("geo_priority") or 3) == 1
    )
    pipeline_tty(
        f"[PIPELINE] .... │ priority | Ethiopia {ethiopia_count} | other {len(all_tenders) - ethiopia_count}"
    )

    strong_matches = [
        tender
        for tender in all_tenders
        if bool((tender.get("screening") or {}).get("passes_filter"))
    ]
    if enable_date_filtering:
        filtered_for_agent2 = strong_matches
    else:
        filtered_for_agent2 = all_tenders

    filtered_count = len(all_tenders) - len(filtered_for_agent2)

    # Dedupe
    logger.info("Simple pipeline: deduplicating %s row(s)", len(all_tenders))
    extracted: List[Dict[str, Any]] = []
    duplicate_count = 0
    seen_batch_keys: set[str] = set()
    for tender in all_tenders:
        title = tender.get("title", "")
        url = tender.get("url", "")
        if not title or not url:
            duplicate_count += 1
            continue
        batch_key = _batch_identity_key(tender, page_id=page_id, tender_repo=tender_repo)
        if batch_key in seen_batch_keys:
            duplicate_count += 1
            continue
        seen_batch_keys.add(batch_key)
        is_dup = tender_repo.check_duplicate_tender(
            db,
            title,
            url,
            page_id,
            screening_result=tender.get("screening", {}),
            tender_date=(
                tender.get("screening", {}).get("step3", {}).get("deadline") or tender.get("date")
            ),
        )
        if is_dup:
            duplicate_count += 1
        else:
            extracted.append(tender)

    filtered_keys = {identity_key_fn(t) for t in extracted}
    # Agent 2 now runs for all newly saved rows (not only strong matches).
    tenders_for_agent2: List[Dict[str, Any]] = []
    for tender in extracted:
        if identity_key_fn(tender) in filtered_keys:
            tenders_for_agent2.append(tender)

    pipeline_tty(
        f"[PIPELINE] .... │ dedupe | new {len(extracted)} | skipped_dup {duplicate_count}"
    )

    if not extracted:
        logger.info("Simple pipeline: nothing new after dedupe")
        pipeline_tty("[PIPELINE] .... ● done (no new rows to save)")
        return {
            "filtered_tenders": [],
            "detailed_tenders": [],
            "email_compositions": [],
            "duplicates_checked": True,
            "duplicate_count": duplicate_count,
            "filtered_count": filtered_count,
            "agent1_completed": True,
            "agent2_completed": False,
            "agent3_completed": False,
            "workflow_failed": False,
            "error": "",
            "total_found": len(all_tenders),
            "total_saved_basic": 0,
            "total_saved_detailed": 0,
            "total_email_compositions": 0,
            "date_filtering_enabled": enable_date_filtering,
            "processing_summary": {
                "all_tenders_found": len(all_tenders),
                "after_date_filtering": len(filtered_for_agent2),
                "after_duplicate_removal": 0,
                "processed_by_agent2": 0,
                "skipped_by_agent2": 0,
            },
        }

    saved_basic = []
    for tender_data in extracted:
        tender = tender_repo.save_tender(
            db,
            page_id=page_id,
            title=tender_data["title"],
            url=tender_data["url"],
            tender_date=(
                tender_data.get("screening", {})
                .get("step3", {})
                .get("deadline")
                or tender_data.get("date")
            ),
            description=tender_data.get("description", ""),
            screening_result=tender_data.get("screening", {}),
        )
        if tender:
            saved_basic.append(tender)

    pipeline_tty(f"[PIPELINE] .... │ DB1 saved {len(saved_basic)} tender(s)")

    skip_date_validation = not enable_date_filtering
    pipeline_tty(
        f"[PIPELINE] .... ↓ Agent 2 | {len(tenders_for_agent2)} tender(s) in queue"
    )
    t_a2 = time.perf_counter()
    detailed_results = await agent2.process_multiple_tenders(
        tender_list=tenders_for_agent2,
        skip_date_validation=skip_date_validation,
    )
    n_done = len([t for t in detailed_results if t.get("processing_status") == "completed"])
    n_skip = len([t for t in detailed_results if t.get("processing_status") == "skipped"])
    pipeline_tty(
        f"[PIPELINE] .... ✓ Agent 2 | completed={n_done} skipped={n_skip} | "
        f"⏱: {time.perf_counter() - t_a2:.1f}s"
    )

    saved_detailed = []
    for detailed_tender in detailed_results:
        if detailed_tender.get("processing_status") != "completed":
            continue
        tender_url = detailed_tender.get("url")
        basic_tender = None
        for saved_tender in saved_basic:
            if saved_tender.url == tender_url:
                basic_tender = saved_tender
                break
        if not basic_tender:
            continue
        detailed_info = detailed_tender.get("detailed_info", {})
        obj = tender_repo.save_detailed_tender(
            db,
            tender_id=basic_tender.id,
            detailed_info=detailed_info,
        )
        if obj:
            saved_detailed.append(obj)

    pipeline_tty(f"[PIPELINE] .... │ DB2 saved {len(saved_detailed)} detail row(s)")

    completed = [t for t in detailed_results if t.get("processing_status") == "completed"]
    completed = [t for t in completed if bool((t.get("screening") or {}).get("passes_filter"))]
    email_compositions: List[Dict[str, Any]] = []
    if completed:
        pipeline_tty(f"[PIPELINE] .... ↓ Agent 3 | {len(completed)} tender(s) for email")
        t_a3 = time.perf_counter()
        email_compositions = await agent3.compose_multiple_emails(completed, "screening_opportunities")
        pipeline_tty(
            f"[PIPELINE] .... ✓ Agent 3 | {len(email_compositions)} email(s) | "
            f"⏱: {time.perf_counter() - t_a3:.1f}s"
        )
    else:
        pipeline_tty("[PIPELINE] .... │ Agent 3 skipped (no completed tenders)")

    pipeline_tty(f"[PIPELINE] ● complete page_id={page_id}")

    return {
        "filtered_tenders": saved_basic,
        "detailed_tenders": detailed_results,
        "email_compositions": email_compositions,
        "duplicates_checked": True,
        "duplicate_count": duplicate_count,
        "filtered_count": filtered_count,
        "agent1_completed": True,
        "agent2_completed": True,
        "agent3_completed": True,
        "workflow_failed": False,
        "error": "",
        "total_found": len(all_tenders),
        "total_saved_basic": len(saved_basic),
        "total_saved_detailed": len(saved_detailed),
        "total_email_compositions": len(email_compositions),
        "date_filtering_enabled": enable_date_filtering,
        "processing_summary": {
            "all_tenders_found": len(all_tenders),
            "after_date_filtering": len(filtered_for_agent2),
            "after_duplicate_removal": len(saved_basic),
            "processed_by_agent2": len([t for t in detailed_results if t.get("processing_status") == "completed"]),
            "skipped_by_agent2": len([t for t in detailed_results if t.get("processing_status") == "skipped"]),
        },
    }
