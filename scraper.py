import asyncio
from crawl4ai import AsyncWebCrawler
from typing import List, Dict, Optional
from datetime import datetime
import re
from bs4 import BeautifulSoup
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TenderScraper:
    def __init__(self):
        self.crawler = None
    
    async def __aenter__(self):
        self.crawler = AsyncWebCrawler()
        await self.crawler.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.crawler:
            await self.crawler.__aexit__(exc_type, exc_val, exc_tb)
    
    async def scrape_page(self, url: str) -> Optional[Dict]:
        """Scrape a single page and return the content"""
        try:
            logger.info(f"Scraping page: {url}")
            result = await self.crawler.arun(url=url)
            
            if result.success:
                return {
                    'url': url,
                    'markdown': result.markdown,
                    'html': result.html,
                    'status': 'success',
                    'scraped_at': datetime.utcnow()
                }
            else:
                logger.error(f"Failed to scrape {url}: {result.error_message}")
                return {
                    'url': url,
                    'status': 'failed',
                    'error': result.error_message,
                    'scraped_at': datetime.utcnow()
                }
        except Exception as e:
            logger.error(f"Exception while scraping {url}: {str(e)}")
            return {
                'url': url,
                'status': 'failed',
                'error': str(e),
                'scraped_at': datetime.utcnow()
            }
    
    def extract_tender_links(self, content: str, base_url: str) -> List[Dict]:
        """Extract potential tender links from page content"""
        tender_patterns = [
            r'tender',
            r'тендер',
            r'конкурс',
            r'закупка',
            r'procurement',
            r'bid',
            r'rfp',
            r'request for proposal'
        ]
        
        # Parse HTML content
        soup = BeautifulSoup(content, 'html.parser')
        links = []
        
        # Find all links
        for link in soup.find_all('a', href=True):
            href = link.get('href')
            text = link.get_text(strip=True).lower()
            
            # Check if link text contains tender-related keywords
            if any(pattern in text for pattern in tender_patterns):
                # Convert relative URLs to absolute
                if href.startswith('/'):
                    full_url = base_url.rstrip('/') + href
                elif not href.startswith('http'):
                    full_url = base_url.rstrip('/') + '/' + href
                else:
                    full_url = href
                
                # Try to extract date from text or nearby elements
                date_match = self.extract_date_from_text(text)
                
                links.append({
                    'title': link.get_text(strip=True),
                    'url': full_url,
                    'extracted_date': date_match,
                    'context': text
                })
        
        return links
    
    def extract_date_from_text(self, text: str) -> Optional[datetime]:
        """Extract date from text using various patterns"""
        date_patterns = [
            r'(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})',
            r'(\d{1,2})\.(\d{1,2})\.(\d{4})',
            r'(\d{4})-(\d{1,2})-(\d{1,2})',
            r'(\d{1,2})/(\d{1,2})/(\d{4})'
        ]
        
        months_ru = {
            'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4,
            'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8,
            'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
        }
        
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    if 'января' in pattern:  # Russian month names
                        day, month_name, year = match.groups()
                        month = months_ru.get(month_name.lower())
                        if month:
                            return datetime(int(year), month, int(day))
                    else:  # Numeric dates
                        groups = match.groups()
                        if len(groups) == 3:
                            if '.' in pattern or '/' in pattern:
                                day, month, year = groups
                                return datetime(int(year), int(month), int(day))
                            else:  # YYYY-MM-DD format
                                year, month, day = groups
                                return datetime(int(year), int(month), int(day))
                except (ValueError, TypeError):
                    continue
        
        return None

async def test_scraper():
    """Test the scraper with the example URL"""
    async with TenderScraper() as scraper:
        result = await scraper.scrape_page("https://corp.uzairways.com/ru/press-center/tenders")
        if result['status'] == 'success':
            print("✓ Scraping successful")
            tender_links = scraper.extract_tender_links(result['html'], "https://corp.uzairways.com")
            print(f"Found {len(tender_links)} potential tender links")
            for link in tender_links[:5]:  # Show first 5
                print(f"- {link['title'][:50]}... -> {link['url']}")
        else:
            print(f"✗ Scraping failed: {result['error']}")

if __name__ == "__main__":
    asyncio.run(test_scraper())
