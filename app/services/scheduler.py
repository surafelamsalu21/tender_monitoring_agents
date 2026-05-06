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
from app.pipeline.crawl_artifact import crawl_artifact_from_harvest
from app.pipeline.progress import pipeline_tty
from app.services.db_backup import run_scheduled_backup

logger = logging.getLogger(__name__)


def _normalize_crawl_strategy(page: MonitoredPage) -> str:
    return (getattr(page, "crawl_strategy", None) or "crawl4ai").strip().lower()


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
        self.extraction_in_progress = False
        self.extraction_started_at: str | None = None
        self.last_extraction_at: str | None = None
        self.next_extraction_at: str | None = None
        self.backup_task: Optional[asyncio.Task] = None
        self.last_backup_at: str | None = None
        self.last_backup_filename: str | None = None
        self.last_backup_error: str | None = None
    
    async def start(self):
        """Start the periodic crawling scheduler"""
        if self.running:
            return
        
        self.running = True
        logger.info("Starting extended tender monitoring pipeline with Agent 3...")
        logger.info(f"Scheduler will run every {settings.CRAWL_INTERVAL_HOURS} hours")
        logger.info("Extended Pipeline: Main Page -> Agent1 -> DB1 -> Agent2 -> DB2 -> Agent3 -> Enhanced Email")

        # Start periodic task
        self.task = asyncio.create_task(self._periodic_task())

        # Start independent backup loop (skipped at runtime if BACKUP_ENABLED=False)
        if bool(getattr(settings, "BACKUP_ENABLED", True)):
            self.backup_task = asyncio.create_task(self._periodic_backup())
            logger.info(
                "Database backup scheduler started (every %sh, retention=%s)",
                getattr(settings, "BACKUP_INTERVAL_HOURS", 24),
                getattr(settings, "BACKUP_RETENTION", 30),
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
        if self.backup_task:
            self.backup_task.cancel()
            try:
                await self.backup_task
            except asyncio.CancelledError:
                pass
        logger.info("Scheduler stopped")

    async def _periodic_backup(self):
        """Independent loop that takes a SQLite online backup every N hours."""
        from datetime import datetime, timezone

        initial_delay = max(0, int(getattr(settings, "BACKUP_INITIAL_DELAY_SECONDS", 300) or 0))
        interval_hours = max(1, int(getattr(settings, "BACKUP_INTERVAL_HOURS", 24) or 24))
        interval_seconds = interval_hours * 3600

        try:
            await asyncio.sleep(initial_delay)
        except asyncio.CancelledError:
            return

        while self.running:
            try:
                info = await asyncio.to_thread(run_scheduled_backup)
                if info is not None:
                    self.last_backup_at = datetime.now(timezone.utc).isoformat()
                    self.last_backup_filename = info.filename
                    self.last_backup_error = None
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.last_backup_error = str(e)
                logger.error("Scheduled DB backup failed: %s", e)

            try:
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                break
    
    async def _periodic_task(self):
        """Internal periodic task runner — runs every CRAWL_INTERVAL_HOURS."""
        from datetime import datetime, timedelta, timezone

        interval_seconds = settings.CRAWL_INTERVAL_HOURS * 3600
        # Initial next-run estimate (from startup), updated after each run.
        self.next_extraction_at = (
            datetime.now(timezone.utc) + timedelta(seconds=interval_seconds)
        ).isoformat()

        while self.running:
            try:
                await asyncio.sleep(interval_seconds)
                if self.running:
                    await self.run_extraction_once()
                self.next_extraction_at = (
                    datetime.now(timezone.utc) + timedelta(seconds=interval_seconds)
                ).isoformat()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic task: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying
    
    async def run_extraction_once(self, force: bool = False):
        """Run the extended extraction pipeline once.

        Args:
            force: If True, ignore per-page crawl_frequency_hours (e.g. manual trigger).
        """
        from datetime import datetime, timezone
        self.extraction_in_progress = True
        self.extraction_started_at = datetime.now(timezone.utc).isoformat()
        logger.info("Starting extended tender extraction cycle with Agent 3...")
        
        db = SessionLocal()
        try:
            # Step 1: Get active monitored pages
            pages = self.page_repo.get_active_pages(db)
            
            if not pages:
                logger.warning("No active monitored pages found")
                return
            
            logger.info(f"Processing {len(pages)} pages (force={force})")
            _pm = (settings.PIPELINE_MODE or "simple").strip().lower()
            if _pm in ("langgraph", "legacy"):
                logger.info("Pipeline mode=%s (LangGraph + checklist Agent 1)", _pm)
            else:
                logger.info(
                    "Pipeline mode=%s (crawler artifact → ListingStructureAgent → Agent 2/3)",
                    _pm,
                )
            
            # Step 3: Process each monitored page through extended pipeline
            total_new_tenders = 0
            all_email_compositions = []
            
            for page in pages:
                page_result = await self._process_page_extended_pipeline(db, page, force=force)
                total_new_tenders += page_result['new_tenders_count']
                all_email_compositions.extend(page_result['email_compositions'])
            
            # Step 4: Send intelligent notifications using Agent 3 compositions
            await self._send_intelligent_notifications(all_email_compositions)
            
            # Step 5: Fallback notifications for any unnotified tenders (if Agent 3 failed)
            await self._send_fallback_notifications(db)

            # Step 6: Automatic catch-up for pending detail extraction so users don't
            # need to click "Retry pending details (batch)" manually every run.
            if total_new_tenders > 0:
                await self._auto_retry_pending_details_and_notify(db)
            
            logger.info(f"Extended extraction cycle completed - {total_new_tenders} new tenders processed with {len(all_email_compositions)} intelligent emails")
            
        except Exception as e:
            logger.error(f"Error in extended extraction cycle: {e}")
        finally:
            db.close()
            self.extraction_in_progress = False
            self.extraction_started_at = None
            self.last_extraction_at = datetime.now(timezone.utc).isoformat()
    
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
            if pipeline_mode in ("langgraph", "legacy"):
                agent_md, listing_for_expiry = dual_markdown_for_agent1_and_expiry(
                    page.url,
                    harvest.markdown or "",
                    harvest.listing_urls,
                    html=harvest.html,
                )
                crawl_artifact_kw = None
            else:
                agent_md = harvest.markdown or ""
                listing_for_expiry = harvest.markdown or ""
                crawl_artifact_kw = crawl_artifact

            pipeline_tty(
                f"[PIPELINE] · handoff | {len(harvest.markdown or ''):,} chars | "
                f"links={len(harvest.listing_urls)} | pipeline={pipeline_mode}"
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

    async def _auto_retry_pending_details_and_notify(self, db: Session):
        """
        Automatic catch-up pass after extraction:
        - Retry Agent 2 for pending recommended tenders
        - Send notifications for newly processed unnotified tenders
        This mirrors the manual "Retry pending details (batch)" action.
        """
        try:
            from app.services.agent2_retry import retry_pending_details_bulk

            logger.info(
                "Auto catch-up: retrying pending detail extraction (recommended only)"
            )
            result = await retry_pending_details_bulk(
                db,
                limit=50,
                only_passed_screening=True,
                # Pending rows often need permissive retry path.
                skip_date_validation=True,
                send_notifications=True,
            )
            logger.info(
                "Auto catch-up done: attempted=%s completed=%s notified_sent=%s",
                result.get("attempted", 0),
                result.get("completed", 0),
                (result.get("notification") or {}).get("sent", 0),
            )
        except Exception as exc:
            logger.error("Auto catch-up retry failed: %s", exc)
    
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