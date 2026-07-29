"""
Updated Background Scheduler Service with Agent 3 Integration
Extended pipeline: Main Page → Agent1 → DB1 → Agent2 → DB2 → Agent3 → Enhanced Email
"""
import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any
import logging
from sqlalchemy.orm import Session
from app.core.database import get_db, SessionLocal
from app.core.config import settings
from app.models import MonitoredPage, DetailedTender, Keyword, CrawlLog
from app.models.tender import Tender
from app.agents import TenderAgent
from app.services.email_service import EnhancedEmailService
from app.repositories.tender_repository import TenderRepository
from app.repositories.page_repository import PageRepository
from app.repositories.keyword_repository import KeywordRepository
from app.repositories.email_settings_repository import EmailSettingsRepository
from app.crawl.eligibility import is_monitored_page_due_for_crawl
from app.crawl.orchestrator import harvest_for_page
from app.utils.listing_prep import dual_markdown_for_agent1_and_expiry
from app.utils.tender_expiry import filter_expired_compositions, partition_notifiable
from app.pipeline.crawl_artifact import crawl_artifact_from_harvest
from app.pipeline.progress import pipeline_tty
from app.services.db_backup import run_scheduled_backup
from app.services.crawl_schedule import (
    next_scheduled_crawl_utc,
    schedule_description,
    seconds_until_next_crawl,
    uses_weekday_schedule,
)

logger = logging.getLogger(__name__)


def _normalize_crawl_strategy(page: MonitoredPage) -> str:
    return (getattr(page, "crawl_strategy", None) or "crawl4ai").strip().lower()


def _force_simple_pipeline_for_strategy(strategy: str) -> bool:
    # API-backed structured sources should bypass checklist/langgraph Agent 1.
    return strategy in {"un_careers", "eu_funding"}


def _force_simple_pipeline_for_harvest(harvest) -> bool:
    meta = getattr(harvest, "session_meta", None) or {}
    if meta.get("backend") == "worldbank_procnotices_api":
        return True
    if meta.get("structured_source") and meta.get("listing_rows_v1"):
        return True
    return False


class TenderScheduler:
    """Background scheduler with Agent 3 integration for intelligent email notifications"""
    
    def __init__(self):
        self.tender_agent = TenderAgent()
        self.email_service = EnhancedEmailService()  # Updated to enhanced service
        self.tender_repo = TenderRepository()
        self.page_repo = PageRepository()
        self.keyword_repo = KeywordRepository()
        self.running = False
        self.task = None
        self.retry_task = None
        self.extraction_in_progress = False
        self.extraction_started_at: str | None = None
        self.last_extraction_at: str | None = None
        self.next_extraction_at: str | None = None
        self.last_backup_at: str | None = None
        self.last_backup_filename: str | None = None
        self.last_backup_error: str | None = None
    
    async def start(self):
        """Start the periodic crawling scheduler"""
        if self.running:
            return
        
        self.running = True
        logger.info("Starting extended tender monitoring pipeline with Agent 3...")
        if uses_weekday_schedule():
            logger.info("Scheduler will run on %s", schedule_description())
        else:
            interval_hours = settings.CRAWL_INTERVAL_HOURS
            interval_label = (
                f"{interval_hours // 24} day(s)"
                if interval_hours % 24 == 0 and interval_hours >= 24
                else f"{interval_hours} hour(s)"
            )
            logger.info("Scheduler will run every %s", interval_label)
        logger.info("Extended Pipeline: Main Page -> Agent1 -> DB1 -> Agent2 -> DB2 -> Agent3 -> Enhanced Email")

        if uses_weekday_schedule():
            from datetime import datetime, timezone
            self.next_extraction_at = next_scheduled_crawl_utc().isoformat()
        else:
            from datetime import datetime, timedelta, timezone
            interval_seconds = settings.CRAWL_INTERVAL_HOURS * 3600
            self.next_extraction_at = (
                datetime.now(timezone.utc) + timedelta(seconds=interval_seconds)
            ).isoformat()

        # Start periodic task
        self.task = asyncio.create_task(self._periodic_task())
        if bool(getattr(settings, "EMAIL_RETRY_ENABLED", True)):
            retry_minutes = int(getattr(settings, "EMAIL_RETRY_INTERVAL_MINUTES", 30))
            logger.info(
                "Email retry worker enabled: failed recipients retried every %s minute(s)",
                retry_minutes,
            )
            self.retry_task = asyncio.create_task(self._email_retry_task())
        if bool(getattr(settings, "BACKUP_ENABLED", True)):
            logger.info(
                "Database backup configured for post-extraction weekdays: %s",
                getattr(settings, "BACKUP_AFTER_EXTRACTION_WEEKDAYS", "monday,thursday"),
            )
    
    async def stop(self):
        """Stop the periodic crawling"""
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        if self.retry_task:
            self.retry_task.cancel()
            try:
                await self.retry_task
            except asyncio.CancelledError:
                pass
        logger.info("Scheduler stopped")

    def _post_extraction_backup_weekday_indexes(self) -> set[int]:
        """Return configured weekday indexes (Monday=0 ... Sunday=6) for post-run backups."""
        raw = str(getattr(settings, "BACKUP_AFTER_EXTRACTION_WEEKDAYS", "monday,thursday") or "")
        mapping = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }
        days: set[int] = set()
        for part in raw.split(","):
            key = part.strip().lower()
            if key in mapping:
                days.add(mapping[key])
        # Safe fallback to requested default behavior.
        return days or {0, 3}

    async def _run_post_extraction_backup_if_due(self):
        """Run a DB backup after extraction when today's weekday is configured."""
        from datetime import datetime, timezone

        if not bool(getattr(settings, "BACKUP_ENABLED", True)):
            return
        if not bool(getattr(settings, "BACKUP_AFTER_EXTRACTION_ENABLED", True)):
            return

        now_utc = datetime.now(timezone.utc)
        scheduled_days = self._post_extraction_backup_weekday_indexes()
        if now_utc.weekday() not in scheduled_days:
            return

        try:
            info = await asyncio.to_thread(run_scheduled_backup)
            if info is not None:
                self.last_backup_at = now_utc.isoformat()
                self.last_backup_filename = info.filename
                self.last_backup_error = None
                logger.info(
                    "Post-extraction DB backup completed: %s",
                    info.filename,
                )
        except Exception as e:
            self.last_backup_error = str(e)
            logger.error("Post-extraction DB backup failed: %s", e)
    
    async def _periodic_task(self):
        """Run extraction on configured weekdays (or fixed interval fallback)."""
        from datetime import datetime, timezone

        while self.running:
            try:
                if uses_weekday_schedule():
                    self.next_extraction_at = next_scheduled_crawl_utc().isoformat()
                else:
                    from datetime import timedelta
                    interval_seconds = settings.CRAWL_INTERVAL_HOURS * 3600
                    self.next_extraction_at = (
                        datetime.now(timezone.utc) + timedelta(seconds=interval_seconds)
                    ).isoformat()

                sleep_seconds = seconds_until_next_crawl()
                logger.info(
                    "Next scheduled extraction at %s (sleep %.0fs)",
                    self.next_extraction_at,
                    sleep_seconds,
                )
                await asyncio.sleep(sleep_seconds)
                if self.running:
                    # Scheduled ticks respect each page's crawl_frequency_hours so a
                    # large page set can be staggered instead of all firing at once.
                    # Manual triggers still default to force=True.
                    await self.run_extraction_once(
                        force=bool(getattr(settings, "SCHEDULED_CRAWL_FORCE_ALL_PAGES", False))
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic task: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying

    async def _email_retry_task(self):
        """Retry failed recipient sends at fixed intervals."""
        while self.running:
            try:
                interval_minutes = max(
                    1, int(getattr(settings, "EMAIL_RETRY_INTERVAL_MINUTES", 30))
                )
                await asyncio.sleep(interval_minutes * 60)
                if not self.running:
                    break
                summary = await self.email_service.retry_failed_notifications()
                if summary.get("due", 0):
                    logger.info(
                        "Email retry pass completed: due=%s retried=%s sent=%s failed=%s dropped=%s",
                        summary.get("due", 0),
                        summary.get("retried", 0),
                        summary.get("sent", 0),
                        summary.get("failed", 0),
                        summary.get("dropped", 0),
                    )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Email retry worker error: %s", exc)
                await asyncio.sleep(60)
    
    async def run_extraction_once(self, force: bool = False):
        """Run the extended extraction pipeline once.

        Args:
            force: If True, ignore per-page crawl_frequency_hours (e.g. manual trigger).
        """
        from datetime import datetime, timezone

        # A cycle can run for hours with many pages, which makes it easy to trigger
        # a second one by hand while the first is still going. Two concurrent cycles
        # double the LLM spend and have both writing the same tables, so refuse.
        if self.extraction_in_progress:
            logger.warning(
                "Extraction already in progress (started %s) — ignoring this request",
                self.extraction_started_at,
            )
            return {"skipped": True, "reason": "extraction_already_in_progress"}

        self.extraction_in_progress = True
        self.extraction_started_at = datetime.now(timezone.utc).isoformat()
        logger.info("Starting extended tender extraction cycle with Agent 3...")

        try:
            # Step 1: Snapshot the active pages, then release the session. Page work
            # gets its own session each so nothing holds one open for the cycle.
            db = SessionLocal()
            try:
                pages = self.page_repo.get_active_pages(db)
                page_ids = [page.id for page in pages]
                page_names = {page.id: page.name or page.url for page in pages}
            finally:
                db.close()

            if not page_ids:
                logger.warning("No active monitored pages found")
                return

            max_concurrent = max(1, int(getattr(settings, "MAX_CONCURRENT_PAGES", 3) or 1))
            logger.info(
                "Processing %s pages (force=%s, up to %s at a time)",
                len(page_ids),
                force,
                max_concurrent,
            )
            _pm = (settings.PIPELINE_MODE or "simple").strip().lower()
            if _pm in ("langgraph", "legacy"):
                logger.info("Pipeline mode=%s (LangGraph + checklist Agent 1)", _pm)
            else:
                logger.info(
                    "Pipeline mode=%s (crawler artifact → ListingStructureAgent → Agent 2/3)",
                    _pm,
                )

            # Step 2: Process pages concurrently, bounded, each isolated so one
            # failure or timeout cannot take the rest of the cycle with it.
            semaphore = asyncio.Semaphore(max_concurrent)
            results = await asyncio.gather(
                *(
                    self._process_page_guarded(page_id, force, semaphore)
                    for page_id in page_ids
                ),
                return_exceptions=True,
            )

            total_new_tenders = 0
            all_email_compositions: List[Dict[str, Any]] = []
            failed_pages = 0
            for page_id, result in zip(page_ids, results):
                if isinstance(result, BaseException):
                    failed_pages += 1
                    logger.error(
                        "Page %s (%s) failed: %s",
                        page_id,
                        page_names.get(page_id, "?"),
                        result,
                    )
                    continue
                total_new_tenders += result.get("new_tenders_count", 0)
                all_email_compositions.extend(result.get("email_compositions", []))

            if failed_pages:
                logger.warning("%s of %s pages failed this cycle", failed_pages, len(page_ids))

            # Step 3: Tail work on a fresh short-lived session.
            db = SessionLocal()
            try:
                # Automatic catch-up for pending detail extraction so users don't
                # need to click "Retry pending details (batch)" manually every run.
                if total_new_tenders > 0:
                    await self._auto_retry_pending_details(db)

                # Send exactly one digest email for all currently unnotified,
                # processed, screening-passed tenders.
                await self._send_single_cycle_digest(db)
            finally:
                db.close()

            logger.info(f"Extended extraction cycle completed - {total_new_tenders} new tenders processed with {len(all_email_compositions)} intelligent emails")

        except Exception as e:
            logger.error(f"Error in extended extraction cycle: {e}")
        finally:
            self.extraction_in_progress = False
            self.extraction_started_at = None
            self.last_extraction_at = datetime.now(timezone.utc).isoformat()
            await self._run_post_extraction_backup_if_due()

    async def _process_page_guarded(
        self,
        page_id: int,
        force: bool,
        semaphore: asyncio.Semaphore,
    ) -> Dict[str, Any]:
        """
        Run one page with its own DB session, a concurrency slot and a hard timeout.

        The page is re-loaded inside this session rather than passed in, because an
        ORM object belongs to the session that produced it.
        """
        empty: Dict[str, Any] = {"new_tenders_count": 0, "email_compositions": []}
        timeout = max(60, int(getattr(settings, "PAGE_PROCESSING_TIMEOUT_SEC", 1800) or 1800))

        async with semaphore:
            db = SessionLocal()
            try:
                page = self.page_repo.get_page_by_id(db, page_id)
                if not page or not page.is_active:
                    logger.info("Page %s is gone or inactive, skipping", page_id)
                    return empty

                try:
                    return await asyncio.wait_for(
                        self._process_page_extended_pipeline(db, page, force=force),
                        timeout=timeout,
                    )
                except asyncio.TimeoutError:
                    logger.error(
                        "Page %s (%s) exceeded the %ss budget — abandoning it so the "
                        "rest of the cycle continues",
                        page_id,
                        page.name or page.url,
                        timeout,
                    )
                    self._fail_unfinished_crawl_log(
                        db, page, f"Timed out after {timeout}s"
                    )
                    return empty
            except Exception as exc:
                logger.error("Page %s raised: %s", page_id, exc)
                return empty
            finally:
                db.close()

    def _fail_unfinished_crawl_log(
        self, db: Session, page: MonitoredPage, message: str
    ) -> None:
        """Close out the crawl log and failure counters for an abandoned page."""
        try:
            db.rollback()
            crawl_log = (
                db.query(CrawlLog)
                .filter(CrawlLog.page_id == page.id, CrawlLog.completed_at.is_(None))
                .order_by(CrawlLog.started_at.desc())
                .first()
            )
            if crawl_log:
                crawl_log.status = "failed"
                crawl_log.error_message = message
                crawl_log.completed_at = datetime.utcnow()
            page.consecutive_failures = (page.consecutive_failures or 0) + 1
            page.last_crawled = datetime.utcnow()
            db.commit()
        except Exception as exc:
            logger.error("Could not record the abandoned run for page %s: %s", page.id, exc)
            db.rollback()


    async def _process_page_extended_pipeline(
        self, db: Session, page: MonitoredPage, force: bool = False
    ) -> Dict[str, Any]:
        """
        Process a single monitored page through the extended pipeline with Agent 3
        
        Extended Pipeline Flow:
        1. Harvest main page (crawl4ai or future Playwright) → markdown
        2. Agent 1: Extract & categorize tenders from main page → Save to DB1
        3. Agent 2: Extract details from individual tender pages → Save to DB2
        4. Agent 3: Compose intelligent email content
        5. Return email compositions for sending
        """
        if not force and not is_monitored_page_due_for_crawl(page):
            logger.info(
                "Skipping page %s (id=%s): not due (crawl_frequency_hours=%s, last_crawled=%s)",
                page.name,
                page.id,
                page.crawl_frequency_hours,
                page.last_crawled.isoformat() if page.last_crawled else None,
            )
            return {'new_tenders_count': 0, 'email_compositions': [], 'skipped': True}
        logger.info(f"Processing page through extended pipeline: {page.name} ({page.url})")
        
        # Create crawl log
        crawl_log = CrawlLog(
            page_id=page.id,
            status="started",
            started_at=datetime.utcnow()
        )
        db.add(crawl_log)
        db.commit()
        
        try:
            strategy = _normalize_crawl_strategy(page)
            logger.info(
                "Harvesting page %s via strategy=%s",
                page.url,
                strategy,
            )
            harvest = await harvest_for_page(page)

            if harvest.status != "success":
                error_msg = harvest.error or "Harvest failed"
                logger.error(f"Failed to harvest main page {page.url}: {error_msg}")

                crawl_log.status = "failed"
                crawl_log.error_message = error_msg
                crawl_log.completed_at = datetime.utcnow()
                db.commit()

                page.consecutive_failures += 1
                page.last_crawled = datetime.utcnow()
                db.commit()
                return {'new_tenders_count': 0, 'email_compositions': []}

            logger.info(
                "Successfully harvested main page: %s characters (links=%s)",
                len(harvest.markdown or ""),
                len(harvest.listing_urls),
            )

            crawl_artifact = crawl_artifact_from_harvest(harvest)
            pipeline_mode = (settings.PIPELINE_MODE or "simple").strip().lower()
            force_simple_pipeline = (
                _force_simple_pipeline_for_strategy(strategy)
                or _force_simple_pipeline_for_harvest(harvest)
            )
            if pipeline_mode in ("langgraph", "legacy"):
                agent_md, listing_for_expiry = dual_markdown_for_agent1_and_expiry(
                    page.url,
                    harvest.markdown or "",
                    harvest.listing_urls,
                    html=harvest.html,
                )
                crawl_artifact_kw = crawl_artifact if force_simple_pipeline else None
            else:
                agent_md = harvest.markdown or ""
                listing_for_expiry = harvest.markdown or ""
                crawl_artifact_kw = crawl_artifact

            pipeline_tty(
                f"[PIPELINE] · handoff | {len(harvest.markdown or ''):,} chars | "
                f"links={len(harvest.listing_urls)} | pipeline={pipeline_mode}"
                f"{' | pages=' + str((harvest.session_meta or {}).get('pages_captured') or (harvest.session_meta or {}).get('pages_attempted') or '?') + '/' + str((harvest.session_meta or {}).get('max_pages') or '?') if (harvest.session_meta or {}) else ''}"
                f"{'→simple-forced' if force_simple_pipeline else ''}"
            )

            try:
                logger.info("Starting extended agent pipeline with Agent 3...")

                result = await self.tender_agent.process_page(
                    page_content=agent_md,
                    page_url=page.url,
                    page_id=page.id,
                    tender_repo=self.tender_repo,
                    db=db,
                    listing_markdown_for_expiry=listing_for_expiry,
                    crawl_artifact=crawl_artifact_kw,
                    force_simple_pipeline=force_simple_pipeline,
                )

                logger.info("Extended agent pipeline completed")

            except Exception as workflow_error:
                logger.error(
                    f"Extended agent pipeline failed for page {page.url}: {workflow_error}"
                )

                crawl_log.status = "failed"
                crawl_log.error_message = f"Extended agent pipeline error: {str(workflow_error)}"
                crawl_log.completed_at = datetime.utcnow()
                db.commit()

                page.consecutive_failures += 1
                page.last_crawled = datetime.utcnow()
                db.commit()
                return {'new_tenders_count': 0, 'email_compositions': []}

            if result.get('workflow_failed'):
                error_msg = result.get('error', 'Extended workflow failed')
                logger.error(f"Extended workflow failed for page {page.url}: {error_msg}")

                crawl_log.status = "failed"
                crawl_log.error_message = error_msg
                crawl_log.completed_at = datetime.utcnow()
                db.commit()

                page.consecutive_failures += 1
                page.last_crawled = datetime.utcnow()
                db.commit()
                return {'new_tenders_count': 0, 'email_compositions': []}

            basic_count = result.get('total_saved_basic', 0)
            detailed_count = result.get('total_saved_detailed', 0)
            email_count = result.get('total_email_compositions', 0)
            duplicate_count = result.get('duplicate_count', 0)

            logger.info(f"Extended Pipeline Results for {page.name}:")
            logger.info(f"   Basic tenders saved to DB1: {basic_count}")
            logger.info(f"   Detailed tenders saved to DB2: {detailed_count}")
            logger.info(f"   Email compositions created: {email_count}")
            logger.info(f"   Duplicates filtered: {duplicate_count}")

            crawl_log.status = "completed"
            crawl_log.tenders_found = basic_count
            crawl_log.tenders_new = basic_count
            crawl_log.completed_at = datetime.utcnow()
            db.commit()

            page.consecutive_failures = 0
            page.last_crawled = datetime.utcnow()
            page.last_successful_crawl = datetime.utcnow()
            db.commit()

            logger.info(f"Successfully processed page {page.url} through extended pipeline")

            return {
                'new_tenders_count': basic_count,
                'email_compositions': result.get('email_compositions', []),
            }
        except Exception as e:
            logger.error(f"Error processing page {page.url} through extended pipeline: {e}")
            
            # Update crawl log with error
            crawl_log.status = "failed"
            crawl_log.error_message = str(e)
            crawl_log.completed_at = datetime.utcnow()
            db.commit()
            
            # Update page failure count
            page.consecutive_failures += 1
            page.last_crawled = datetime.utcnow()
            db.commit()
            return {'new_tenders_count': 0, 'email_compositions': []}
    
    async def _send_intelligent_notifications(self, email_compositions: List[Dict[str, Any]]):
        """Send intelligent notifications using Agent 3 composed content"""
        try:
            if not email_compositions:
                logger.info("No email compositions to send")
                return

            email_compositions, expired_count = filter_expired_compositions(email_compositions)
            if expired_count:
                logger.info(
                    "Intelligent digest: dropped %s closed opportunity/ies", expired_count
                )
            if not email_compositions:
                logger.info("No open opportunities left to send after the expiry gate")
                return

            logger.info(f"Sending {len(email_compositions)} intelligent email notifications...")
            
            # Send all intelligent notifications
            results = await self.email_service.send_intelligent_notifications(email_compositions)
            
            # Log results
            logger.info(f"Intelligent email results:")
            logger.info(f"   Total compositions: {results['total_compositions']}")
            logger.info(f"   Sent successfully: {results['sent_successfully']}")
            logger.info(f"   Failed sends: {results['failed_sends']}")
            
            if results['errors']:
                logger.warning("Email sending errors:")
                for error in results['errors']:
                    logger.warning(
                        "   - %s: %s",
                        error.get('tender_title', '(unknown)'),
                        error.get('error', error),
                    )

            if results['sent_emails']:
                logger.info("Successfully sent intelligent emails:")
                for email in results['sent_emails']:
                    logger.info(
                        "   - %s to %s team (Priority: %s)",
                        email.get('tender_title', email.get('subject', '(unknown)')),
                        email.get('team_category', '(unknown)'),
                        email.get('priority', 'Medium'),
                    )
            
        except Exception as e:
            logger.error(f"Error sending intelligent notifications: {e}")
    
    async def _send_fallback_notifications(self, db: Session):
        """Send fallback notifications for any unnotified tenders (when Agent 3 fails)"""
        try:
            logger.info("Checking for unnotified tenders (fallback notifications)...")
            
            # Only notify (and mark is_notified) for tenders that finished Agent 2.
            unnotified_tenders = self.tender_repo.get_unnotified_tenders(
                db, only_passed=True, require_processed=True
            )
            if not unnotified_tenders:
                logger.info("No unnotified screened opportunities found for fallback notifications")
                return

            # This query spans the whole backlog, not just this run, so rows that
            # were live when saved may have closed since. Re-check against today.
            # Suppressed rows keep ``is_notified=False`` on purpose: if a deadline
            # is ever misparsed, the opportunity stays recoverable instead of being
            # permanently marked as handled.
            unnotified_tenders, expired_tenders = partition_notifiable(unnotified_tenders)
            if expired_tenders:
                logger.info(
                    "Fallback digest: suppressed %s closed opportunity/ies", len(expired_tenders)
                )

            if not unnotified_tenders:
                logger.info("No open screened opportunities left to notify after the expiry gate")
                return

            logger.info(
                "Sending fallback screening notification for %s opportunities",
                len(unnotified_tenders),
            )
            success = await self.email_service.send_fallback_notifications(
                unnotified_tenders,
                "screening_opportunities",
            )
            if success:
                for tender in unnotified_tenders:
                    self.tender_repo.mark_tender_notified(db, tender.id)
                logger.info(
                    "Fallback notifications sent for %s opportunities",
                    len(unnotified_tenders),
                )
            else:
                logger.error("Failed to send fallback screening notifications")
                
        except Exception as e:
            logger.error(f"Error sending fallback notifications: {e}")

    async def _auto_retry_pending_details(self, db: Session):
        """
        Automatic catch-up pass after extraction:
        - Retry Agent 2 for pending recommended tenders
        - Do not send emails here; notifications are sent once at cycle end
          as one consolidated digest.
        """
        try:
            from app.services.agent2_retry import retry_pending_details_bulk

            logger.info(
                "Auto catch-up: retrying pending detail extraction (recommended only, notifications disabled)"
            )
            result = await retry_pending_details_bulk(
                db,
                limit=50,
                only_passed_screening=True,
                # Pending rows often need permissive retry path.
                skip_date_validation=True,
                send_notifications=False,
            )
            logger.info(
                "Auto catch-up done: attempted=%s completed=%s",
                result.get("attempted", 0),
                result.get("completed", 0),
            )
        except Exception as exc:
            logger.error("Auto catch-up retry failed: %s", exc)

    async def _send_single_cycle_digest(self, db: Session):
        """
        Send one consolidated digest email containing all currently unnotified,
        screening-passed tenders that completed Agent 2 detail extraction.
        """
        try:
            tenders = self.tender_repo.get_unnotified_tenders(
                db, only_passed=True, require_processed=True
            )
            if not tenders:
                logger.info("No unnotified processed screened tenders found for cycle digest")
                return

            # The backlog is not time-bounded: anything that waited on an Agent 2
            # retry, or on a send that failed, may have closed in the meantime.
            # Filter on ORM rows rather than compositions, because the row still
            # has the detail-page deadline and the listing deadline to consult.
            tenders, expired_tenders = partition_notifiable(tenders)
            if expired_tenders:
                logger.info(
                    "Cycle digest: suppressed %s closed opportunity/ies", len(expired_tenders)
                )
            if not tenders:
                logger.info("No open screened opportunities left for the cycle digest")
                return

            logger.info(
                "Sending one consolidated digest for %s screened opportunities",
                len(tenders),
            )

            compositions: List[Dict[str, Any]] = []
            for tender in tenders:
                compositions.append(
                    {
                        "tender_data": {
                            "id": tender.id,
                            "title": tender.title,
                            "url": tender.url,
                            "date": tender.tender_date.strftime("%Y-%m-%d")
                            if tender.tender_date
                            else "Not specified",
                        },
                        "email_content": {
                            "tender_id": tender.id,
                            "team_category": "screening_opportunities",
                            "subject": f"New SCREENING OPPORTUNITIES Tenders - {len(tenders)} Opportunities Found",
                            "priority": "Medium",
                            "summary": "Consolidated digest for this cycle.",
                            "html_body": "",
                        },
                        "composition_status": "success",
                        "email_type": "digest",
                    }
                )

            results = await self.email_service.send_intelligent_notifications(compositions)
            logger.info(
                "Cycle digest send result: sent=%s failed=%s",
                results.get("sent_successfully", 0),
                results.get("failed_sends", 0),
            )
        except Exception as exc:
            logger.error("Error sending single cycle digest: %s", exc)
    
    async def test_extended_pipeline(self):
        """Test the extended pipeline with Agent 3 (for development)"""
        logger.info("Running extended pipeline test with Agent 3...")
        await self.run_extraction_once(force=True)
        logger.info("Extended pipeline test completed")
    
    async def test_agent3_email_composition(self, test_email: str = None):
        """Test Agent 3 email composition and sending"""
        try:
            logger.info("Testing Agent 3 email composition...")
            
            if not test_email:
                test_email = settings.SCREENING_DEFAULT_TEST_EMAIL
                if not test_email:
                    db = SessionLocal()
                    try:
                        email_repo = EmailSettingsRepository()
                        recipients = email_repo.get_emails_by_category(
                            db, "screening_opportunities"
                        )
                        test_email = recipients[0] if recipients else None
                    finally:
                        db.close()
                if not test_email:
                    logger.error(
                        "No test email provided and no SCREENING_DEFAULT_TEST_EMAIL "
                        "or configured screening notification recipients"
                    )
            
            # Send test intelligent email
            result = await self.email_service.send_test_intelligent_email(test_email)
            
            if result['status'] == 'success':
                logger.info(f"Agent 3 test email sent successfully to {test_email}")
                logger.info(f"Email preview: {result['email_content_preview']}")
            else:
                logger.error(f"Agent 3 test email failed: {result['message']}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error testing Agent 3 email composition: {e}")
            return {'status': 'failed', 'message': str(e)}

# Additional utility functions for monitoring the extended pipeline
async def test_extended_pipeline():
    """Test function for the extended pipeline with Agent 3"""
    scheduler = TenderScheduler()
    await scheduler.test_extended_pipeline()

async def test_agent3_emails(test_email: str = None):
    """Test Agent 3 email composition"""
    scheduler = TenderScheduler()
    return await scheduler.test_agent3_email_composition(test_email)

def get_extended_pipeline_status():
    """Get status of the extended pipeline including Agent 3"""
    db = SessionLocal()
    try:
        # Get recent crawl logs
        recent_logs = db.query(CrawlLog).order_by(CrawlLog.started_at.desc()).limit(10).all()
        
        # Get unnotified tenders
        tender_repo = TenderRepository()
        unnotified_screened = len(tender_repo.get_unnotified_tenders(db, only_passed=True))
        
        # Get recent detailed tenders (for Agent 3 email composition)
        recent_detailed = db.query(DetailedTender).order_by(DetailedTender.created_at.desc()).limit(5).all()
        
        return {
            "status": "extended_pipeline_with_agent3_active",
            "pipeline_version": "3.0",
            "agents_active": ["Agent1_Extract", "Agent2_Details", "Agent3_EmailComposer"],
            "recent_crawls": len(recent_logs),
            "unnotified_tenders": {
                "screened_passed": unnotified_screened,
                "total": unnotified_screened,
            },
            "recent_detailed_extractions": len(recent_detailed),
            "last_crawl": recent_logs[0].started_at.isoformat() if recent_logs else None,
            "pipeline_flow": "Main Page -> Agent1 -> DB1 -> Agent2 -> DB2 -> Agent3 -> Enhanced Email"
        }
    finally:
        db.close()

if __name__ == "__main__":
    import asyncio
    
    # Test the extended pipeline
    asyncio.run(test_extended_pipeline())