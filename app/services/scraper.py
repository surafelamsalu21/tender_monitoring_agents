"""
Web Scraping Service
Handles crawl4ai integration for web scraping
"""

import asyncio
from typing import Dict, Any, Optional
from crawl4ai import AsyncWebCrawler
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

class TenderScraper:
    """
    Web scraper for tender pages using crawl4ai.
    Provides asynchronous scraping for single or multiple pages and utility methods.
    """

    def __init__(self):
        # The underlying crawler instance (from crawl4ai)
        self.crawler = None
        # Placeholder for potential session tracking
        self.session_id = None

    async def __aenter__(self):
        """
        Asynchronous context manager entry.
        Instantiates the AsyncWebCrawler and opens its context.
        This allows use of 'async with TenderScraper() as scraper:' syntax,
        ensuring proper acquisition and cleanup of underlying crawler resources.
        """
        self.crawler = AsyncWebCrawler(verbose=False)
        await self.crawler.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Asynchronous context manager exit.
        Ensures the AsyncWebCrawler context is properly closed on exit.
        """
        if self.crawler:
            await self.crawler.__aexit__(exc_type, exc_val, exc_tb)

    async def scrape_page(self, url: str, **kwargs) -> Dict[str, Any]:
        """
        Scrape a single page and return structured data and metadata.

        Args:
            url (str): URL of the page to scrape.
            **kwargs: Additional parameters to control crawling (forwarded to crawl4ai).

        Returns:
            dict: Result including status,
                  basic content fields ('markdown', 'html', 'links', etc.),
                  and crawl meta ('metadata', 'word_count', 'char_count').
                  Returns error details on failure.
        """
        try:
            logger.info(f"Scraping page: {url}")

            # Compose crawl parameters, applying any overrides from caller.
            crawl_params = {
                'url': url,
                'word_count_threshold': 10,                # Minimum content length
                'bypass_cache': True,                      # Ignore previous fetches
                'timeout': settings.REQUEST_TIMEOUT,       # Max request duration
                **kwargs
            }

            # EU Funding & Tenders Portal is a React SPA; give it time to render.
            _eu_host = "ec.europa.eu"
            if _eu_host in url and "funding-tenders" in url:
                crawl_params.setdefault('delay_before_return_html', 5)
                crawl_params.setdefault('word_count_threshold', 5)

            # Actual crawling invocation (async)
            result = await self.crawler.arun(**crawl_params)

            if result.success:
                # On success, return structured output and meta counts.
                status_code = getattr(result, "status_code", None)
                return {
                    'status': 'success',
                    'url': url,
                    'title': result.metadata.get('title', ''),
                    'markdown': result.markdown,
                    'html': result.html,
                    'links': result.links,
                    'media': result.media,
                    'metadata': result.metadata,
                    'status_code': status_code,
                    'word_count': len(result.markdown.split()) if result.markdown else 0,
                    'char_count': len(result.markdown) if result.markdown else 0
                }
            else:
                # craw4lai error, return informative details
                logger.error(f"Failed to scrape {url}: {result.error_message}")
                return {
                    'status': 'failed',
                    'url': url,
                    'error': result.error_message,
                    'markdown': '',
                    'html': '',
                    'links': [],
                    'media': [],
                    'metadata': {},
                    'status_code': getattr(result, "status_code", None),
                }

        except Exception as e:
            # Catch-all for unexpected errors, log and propagate error structure
            logger.error(f"Error scraping {url}: {e}")
            return {
                'status': 'error',
                'url': url,
                'error': str(e),
                'markdown': '',
                'html': '',
                'links': [],
                'media': [],
                'metadata': {},
                'status_code': None,
            }

    async def scrape_multiple_pages(self, urls: list, max_concurrent: int = None) -> Dict[str, Dict[str, Any]]:
        """
        Scrape multiple pages concurrently, limiting concurrency as needed.

        Args:
            urls (list): List of string URLs to be scraped.
            max_concurrent (int, optional): Max number of concurrent requests; if None,
                                            uses settings.MAX_CONCURRENT_CRAWLS.

        Returns:
            dict: Maps each URL to its scrape results.
        """
        if max_concurrent is None:
            max_concurrent = settings.MAX_CONCURRENT_CRAWLS

        semaphore = asyncio.Semaphore(max_concurrent)

        async def scrape_with_semaphore(url: str) -> tuple:
            """
            Helper coroutine to control concurrency of scraping.
            Acquires semaphore before scraping each page.
            """
            async with semaphore:
                result = await self.scrape_page(url)
                return url, result

        # Create coroutine tasks for all URLs
        tasks = [scrape_with_semaphore(url) for url in urls]

        # Gather results concurrently, allowing for exceptions in results
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collate all results into dict, logging errors as encountered
        scraped_data = {}
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Error in concurrent scraping: {result}")
                continue

            url, data = result
            scraped_data[url] = data

        return scraped_data

    def extract_links(self, content: str, base_url: str) -> list:
        """
        Extract and normalize all links found in a page's content (markdown or HTML).

        Args:
            content (str): The HTML/markdown document as a single string.
            base_url (str): The base URL to resolve relative paths.

        Returns:
            list: Collection of normalized absolute URLs found in the content.
        """
        # This implementation is intentionally simple. For rich HTML parsing,
        # consider using BeautifulSoup or an equivalent parser.
        import re
        from urllib.parse import urljoin, urlparse

        # Extract markdown links: [text](url)
        markdown_links = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', content)
        # Extract HTML links: <a href="url">...</a>
        html_links = re.findall(r'href=["\']([^"\']+)["\']', content)

        all_links = []

        # Normalize and validate markdown links
        for text, url in markdown_links:
            normalized_url = urljoin(base_url, url)
            if self._is_valid_url(normalized_url):
                all_links.append(normalized_url)

        # Normalize and validate HTML links
        for url in html_links:
            normalized_url = urljoin(base_url, url)
            if self._is_valid_url(normalized_url):
                all_links.append(normalized_url)

        # Deduplicate the results
        return list(set(all_links))

    def _is_valid_url(self, url: str) -> bool:
        """
        Helper function to check if a URL is valid for scraping (not a mailto or fragment).

        Args:
            url (str): The URL to validate.

        Returns:
            bool: True if the URL is an http(s) link and not a fragment/mailto.
        """
        from urllib.parse import urlparse
        try:
            parsed = urlparse(url)
            return (
                parsed.scheme in ('http', 'https') and
                parsed.netloc and
                not url.startswith('#') and
                not url.startswith('mailto:')
            )
        except Exception:
            return False


################################################################################
#                                                                              #
#                              FILE & CODE COMMENTS                            #
#                                                                              #
################################################################################

# app/services/scraper.py
#
# Purpose:
#   - Defines the TenderScraper class for programmatically scraping tender (and other)
#     web pages, with a focus on:
#       - Asynchronous operations for performance.
#       - Crawl4ai integration for robust page crawling.
#       - Automatic error handling, logging, and structured outputs.
#
# Main Components:
#   * TenderScraper class:
#     - Supports async context management (ensures proper crawler resource lifecycle).
#     - scrape_page(): Scrapes a single page, returns uniform detailed dictionaries
#                     with fields like 'markdown', 'html', meta, and error info.
#     - scrape_multiple_pages(): Allows concurrent scraping of a batch of URLs,
#         with concurrency limits to avoid overloading servers or API quota issues.
#     - extract_links(): Utility for extracting all (absolute, deduplicated) URLs from
#         markdown or HTML content. Useful for discovering subpages, attached documents, etc.
#     - _is_valid_url(): Helper for filtering out non-http(s) targets and irrelevant hrefs.
#
# Usage Patterns:
#   - Used for monitoring, crawling, or re-crawling potential tender sources.
#   - Can be invoked independently (for a single scrape) or in a batch (for periodic scans).
#   - Supports customization of crawl parameters and error-safe parallel processing.
#
# Robustness:
#   - Each scraping method logs activity and errors, ensuring traceability.
#   - Failures are caught and returned as structured (not raising) errors—this prevents
#     batch jobs or APIs from dying unpredictably.
#
# Extensibility:
#   - Current link extraction is intentionally simple—well-suited for quick scans.
#     If needed, this can be upgraded with richer parsing for new document types.
#
# Integration:
#   - Relies on 'settings' for important runtime parameters (timeouts, concurrency caps).
#   - Used in downstream routes or periodic job modules for acquiring timely tender content.
#
################################################################################