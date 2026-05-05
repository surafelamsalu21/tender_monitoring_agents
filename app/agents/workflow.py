"""
Updated Workflow Configuration with Date Filtering Options
Supports both filtered and unfiltered tender extraction
"""
import logging
from typing import Dict, List, Any, TypedDict, Optional, NotRequired
from langgraph.graph import StateGraph, END, START
from datetime import datetime

from .screening_agent import ScreeningExtractionAgent
from .agent1 import use_fast_agent1_pipeline
from .agent2 import TenderDetailAgent
from .agent3 import EmailComposerAgent
from app.models import Keyword
from app.core.config import settings
from app.utils.tender_deadline_gate import filter_expired_agent1_items
from app.pipeline.schemas import CrawlArtifactV1
from app.pipeline.progress import pipeline_tty, active_llm_label

logger = logging.getLogger(__name__)


def _workflow_url_key(url: Optional[str]) -> str:
    return (url or "").strip().rstrip("/")


def _basic_tender_matches_detailed_url(
    saved_tender: Any,
    detail_url: Optional[str],
    agent1_url_by_tender_id: Dict[int, str],
) -> bool:
    """Match DB1 row to Agent 2 output: ORM.url may still be a listing URL after dedupe."""
    key = _workflow_url_key(detail_url)
    if not key:
        return False
    if _workflow_url_key(getattr(saved_tender, "url", None)) == key:
        return True
    mapped = agent1_url_by_tender_id.get(int(getattr(saved_tender, "id", 0) or 0), "")
    return _workflow_url_key(mapped) == key


class WorkflowState(TypedDict):
    # --- Input parameters provided at the start of the workflow ---
    page_content: str                         # Markdown / text passed to Agent 1 (may be slimmed per source)
    listing_markdown_for_expiry: str           # Full listing scrape for post–Agent 1 deadline gate (PDF table rows, etc.)
    page_url: str                             # URL of the scraped page
    page_id: int                              # Unique page identifier for DB-relation and dedupe
    screening_config: Dict[str, Any]          # Screening checklist configuration
    tender_repo: Any                          # Data repository, must offer DB ops methods
    db: Any                                   # Database session/connection/context

    # --- Pipeline control: options for tender filtering and saving ---
    enable_date_filtering: bool               # True: Only strong matches (≥3 YES) go to Agent 2; False: all kept rows
    include_all_for_db1: bool                 # Deprecated — all non-excluded rows are always saved to DB1

    # --- Outputs / intermediate states (Agent 1) ---
    extracted_tenders: List[Dict[str, Any]]   # Raw tenders extracted (subject to deduplication)
    all_tenders: List[Dict[str, Any]]         # All tenders found on page, unfiltered (for reference)
    filtered_tenders: List[Dict[str, Any]]    # Tenders after date filtering
    saved_basic_tenders: List[Any]            # Tenders actually saved to DB1

    # --- Agent 2 input/output ---
    tenders_for_agent2: List[Dict[str, Any]]  # Tenders accepted for detailed processing (normally date-filtered)
    detailed_tenders: List[Dict[str, Any]]    # Agent 2 results: detailed info, status, and enriched fields
    saved_detailed_tenders: List[Any]         # Details saved to DB2

    # --- Agent 3 input/output ---
    email_compositions: List[Dict[str, Any]]  # Email contents generated for final notification/alerting

    # --- Status/diagnostic flags ---
    agent1_completed: bool                    # Agent 1 ran
    agent2_completed: bool                    # Agent 2 ran
    agent3_completed: bool                    # Agent 3 ran
    duplicates_checked: bool                  # Dedupe check was performed
    duplicate_count: int                      # Count of tenders removed as duplicates
    filtered_count: int                       # Count filtered out by date (all_tenders - filtered_tenders)
    error: str                                # Exception or failure message
    workflow_failed: bool                     # Pipeline critically failed

    # URL from Agent 1 dict per saved tender id (notice detail URL; may differ from ORM.url)
    agent1_detail_url_by_tender_id: NotRequired[Dict[int, str]]

class TenderAgent:
    """Enhanced workflow orchestrator with configurable date filtering"""
    
    def __init__(self):
        # Instantiate each agent for workflow steps: extraction, enrichment, email composition
        self.agent1 = ScreeningExtractionAgent()
        self.agent2 = TenderDetailAgent()
        self.agent3 = EmailComposerAgent()
        # Build the core workflow DAG using StateGraph abstraction
        self.workflow = self._build_workflow()

    def _build_workflow(self) -> StateGraph:
        """Build the enhanced workflow graph with nodes for each pipeline stage.
        The pipeline consists of:
            Agent 1: Extraction + categorization + (optionally) date filtering
            Duplicate Check: Remove known tenders already in DB
            Save to DB1: Save filtered tenders as basic objects
            Agent 2: Further process for details (with date validation)
            Save to DB2: Save full details
            Agent 3: Compose emails for relevant teams
        """
        workflow = StateGraph(WorkflowState)
        
        # Step nodes for each stage
        workflow.add_node("agent1_extract", self._agent1_extract_node)
        workflow.add_node("check_duplicates", self._check_duplicates_node)
        workflow.add_node("save_to_db1", self._save_to_db1_node)
        workflow.add_node("agent2_details", self._agent2_details_node)
        workflow.add_node("save_to_db2", self._save_to_db2_node)
        workflow.add_node("agent3_compose", self._agent3_compose_node)
        
        # Explicit state transitions to control the workflow pipeline
        workflow.add_edge(START, "agent1_extract")
        workflow.add_edge("agent1_extract", "check_duplicates")
        workflow.add_conditional_edges(
            "check_duplicates",
            self._should_continue_pipeline,  # branch by whether any new tenders are left
            {
                "save_to_db1": "save_to_db1",  # if new tenders remain, continue
                "end": END                     # else, terminate pipeline
            }
        )
        workflow.add_edge("save_to_db1", "agent2_details")
        workflow.add_edge("agent2_details", "save_to_db2")
        workflow.add_edge("save_to_db2", "agent3_compose")
        workflow.add_edge("agent3_compose", END)
        
        return workflow.compile()

    def _tender_identity_key(self, tender: Dict[str, Any]) -> str:
        """
        Build a lightweight in-memory identity key for matching tenders across workflow steps.
        Prefer opportunity fingerprint, fallback to URL+title.
        """
        screening = tender.get("screening", {}) or {}
        step3 = screening.get("step3", {}) or {}
        base = (
            tender.get("opportunity_fingerprint")
            or f"{tender.get('title', '').strip().lower()}|"
               f"{(step3.get('deadline') or tender.get('date') or '').strip()}|"
               f"{(step3.get('source') or '').strip().lower()}|"
               f"{(step3.get('type') or '').strip().lower()}|"
               f"{(step3.get('country') or '').strip().lower()}"
        )
        return base
    
    async def _agent1_extract_node(self, state: WorkflowState) -> WorkflowState:
        """Enhanced Agent 1: Extract opportunities once (weak + strong matches).
        - Agent 1 drops only 0/5 YES or unrelated rows.
        - Strong matches (≥3 YES) feed Agent 2 when date filtering is enabled.
        - All kept rows are saved to DB1 (include_all_for_db1 is deprecated; ignored here).
        """
        import time
        start_time = time.time()

        try:
            logger.info("Agent 1: Starting enhanced tender extraction")
            logger.info(f"Date filtering: {'ENABLED' if state.get('enable_date_filtering', True) else 'DISABLED'}")
            logger.info(f"Agent 1: Content size = {len(state['page_content']):,} chars")
            a1_mode = "fast-2step" if use_fast_agent1_pipeline() else "checklist-1call"
            pipeline_tty(
                f"[AGENT1] · {a1_mode} | {len(state['page_content']):,} chars | llm={active_llm_label()}"
            )

            keyword_hints = None
            db = state.get("db")
            if db is not None:
                try:
                    rows = (
                        db.query(Keyword)
                        .filter(Keyword.is_active == True)
                        .limit(80)
                        .all()
                    )
                    keyword_hints = [k.keyword for k in rows if k.keyword]
                except Exception:
                    keyword_hints = None

            # Single extraction: keep low matches (1–2 YES) for DB/UI; drop only 0/5 or unrelated (Agent 1).
            all_tenders = await self.agent1.extract_and_screen_opportunities(
                page_content=state['page_content'],
                keyword_hints=keyword_hints,
                page_url=state.get('page_url'),
            )

            expiry_dropped = 0
            if settings.SKIP_EXPIRED_AFTER_AGENT1 and all_tenders:
                all_tenders, expiry_dropped = filter_expired_agent1_items(
                    all_tenders,
                    state["listing_markdown_for_expiry"],
                )
                if expiry_dropped:
                    logger.info(
                        "Expiry gate: removed %s closed / past-deadline row(s) after Agent 1",
                        expiry_dropped,
                    )

            strong_matches = [
                t for t in all_tenders
                if bool((t.get("screening") or {}).get("passes_filter"))
            ]

            # filtered_tenders / Agent 2 input: strong matches only when date pipeline is on (saves detail cost).
            if state.get('enable_date_filtering', True):
                filtered_tenders = strong_matches
            else:
                filtered_tenders = all_tenders

            state['all_tenders'] = all_tenders
            state['filtered_tenders'] = filtered_tenders
            state['filtered_count'] = len(all_tenders) - len(filtered_tenders)

            # DB1: all kept rows (weak + strong). Agent 2: strong only when date filtering enabled.
            state['extracted_tenders'] = all_tenders
            state['tenders_for_agent2'] = filtered_tenders

            state['agent1_completed'] = True

            elapsed = time.time() - start_time
            logger.info(f"Agent 1 completed in {elapsed:.1f}s:")
            logger.info(f"   Agent 1 kept (non-excluded): {len(all_tenders)}")
            logger.info(f"   Strong matches (Agent 2 queue): {len(filtered_tenders)}")
            logger.info(f"   Low-match only (saved, no Agent 2): {state['filtered_count']}")
            logger.info(f"   For DB1: {len(state['extracted_tenders'])}")
            logger.info(f"   For Agent 2: {len(state['tenders_for_agent2'])}")
            pipeline_tty(
                f"[AGENT1] · done in {elapsed:.1f}s | kept={len(all_tenders)} | "
                f"strong→A2={len(filtered_tenders)}"
            )

            return state

        except Exception as e:
            logger.error(f"Agent 1 failed: {e}")
            state['extracted_tenders'] = []
            state['all_tenders'] = []
            state['filtered_tenders'] = []
            state['tenders_for_agent2'] = []
            state['agent1_completed'] = True
            state['error'] = str(e)
            return state

    async def _check_duplicates_node(self, state: WorkflowState) -> WorkflowState:
        """Check for known duplicate tenders in DB, filter them out before saving
        - Uses tender_repo to check existence based on title, url, and page.
        - Also updates the Agent 2 input so only new tenders continue.
        - Updates duplicate counters for output reporting.
        """
        try:
            logger.info("Checking for duplicate tenders...")
            extracted_tenders = state['extracted_tenders']
            filtered_tenders = []
            duplicate_count = 0

            for tender in extracted_tenders:
                title = tender.get('title', '')
                url = tender.get('url', '')

                # Defensive: skip incomplete tenders
                if not title or not url:
                    logger.warning(f"Skipping tender with missing title or URL: {tender}")
                    continue

                is_duplicate = state['tender_repo'].check_duplicate_tender(
                    state['db'],
                    title,
                    url,
                    state['page_id'],
                    screening_result=tender.get("screening", {}),
                    tender_date=(
                        tender.get("screening", {}).get("step3", {}).get("deadline")
                        or tender.get("date")
                    ),
                )

                if is_duplicate:
                    duplicate_count += 1
                    logger.info(f"Duplicate found: {title[:50]}...")
                else:
                    filtered_tenders.append(tender)
                    logger.info(f"New tender: {title[:50]}...")

            state['extracted_tenders'] = filtered_tenders
            state['duplicate_count'] = duplicate_count
            state['duplicates_checked'] = True

            # Agent 2 also only processes non-duplicate tenders
            filtered_keys = {self._tender_identity_key(t) for t in filtered_tenders}
            agent2_filtered = []
            for tender in state['tenders_for_agent2']:
                if self._tender_identity_key(tender) in filtered_keys:
                    agent2_filtered.append(tender)
            state['tenders_for_agent2'] = agent2_filtered

            logger.info(f"Filtered out {duplicate_count} duplicates.")
            logger.info(f"New tenders for DB1: {len(filtered_tenders)}")
            logger.info(f"New tenders for Agent 2: {len(state['tenders_for_agent2'])}")
            return state

        except Exception as e:
            logger.error(f"Duplicate checking failed: {e}")
            state['duplicates_checked'] = False
            state['error'] = str(e)
            return state

    def _should_continue_pipeline(self, state: WorkflowState) -> str:
        """
        Used as a conditional branch in the StateGraph.
        If there are no new tenders (after filter and dedupe), the workflow stops early.
        """
        new_tenders = state.get('extracted_tenders', [])
        if len(new_tenders) > 0:
            logger.info(f"Pipeline continuing: {len(new_tenders)} new tenders to process")
            return "save_to_db1"
        else:
            logger.info("No new tenders found. Ending pipeline.")
            return "end"

    async def _save_to_db1_node(self, state: WorkflowState) -> WorkflowState:
        """
        Save basic info about tenders to DB1.
        Each tender is persisted and assigned a DB identifier.
        Failed saves are skipped and logged; successful results collected for Agent 2 matching.
        """
        try:
            logger.info("Saving basic tender info to DB1...")

            saved_tenders = []
            url_by_tender_id: Dict[int, str] = {}

            for tender_data in state['extracted_tenders']:
                tender = state['tender_repo'].save_tender(
                    state['db'],
                    page_id=state['page_id'],
                    title=tender_data['title'],
                    url=tender_data['url'],
                    tender_date=(
                        tender_data.get('screening', {})
                        .get('step3', {})
                        .get('deadline')
                        or tender_data.get('deadline')
                        or tender_data.get('date')
                    ),
                    description=tender_data.get('description', ''),
                    screening_result=tender_data.get('screening', {}),
                )

                if tender:
                    saved_tenders.append(tender)
                    td_url = tender_data.get("url")
                    if td_url:
                        url_by_tender_id[tender.id] = str(td_url).strip()
                    logger.info(f"Saved to DB1: {tender.title[:50]}... (ID: {tender.id})")

            state['saved_basic_tenders'] = saved_tenders
            state['agent1_detail_url_by_tender_id'] = url_by_tender_id
            logger.info(f"DB1 Save completed: {len(saved_tenders)} tenders saved")
            return state

        except Exception as e:
            logger.error(f"DB1 save failed: {e}")
            state['saved_basic_tenders'] = []
            state['error'] = str(e)
            return state

    async def _agent2_details_node(self, state: WorkflowState) -> WorkflowState:
        """
        Agent 2: For all tenders_for_agent2, extract detailed information.
        Optionally skips date validation (if pipeline is running in non-filtering mode).
        Output is a list of dicts with 'processing_status' (completed/skipped/error).
        """
        try:
            logger.info("Agent 2: Starting detailed tender extraction with date validation")

            tenders_to_process = state['tenders_for_agent2']
            skip_date_validation = not state.get('enable_date_filtering', True)

            logger.info(f"Processing {len(tenders_to_process)} tenders for details")
            logger.info(f"Date validation: {'DISABLED' if skip_date_validation else 'ENABLED'}")

            detailed_results = await self.agent2.process_multiple_tenders(
                tender_list=tenders_to_process,
                skip_date_validation=skip_date_validation
            )

            state['detailed_tenders'] = detailed_results
            state['agent2_completed'] = True

            # Log summary of which tenders were processed or skipped
            completed = len([t for t in detailed_results if t.get('processing_status') == 'completed'])
            skipped = len([t for t in detailed_results if t.get('processing_status') == 'skipped'])

            logger.info(f"Agent 2 completed:")
            logger.info(f"   Successfully processed: {completed}")
            logger.info(f"   Skipped (date validation): {skipped}")
            logger.info(f"   Total detailed tenders: {len(detailed_results)}")

            return state

        except Exception as e:
            logger.error(f"Agent 2 failed: {e}")
            state['detailed_tenders'] = []
            state['agent2_completed'] = True
            state['error'] = str(e)
            return state

    async def _save_to_db2_node(self, state: WorkflowState) -> WorkflowState:
        """
        Save detailed info to DB2 (Agent 2 output).
        Only completed (not skipped) tenders are saved.
        Uses match by URL between Agent 2 result and DB1 record.
        """
        try:
            logger.info("Saving detailed tender info to DB2...")

            saved_detailed = []

            for detailed_tender in state['detailed_tenders']:
                # Only process completed (not skipped) tenders
                if detailed_tender.get('processing_status') != 'completed':
                    continue

                try:
                    basic_tender = None
                    tender_url = detailed_tender.get('url')
                    agent1_urls = state.get("agent1_detail_url_by_tender_id") or {}

                    # Match DB1 row by URL OR by Agent 1 notice URL snapshot (dedupe rows
                    # often still have listing-page url on Tender.url).
                    for saved_tender in state['saved_basic_tenders']:
                        if _basic_tender_matches_detailed_url(
                            saved_tender, tender_url, agent1_urls
                        ):
                            basic_tender = saved_tender
                            break

                    if not basic_tender:
                        logger.warning(
                            "No matching basic tender for detail URL %s (saved ids=%s snapshot=%s)",
                            tender_url,
                            [getattr(t, "id", None) for t in state["saved_basic_tenders"]],
                            agent1_urls,
                        )
                        continue

                    detailed_info = detailed_tender.get('detailed_info', {})

                    detailed_tender_obj = state['tender_repo'].save_detailed_tender(
                        state['db'],
                        tender_id=basic_tender.id,
                        detailed_info=detailed_info
                    )

                    if detailed_tender_obj:
                        saved_detailed.append(detailed_tender_obj)
                        logger.info(f"Saved to DB2: {basic_tender.title[:50]}... (Detail ID: {detailed_tender_obj.id})")

                except Exception as e:
                    logger.error(f"Failed to save detailed tender: {e}")
                    continue

            state['saved_detailed_tenders'] = saved_detailed

            logger.info(f"DB2 Save completed: {len(saved_detailed)} detailed tenders saved")
            return state

        except Exception as e:
            logger.error(f"DB2 save failed: {e}")
            state['saved_detailed_tenders'] = []
            state['error'] = str(e)
            return state

    async def _agent3_compose_node(self, state: WorkflowState) -> WorkflowState:
        """
        Agent 3: Compose emails for each tender/category once detailed info is available.
        Only tenders successfully processed to 'completed' state are considered.
        Screening-stage notifications use the unified screening_opportunities recipient list.
        """
        try:
            logger.info("Agent 3: Starting intelligent email composition")

            # Only use successfully completed (not skipped or failed) tenders
            completed_tenders = [
                t for t in state['detailed_tenders']
                if t.get('processing_status') == 'completed'
            ]
            # Email only recommended-tier rows (≥3 Step 1 YES), even if Agent 2 ran in a permissive mode.
            completed_tenders = [
                t for t in completed_tenders
                if bool((t.get('screening') or {}).get('passes_filter'))
            ]

            if not completed_tenders:
                logger.info(
                    "Agent 3: No completed recommended-tier tenders (passes_filter) to compose emails for"
                )
                state['email_compositions'] = []
                state['agent3_completed'] = True
                return state

            email_compositions = []

            logger.info(
                "Agent 3: Composing screening digest for %s passed opportunities",
                len(completed_tenders),
            )
            screening_emails = await self.agent3.compose_multiple_emails(
                completed_tenders,
                "screening_opportunities",
            )
            email_compositions.extend(screening_emails)

            state['email_compositions'] = email_compositions
            state['agent3_completed'] = True

            logger.info(f"Agent 3 completed: {len(email_compositions)} email compositions created")
            logger.info(f"   Based on {len(completed_tenders)} successfully processed tenders")

            return state

        except Exception as e:
            logger.error(f"Agent 3 failed: {e}")
            state['email_compositions'] = []
            state['agent3_completed'] = True
            state['error'] = str(e)
            return state

    async def process_page(
        self,
        page_content: str,
        page_url: str,
        page_id: int,
        tender_repo=None,
        db=None,
        enable_date_filtering: bool = True,
        include_all_for_db1: bool = False,
        screening_config: Dict[str, Any] = None,
        listing_markdown_for_expiry: Optional[str] = None,
        crawl_artifact: Optional[CrawlArtifactV1] = None,
    ) -> Dict[str, Any]:
        """Entry-point: orchestrates the entire tender processing workflow.

        Args:
            page_content:         Content of the scraped webpage (Agent 1 input; may be slimmed for some portals)
            listing_markdown_for_expiry: Optional full listing markdown for closing-date inference;
                defaults to page_content when omitted.
            page_url:             The web page's URL
            page_id:              Unique identifier for logging/dedupe
            tender_repo:          Repo for database ops (must have dedupe/save methods)
            db:                   Database session or object
            enable_date_filtering: When True, only strong matches (≥3 YES) are sent to Agent 2
            include_all_for_db1: Deprecated (ignored); all kept Agent 1 rows are saved to DB1
            crawl_artifact: When set (simple pipeline), Agent 1 uses this markdown — same contract as test crawler.

        Returns:
            A dictionary summarizing workflow outputs and statistics,
            with keys including:
                filtered_tenders, detailed_tenders, email_compositions,
                duplicates_checked, duplicate_count, filtered_count,
                agentX_completed, workflow_failed, error, total counts,
                processing_summary (all major counts)
        """
        
        ex_source = (
            listing_markdown_for_expiry
            if listing_markdown_for_expiry is not None
            else page_content
        )

        pipeline_mode = (settings.PIPELINE_MODE or "simple").strip().lower()
        if pipeline_mode not in ("langgraph", "legacy"):
            try:
                from app.pipeline.simple_orchestrator import run_simple_pipeline

                logger.info("Running pipeline mode=%s (crawler-centric linear)", pipeline_mode)
                return await run_simple_pipeline(
                    page_content=page_content,
                    page_url=page_url,
                    page_id=page_id,
                    listing_markdown_for_expiry=ex_source,
                    tender_repo=tender_repo,
                    db=db,
                    enable_date_filtering=enable_date_filtering,
                    crawl_artifact=crawl_artifact,
                    agent2=self.agent2,
                    agent3=self.agent3,
                    identity_key_fn=self._tender_identity_key,
                )
            except Exception as e:
                logger.error(f"Simple pipeline failed: {e}")
                return {
                    "filtered_tenders": [],
                    "detailed_tenders": [],
                    "email_compositions": [],
                    "duplicates_checked": False,
                    "duplicate_count": 0,
                    "filtered_count": 0,
                    "agent1_completed": False,
                    "agent2_completed": False,
                    "agent3_completed": False,
                    "workflow_failed": True,
                    "error": str(e),
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

        initial_state: WorkflowState = {
            'page_content': page_content,
            'listing_markdown_for_expiry': ex_source,
            'page_url': page_url,
            'page_id': page_id,
            'screening_config': screening_config or {},
            'tender_repo': tender_repo,
            'db': db,

            # Date filtering configuration
            'enable_date_filtering': enable_date_filtering,
            'include_all_for_db1': include_all_for_db1,

            # All outputs/status objects initialized empty/false
            'extracted_tenders': [],
            'all_tenders': [],
            'filtered_tenders': [],
            'tenders_for_agent2': [],
            'saved_basic_tenders': [],
            'detailed_tenders': [],
            'saved_detailed_tenders': [],
            'email_compositions': [],
            'agent1_completed': False,
            'agent2_completed': False,
            'agent3_completed': False,
            'duplicates_checked': False,
            'duplicate_count': 0,
            'filtered_count': 0,
            'error': '',
            'workflow_failed': False,
            'agent1_detail_url_by_tender_id': {},
        }
        
        try:
            logger.info("Starting enhanced tender extraction pipeline with configurable date filtering...")
            logger.info(f"Configuration:")
            logger.info(f"   Date filtering: {'ENABLED' if enable_date_filtering else 'DISABLED'}")
            logger.info(f"   include_all_for_db1 (deprecated): ignored — all kept rows save to DB1")

            # Kick off the async workflow, which manages the full DAG
            result = await self.workflow.ainvoke(initial_state)

            # Compose a comprehensive dictionary for downstream use/UI/diagnostics
            final_result = {
                'filtered_tenders': result.get('saved_basic_tenders', []),        # Tenders that survived all filters and are in DB1
                'detailed_tenders': result.get('detailed_tenders', []),           # Output of Agent 2 (enriched, may include skipped)
                'email_compositions': result.get('email_compositions', []),       # All generated emails
                'duplicates_checked': result.get('duplicates_checked', False),    # Was dedupe check run?
                'duplicate_count': result.get('duplicate_count', 0),              # How many were deduped
                'filtered_count': result.get('filtered_count', 0),                # Kept rows not queued for Agent 2 (low-match only)
                'agent1_completed': result.get('agent1_completed', False),        # Did extraction run
                'agent2_completed': result.get('agent2_completed', False),        # Did Agent 2 run
                'agent3_completed': result.get('agent3_completed', False),        # Did email composition run
                'workflow_failed': bool(result.get('error')),                     # Workflow stopped with an error
                'error': result.get('error', ''),                                 # Top-level error, if any
                # Some summary quantities for quick dashboards/UI
                'total_found': len(result.get('all_tenders', [])),
                'total_saved_basic': len(result.get('saved_basic_tenders', [])),
                'total_saved_detailed': len(result.get('saved_detailed_tenders', [])),
                'total_email_compositions': len(result.get('email_compositions', [])),
                'date_filtering_enabled': enable_date_filtering,
                'processing_summary': {
                    'all_tenders_found': len(result.get('all_tenders', [])),
                    'after_date_filtering': len(result.get('filtered_tenders', [])),  # Strong matches when date pipeline on
                    'after_duplicate_removal': len(result.get('saved_basic_tenders', [])),
                    'processed_by_agent2': len([
                        t for t in result.get('detailed_tenders', []) 
                        if t.get('processing_status') == 'completed'
                    ]),
                    'skipped_by_agent2': len([
                        t for t in result.get('detailed_tenders', []) 
                        if t.get('processing_status') == 'skipped'
                    ])
                }
            }

            logger.info(f"Enhanced pipeline completed successfully!")
            logger.info(f"Processing Summary:")
            logger.info(f"   All tenders found: {final_result['processing_summary']['all_tenders_found']}")
            logger.info(f"   Strong matches (Agent 2 queue): {final_result['processing_summary']['after_date_filtering']}")
            logger.info(f"   After duplicate removal: {final_result['processing_summary']['after_duplicate_removal']}")
            logger.info(f"   Processed by Agent 2: {final_result['processing_summary']['processed_by_agent2']}")
            logger.info(f"   Skipped by Agent 2: {final_result['processing_summary']['skipped_by_agent2']}")
            logger.info(f"   Email compositions: {final_result['total_email_compositions']}")

            return final_result

        except Exception as e:
            logger.error(f"Enhanced pipeline failed: {e}")
            return {
                'filtered_tenders': [],
                'detailed_tenders': [],
                'email_compositions': [],
                'duplicates_checked': False,
                'duplicate_count': 0,
                'filtered_count': 0,
                'agent1_completed': False,
                'agent2_completed': False,
                'agent3_completed': False,
                'workflow_failed': True,
                'error': str(e),
                'total_found': 0,
                'total_saved_basic': 0,
                'total_saved_detailed': 0,
                'total_email_compositions': 0,
                'date_filtering_enabled': enable_date_filtering,
                'processing_summary': {
                    'all_tenders_found': 0,
                    'after_date_filtering': 0,
                    'after_duplicate_removal': 0,
                    'processed_by_agent2': 0,
                    'skipped_by_agent2': 0
                }
            }

# =======================================================================
# DETAILED FILE COMMENTARY
# =======================================================================
#
# This file (app/agents/workflow.py) defines the main control pipeline to process web-scraped tender data
# using a modular multi-agent system that includes: 
#   - Extraction and keyword categorization (Agent 1)
#   - Duplicate detection (via DB lookups)
#   - Optionally date filtering (for recency/relevance)
#   - Saving to two levels of database (basic and detailed objects)
#   - Email composition per team (for actionable new tenders)
#
# Key architectural points:
#  * State is tracked using a TypedDict (WorkflowState) capturing all configuration,
#    intermediate values, error flags, DB results, and status booleans.
#
#  * The pipeline is defined using the langgraph StateGraph DAG, expressing step order,
#    conditional pipeline branching, and stopping if there are no new/interesting tenders.
#
#  * Agent 1 can extract both all-tenders (for audit/analytics) and filtered-tenders
#    for subsequent processing, enabling both monitoring and targeted workflow.
#
#  * Duplicate detection is integrated as an explicit stateful node, ensuring only
#    new tenders are processed and avoiding DB clutter.
#
#  * Each major stage (extraction, detail, notification) is isolated in its own async method,
#    suitable for scaling, testing, or swapping implementation.
#
#  * The process_page entrypoint acts as a complete orchestrator: setting up initial state,
#    running the full async workflow, and returning all important results/statistics
#    as a single rich dictionary.
#
#  * Extensive logging is provided throughout for traceability and production diagnostics.
#
#  * The final output dict, as returned by process_page, enables UI/dashboard/alerting
#    to show pipeline progress, how many tenders were found/skipped/saved/composed, and errors.
#
# Typical usage:
#   result = await TenderAgent().process_page(...)
#   The 'result' object provides both DB-ready outputs (saved tenders, emails)
#   and detailed counters for quality assurance and user feedback.
#
# This modular and detailed-pipeline approach enables robust, customizable tender processing
# that can be extended for new business rules, agents, or notifications as needed.
#