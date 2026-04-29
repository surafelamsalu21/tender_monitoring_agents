#!/usr/bin/env python3
"""
Tender Agent V3 - Main Entry Point
A comprehensive tender monitoring system with AI-powered extraction and categorization.
"""

import asyncio
import sys
import argparse
from pathlib import Path

# Add current directory to path for imports
sys.path.append(str(Path(__file__).parent))

from scheduler import TenderScheduler
from database import DatabaseManager
from email_service import EmailService
from scraper import TenderScraper
from agents import TenderAgent
from config import Config
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def print_banner():
    """Print application banner"""
    banner = """
    ╔══════════════════════════════════════════════════════════════╗
    ║                     TENDER AGENT V3                          ║
    ║              AI-Powered Tender Monitoring System             ║
    ║                                                              ║
    ║  Features:                                                   ║
    ║  • Automated web scraping with crawl4ai                     ║
    ║  • AI-powered tender extraction & categorization             ║
    ║  • ESG and Credit Rating team notifications                 ║
    ║  • Scheduled monitoring every 3 hours                       ║
    ║  • SQLite database for tender tracking                      ║
    ╚══════════════════════════════════════════════════════════════╝
    """
    print(banner)

async def test_components():
    """Test all system components"""
    print("\n🔧 Testing System Components...")
    
    # Test database
    print("\n📊 Testing Database...")
    try:
        db_manager = DatabaseManager()
        db_manager.initialize_default_data()
        print("✓ Database initialization successful")
    except Exception as e:
        print(f"✗ Database test failed: {e}")
        return False
    
    # Test scraper
    print("\n🕷️ Testing Web Scraper...")
    try:
        async with TenderScraper() as scraper:
            result = await scraper.scrape_page("https://corp.uzairways.com/ru/press-center/tenders")
            if result['status'] == 'success':
                print("✓ Web scraping successful")
                tender_links = scraper.extract_tender_links(result['html'], "https://corp.uzairways.com")
                print(f"✓ Found {len(tender_links)} potential tender links")
            else:
                print(f"✗ Web scraping failed: {result['error']}")
                return False
    except Exception as e:
        print(f"✗ Scraper test failed: {e}")
        return False
    
    # Test agents
    print("\n🤖 Testing AI Agents...")
    try:
        if not Config.OPENAI_API_KEY:
            print("⚠️ No OpenAI API key found - skipping agent test")
        else:
            agent = TenderAgent()
            print("✓ AI agents initialized successfully")
    except Exception as e:
        print(f"✗ Agent test failed: {e}")
        return False
    
    # Test email service
    print("\n📧 Testing Email Service...")
    try:
        email_service = EmailService()
        if Config.EMAIL_USER and Config.EMAIL_PASSWORD:
            print("✓ Email service configured")
        else:
            print("⚠️ Email credentials not configured - notifications will be disabled")
    except Exception as e:
        print(f"✗ Email service test failed: {e}")
        return False
    
    print("\n✅ All component tests completed!")
    return True

async def run_single_extraction():
    """Run a single tender extraction cycle"""
    print("\n🚀 Running Single Tender Extraction...")
    
    scheduler = TenderScheduler()
    scheduler.db_manager.initialize_default_data()
    
    try:
        await scheduler.run_once()
        print("✅ Single extraction completed successfully!")
    except Exception as e:
        print(f"❌ Extraction failed: {e}")
        logger.error(f"Single extraction error: {e}")

def start_scheduler():
    """Start the continuous scheduler"""
    print(f"\n⏰ Starting Continuous Scheduler (every {Config.CRAWL_INTERVAL_HOURS} hours)...")
    print("Press Ctrl+C to stop the scheduler")
    
    scheduler = TenderScheduler()
    scheduler.db_manager.initialize_default_data()
    
    try:
        scheduler.start_scheduler()
    except KeyboardInterrupt:
        print("\n🛑 Scheduler stopped by user")
    except Exception as e:
        print(f"❌ Scheduler error: {e}")
        logger.error(f"Scheduler error: {e}")

def show_config():
    """Show current configuration"""
    print("\n⚙️ Current Configuration:")
    print(f"Database URL: {Config.DATABASE_URL}")
    print(f"Crawl Interval: {Config.CRAWL_INTERVAL_HOURS} hours")
    print(f"OpenAI API Key: {'✓ Configured' if Config.OPENAI_API_KEY else '✗ Missing'}")
    print(f"Email User: {Config.EMAIL_USER or '✗ Not configured'}")
    print(f"ESG Team Email: {Config.ESG_TEAM_EMAIL or '✗ Not configured'}")
    print(f"Credit Rating Team Email: {Config.CREDIT_RATING_TEAM_EMAIL or '✗ Not configured'}")
    print(f"ESG Keywords: {len(Config.ESG_KEYWORDS)} configured")
    print(f"Credit Rating Keywords: {len(Config.CREDIT_RATING_KEYWORDS)} configured")

def main():
    """Main entry point with command line interface"""
    print_banner()
    
    parser = argparse.ArgumentParser(description="Tender Agent V3 - AI-Powered Tender Monitoring")
    parser.add_argument('command', nargs='?', choices=['test', 'run', 'schedule', 'config'], 
                       default='schedule', help='Command to execute')
    
    args = parser.parse_args()
    
    if args.command == 'test':
        asyncio.run(test_components())
    elif args.command == 'run':
        asyncio.run(run_single_extraction())
    elif args.command == 'schedule':
        start_scheduler()
    elif args.command == 'config':
        show_config()
    else:
        print("Invalid command. Use: test, run, schedule, or config")

if __name__ == "__main__":
    main()
