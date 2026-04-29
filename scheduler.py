import asyncio
import schedule
import time
from datetime import datetime
from typing import List
from sqlalchemy.orm import Session
from models import get_db
from database import DatabaseManager
from scraper import TenderScraper
from agents import TenderAgent
from email_service import EmailService
from config import Config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TenderScheduler:
    def __init__(self):
        self.db_manager = DatabaseManager()
        self.email_service = EmailService()
        self.agent = TenderAgent()
        self.workflow = self.agent.create_workflow()
    
    async def run_tender_extraction(self):
        """Main tender extraction process"""
        logger.info("Starting scheduled tender extraction...")
        
        with next(get_db()) as db:
            # Get all active monitored pages
            pages = self.db_manager.get_active_pages(db)
            logger.info(f"Processing {len(pages)} monitored pages")
            
            for page in pages:
                try:
                    await self.process_page(db, page)
                except Exception as e:
                    logger.error(f"Error processing page {page.url}: {e}")
                    self.db_manager.log_crawl(db, page.id, "failed", 0, str(e))
            
            # Send notifications for new tenders
            await self.send_notifications(db)
        
        logger.info("Scheduled tender extraction completed")
    
    async def process_page(self, db: Session, page):
        """Process a single monitored page"""
        logger.info(f"Processing page: {page.name} ({page.url})")
        
        try:
            # Scrape the page
            async with TenderScraper() as scraper:
                result = await scraper.scrape_page(page.url)
                
                if result['status'] != 'success':
                    self.db_manager.log_crawl(db, page.id, "failed", 0, result.get('error'))
                    return
                
                # Get keywords for processing
                esg_keywords = self.db_manager.get_keywords_by_category(db, "esg")
                credit_keywords = self.db_manager.get_keywords_by_category(db, "credit_rating")
                
                # Run agent workflow
                initial_state = {
                    'page_url': page.url,
                    'page_content': result['markdown'],
                    'raw_tenders': [],
                    'categorized_tenders': [],
                    'detailed_tenders': [],
                    'keywords_esg': esg_keywords,
                    'keywords_credit': credit_keywords,
                    'error': None
                }
                
                workflow_result = await self.workflow.ainvoke(initial_state)
                
                if workflow_result.get('error'):
                    logger.error(f"Agent workflow error: {workflow_result['error']}")
                    self.db_manager.log_crawl(db, page.id, "failed", 0, workflow_result['error'])
                    return
                
                # Save tenders to database
                saved_tenders = []
                for tender_data in workflow_result.get('categorized_tenders', []):
                    # Agent 1 has filtered tenders - save basic tender info
                    tender = self.db_manager.save_tender(
                        db, 
                        page.id, 
                        tender_data['title'], 
                        tender_data['url'], 
                        tender_data.get('date'), 
                        tender_data['category'], 
                        tender_data['description']
                    )
                    if tender:
                        saved_tenders.append(tender)
                        logger.info(f"Saved basic tender: {tender.title}")
                
                # Save detailed tender information from Agent 2
                detailed_count = 0
                for detailed_tender_data in workflow_result.get('detailed_tenders', []):
                    # Find the corresponding basic tender
                    basic_tender = None
                    for saved_tender in saved_tenders:
                        if (saved_tender.title == detailed_tender_data['title'] and 
                            saved_tender.url == detailed_tender_data['url']):
                            basic_tender = saved_tender
                            break
                    
                    if basic_tender and 'detailed_info' in detailed_tender_data:
                        # Save detailed information
                        detailed_info = detailed_tender_data['detailed_info']
                        detailed_info['full_content'] = detailed_tender_data.get('full_content', '')
                        
                        detailed_tender = self.db_manager.save_detailed_tender(
                            db, 
                            basic_tender.id, 
                            detailed_info
                        )
                        if detailed_tender:
                            detailed_count += 1
                            logger.info(f"Saved detailed tender info for: {basic_tender.title[:50]}...")
                
                logger.info(f"Successfully processed {len(saved_tenders)} basic tenders and {detailed_count} detailed tenders from {page.name}")
                
                # Log crawl activity
                self.db_manager.log_crawl(db, page.id, 'success', len(saved_tenders))
                
                # Update page last crawled time
                page.last_crawled = datetime.utcnow()
                db.commit()
                
        except Exception as e:
            logger.error(f"Error processing page {page.url}: {e}")
            self.db_manager.log_crawl(db, page.id, "failed", 0, str(e))
    
    async def send_notifications(self, db: Session):
        """Send email notifications for new tenders"""
        logger.info("Checking for tenders to notify...")
        
        # Get unnotified ESG tenders
        esg_tenders = self.db_manager.get_unnotified_tenders(db, "esg")
        if esg_tenders:
            success = self.email_service.send_tender_notifications(esg_tenders, "esg")
            if success:
                for tender in esg_tenders:
                    self.db_manager.mark_tender_notified(db, tender.id)
                logger.info(f"Notified ESG team about {len(esg_tenders)} tenders")
        
        # Get unnotified Credit Rating tenders
        credit_tenders = self.db_manager.get_unnotified_tenders(db, "credit_rating")
        if credit_tenders:
            success = self.email_service.send_tender_notifications(credit_tenders, "credit_rating")
            if success:
                for tender in credit_tenders:
                    self.db_manager.mark_tender_notified(db, tender.id)
                logger.info(f"Notified Credit Rating team about {len(credit_tenders)} tenders")
    
    def start_scheduler(self):
        """Start the scheduler"""
        logger.info(f"Starting tender scheduler - will run every {Config.CRAWL_INTERVAL_MINUTES} minutes")
        
        # Schedule the job
        schedule.every(Config.CRAWL_INTERVAL_MINUTES).minutes.do(
            lambda: asyncio.run(self.run_tender_extraction())
        )
        
        # Run once immediately
        asyncio.run(self.run_tender_extraction())
        
        # Keep the scheduler running
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    
    async def run_once(self):
        """Run the extraction process once (for testing)"""
        await self.run_tender_extraction()

def main():
    """Main entry point"""
    scheduler = TenderScheduler()
    
    # Initialize database with default data
    scheduler.db_manager.initialize_default_data()
    
    try:
        scheduler.start_scheduler()
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user")
    except Exception as e:
        logger.error(f"Scheduler error: {e}")

async def test_run():
    """Test run for development"""
    scheduler = TenderScheduler()
    scheduler.db_manager.initialize_default_data()
    await scheduler.run_once()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        asyncio.run(test_run())
    else:
        main()
