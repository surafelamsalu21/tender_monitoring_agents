"""Linear pipeline: crawl artifact → structure → DB (compat) → Agent 2 → Agent 3."""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional

from app.agents.agent2 import TenderDetailAgent
from app.agents.agent3 import EmailComposerAgent
from app.agents.tender_screening_agent import TenderScreeningAgent
from app.core.config import settings
from app.pipeline.agent1_structure import ListingStructureAgent
from app.pipeline.legacy_adapter import listing_rows_to_tender_dicts
from app.pipeline.progress import active_llm_label, pipeline_tty
from app.pipeline.schemas import CrawlArtifactV1
from app.utils.tender_deadline_gate import filter_expired_agent1_items

logger = logging.getLogger(__name__)


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
    if not (md_source or "").strip():
        return _empty_result(enable_date_filtering, "No markdown content from crawl")

    logger.info("Simple pipeline: start page_id=%s url=%s", page_id, page_url)
    pipeline_tty(f"[PIPELINE] .... page_id={page_id}")
    pipeline_tty(f"[PIPELINE] .... │ {page_url}")
    pipeline_tty(
        f"[PIPELINE] .... │ markdown {len(md_source):,} chars | llm={active_llm_label()}"
    )

    struct_agent = ListingStructureAgent()
    rows = await struct_agent.structure_listing(md_source, page_url)
    all_tenders = listing_rows_to_tender_dicts(rows, page_url)

    if not all_tenders:
        logger.warning("Simple pipeline: 0 tenders after structure + adapter")
        pipeline_tty("[PIPELINE] .... ✗ 0 tenders after structure — check LLM JSON")
        out = _empty_result(enable_date_filtering)
        out["agent1_completed"] = True
        return out

    expiry_dropped = 0
    ex_src = listing_markdown_for_expiry if listing_markdown_for_expiry.strip() else md_source
    if settings.SKIP_EXPIRED_AFTER_AGENT1:
        all_tenders, expiry_dropped = filter_expired_agent1_items(all_tenders, ex_src)
        if expiry_dropped:
            logger.info("Simple pipeline: expiry gate dropped %s row(s)", expiry_dropped)

    pipeline_tty(
        f"[PIPELINE] .... │ rows {len(all_tenders)} | expiry dropped {expiry_dropped}"
    )

    pipeline_tty(f"[PIPELINE] .... ↓ checklist screening | {len(all_tenders)} row(s)")
    screened_tenders = await TenderScreeningAgent().screen_items(all_tenders)
    if screened_tenders:
        all_tenders = [
            tender
            for tender in screened_tenders
            if bool((tender.get("screening") or {}).get("passes_filter"))
        ]
    else:
        all_tenders = []
    pipeline_tty(
        f"[PIPELINE] .... │ checklist kept {len(all_tenders)} relevant row(s)"
    )

    if not all_tenders:
        logger.info("Simple pipeline: nothing relevant after checklist screening")
        out = _empty_result(enable_date_filtering)
        out["agent1_completed"] = True
        out["duplicates_checked"] = True
        return out

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
    for tender in all_tenders:
        title = tender.get("title", "")
        url = tender.get("url", "")
        if not title or not url:
            duplicate_count += 1
            continue
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
