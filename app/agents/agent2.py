"""
Enhanced Agent 2: Detail Extraction with Date Validation
Validates tender dates and filters out expired tenders
"""
import logging
import re
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urljoin, urlparse
import asyncio
from langchain_core.messages import HumanMessage

from app.core.llm_factory import get_chat_llm
from app.services.scraper import TenderScraper
from app.agents.page_sanity import (
    http_status_is_hard_failure,
    markdown_indicates_error_or_empty_notice,
)

logger = logging.getLogger(__name__)

class TenderDetailAgent:
    """
    Enhanced Agent 2: Extract detailed information with date validation
    
    Features:
    - Extract detailed information from individual tender pages
    - Validate publication and deadline dates
    - Skip processing of expired tenders
    - Mark urgent tenders for priority processing
    """
    
    def __init__(self):
        self.llm = get_chat_llm(temperature=0.1)  # Initialize Language Model for information extraction
        
        # Date validation configuration
        self.max_days_old = 90  # Maximum allowable age (in days) for tenders to be processed
        self.urgent_days_threshold = 7  # Mark as urgent if deadline within this number of days
    
    async def extract_tender_details(self, tender_url: str, 
                                   basic_tender: Dict[str, Any],
                                   skip_date_validation: bool = False) -> Optional[Dict[str, Any]]:
        """
        Extract detailed information from an individual tender page with date validation.
        
        Args:
            tender_url: URL of the specific tender page to process.
            basic_tender: Basic tender data already extracted (from Agent 1).
            skip_date_validation: If True, bypasses date rules (for "All Tenders" mode).
            
        Returns:
            Structured detailed tender information, or None if tender is expired/invalid.
        """
        try:
            logger.info(f"Agent 2: Processing tender details for {tender_url}")
            
            # Preliminary validation: Should this tender be processed?
            if not skip_date_validation:
                should_process = self._should_process_tender(basic_tender)
                if not should_process:
                    logger.info(f"Agent 2: Skipping expired/old tender: {basic_tender.get('title', 'Unknown')[:50]}...")
                    return self._create_skipped_details(basic_tender, "Tender expired or too old")
            
            # Step 1: Scrape the content of the individual tender page
            page_content, page_http_status = await self._scrape_tender_page(tender_url)
            
            if not page_content:
                msg = "Failed to scrape page"
                if page_http_status is not None:
                    msg = f"Failed to scrape page (HTTP {page_http_status})"
                logger.error("Agent 2: %s: %s", msg, tender_url)
                return self._create_fallback_details(basic_tender, msg)

            sanity = markdown_indicates_error_or_empty_notice(
                page_content, http_status=page_http_status
            )
            if sanity:
                logger.info(
                    "Agent 2: refusing detail extraction (%s): %s",
                    sanity,
                    tender_url[:80],
                )
                return self._create_fallback_details(
                    basic_tender, f"Not a valid notice page: {sanity}"
                )
            
            # Step 2: Extract detailed tender information using the LLM, with focus on date fields
            detailed_info = await self._extract_detailed_info_with_dates(
                page_content, basic_tender, page_http_status=page_http_status
            )
            
            if not detailed_info:
                logger.error(f"Agent 2: Failed to extract details from: {tender_url}")
                return self._create_fallback_details(basic_tender, "Failed to extract details")

            if detailed_info.get("extraction_status") == "failed":
                return self._create_fallback_details(
                    basic_tender,
                    str(
                        detailed_info.get("error_message")
                        or "Model reported extraction failure"
                    ),
                )

            if self._detail_missing_substance(detailed_info):
                logger.info(
                    "Agent 2: no substantive fields after extraction; refusing invented notice: %s",
                    tender_url[:80],
                )
                return self._create_fallback_details(
                    basic_tender,
                    "No substantive procurement fields extracted (model output empty or unusable)",
                )
            
            # Step 3: Final step, validate extracted dates from the detailed info
            if not skip_date_validation:
                date_validation_result = self._validate_extracted_dates(detailed_info, basic_tender)
                detailed_info.update(date_validation_result)
                
                if date_validation_result.get('skip_processing'):
                    logger.info(f"Agent 2: Skipping after date validation: {basic_tender.get('title', 'Unknown')[:50]}...")
                    return self._create_skipped_details(basic_tender, "Failed date validation")
            
            logger.info(f"Agent 2: Completed for: {basic_tender.get('title', 'Unknown')[:50]}...")
            return detailed_info
            
        except Exception as e:
            logger.error(f"Agent 2: Error for {tender_url}: {e}")
            return self._create_fallback_details(basic_tender, str(e))
    
    def _should_process_tender(self, basic_tender: Dict[str, Any]) -> bool:
        """
        Checks preliminary criteria to determine whether this tender warrants detailed processing.
        Will skip tenders that are expired or too old.
        """
        try:
            current_date = datetime.now().date()
            
            # Check date_status from Agent 1
            date_status = basic_tender.get('date_status', 'unknown')
            if date_status == 'expired':
                return False
            
            # Check publication date validity
            publication_date = self._parse_date(basic_tender.get('publication_date'))
            if publication_date:
                days_old = (current_date - publication_date).days
                if days_old > self.max_days_old:
                    logger.info(f"Tender too old: {days_old} days")
                    return False
            
            # Check if deadline (or date) is in the past
            deadline = self._parse_date(basic_tender.get('deadline') or basic_tender.get('date'))
            if deadline and deadline < current_date:
                logger.info(f"Tender deadline passed: {deadline}")
                return False
            
            return True
            
        except Exception as e:
            logger.warning(f"Error in pre-validation: {e}")
            return True  # If there's an error, err on the side of processing
    
    async def _scrape_tender_page(
        self, tender_url: str
    ) -> tuple[Optional[str], Optional[int]]:
        """
        Scrapes the tender page using the TenderScraper service.
        Returns (markdown_or_none, http_status_or_none).
        """
        tender_url = await self._repair_undp_detail_url(tender_url) or tender_url
        try:
            logger.info(f"Scraping tender page: {tender_url}")
            
            async with TenderScraper() as scraper:
                result = await scraper.scrape_page(tender_url)
                code = result.get("status_code")
                
                if result['status'] == 'success':
                    if http_status_is_hard_failure(code):
                        logger.error(
                            "Scrape reported success but HTTP %s for %s",
                            code,
                            tender_url,
                        )
                        return None, code
                    content = result.get("markdown") or ""
                    if self._is_pdf_url(tender_url) and self._looks_minimal_or_blocked(content):
                        pdf_text = await self._scrape_pdf_direct(tender_url)
                        if pdf_text:
                            return pdf_text, code
                    logger.info(
                        "Successfully scraped %s characters from %s",
                        len(content),
                        tender_url,
                    )
                    return content, code
                else:
                    error = result.get('error', 'Unknown error')
                    logger.error(f"Scraping failed for {tender_url}: {error}")
                    if self._is_pdf_url(tender_url):
                        pdf_text = await self._scrape_pdf_direct(tender_url)
                        if pdf_text:
                            return pdf_text, code
                    if self._should_use_playwright_detail_fallback(tender_url, error):
                        text = await self._scrape_detail_with_playwright(tender_url)
                        return text, None
                    return None, code
                    
        except Exception as e:
            logger.error(f"Exception while scraping {tender_url}: {e}")
            if self._is_undp_url(tender_url):
                text = await self._scrape_detail_with_playwright(tender_url)
                return text, None
            return None, None

    def _is_undp_url(self, url: str) -> bool:
        return urlparse(str(url or "")).netloc.lower() == "procurement-notices.undp.org"

    @staticmethod
    def _is_pdf_url(url: str) -> bool:
        return str(url or "").lower().split("?")[0].endswith(".pdf")

    @staticmethod
    def _looks_minimal_or_blocked(content: str) -> bool:
        txt = (content or "").strip().lower()
        if len(txt) < 250:
            return True
        return (
            "blocked by anti-bot" in txt
            or "no_content_elements" in txt
            or "minimal_text" in txt
        )

    async def _scrape_pdf_direct(self, url: str) -> Optional[str]:
        """Direct PDF extraction fallback for URLs that are PDF files."""
        def _read_pdf() -> Optional[str]:
            import io
            import requests
            try:
                from pypdf import PdfReader  # type: ignore[reportMissingImports]
            except Exception as exc:
                logger.error(
                    "Agent 2: pypdf is required for direct PDF fallback but is unavailable: %s",
                    exc,
                )
                return None

            resp = requests.get(
                url,
                timeout=30,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if resp.status_code >= 400:
                return None
            ctype = str(resp.headers.get("content-type", "")).lower()
            if "pdf" not in ctype and not self._is_pdf_url(url):
                return None
            reader = PdfReader(io.BytesIO(resp.content))
            chunks: List[str] = []
            for page in reader.pages[:80]:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    chunks.append(page_text.strip())
            text = "\n\n".join(chunks).strip()
            return text or None

        try:
            text = await asyncio.to_thread(_read_pdf)
            if text and len(text) > 120:
                logger.info(
                    "Agent 2: direct PDF fallback extracted %s chars from %s",
                    len(text),
                    url,
                )
                return text
            return None
        except Exception as exc:
            logger.warning("Agent 2: direct PDF fallback failed for %s: %s", url, exc)
            return None

    def _should_use_playwright_detail_fallback(self, url: str, error: str) -> bool:
        if not self._is_undp_url(url):
            return False
        low = str(error or "").lower()
        return (
            "anti-bot" in low
            or "minimal_text" in low
            or "no_content_elements" in low
            or "issue" in low
        )

    async def _repair_undp_detail_url(self, tender_url: str) -> Optional[str]:
        """
        Older Agent1 outputs sometimes used `view_notice.cfm?notice_id=UNDP-...`.
        Current UNDP Quantum notices need `view_negotiation.cfm?nego_id=...`; resolve it
        from the public listing page before Agent2 scrapes details.
        """
        parsed = urlparse(str(tender_url or ""))
        if parsed.netloc.lower() != "procurement-notices.undp.org":
            return None
        if not parsed.path.endswith("view_notice.cfm"):
            return None

        ref = (parse_qs(parsed.query).get("notice_id") or [""])[0].strip()
        if not ref.upper().startswith("UNDP-"):
            return None

        try:
            import requests
            from bs4 import BeautifulSoup

            def _lookup() -> Optional[str]:
                html = requests.get(
                    "https://procurement-notices.undp.org/",
                    timeout=20,
                    headers={"User-Agent": "Mozilla/5.0"},
                ).text
                soup = BeautifulSoup(html, "html.parser")
                for anchor in soup.find_all("a", href=True):
                    text = anchor.get_text(" ", strip=True)
                    if ref in text:
                        return urljoin(
                            "https://procurement-notices.undp.org/",
                            anchor["href"],
                        )
                return None

            import asyncio

            repaired = await asyncio.to_thread(_lookup)
            if repaired:
                logger.info("Repaired UNDP detail URL %s -> %s", tender_url, repaired)
            return repaired
        except Exception as exc:
            logger.warning("Could not repair UNDP detail URL %s: %s", tender_url, exc)
            return None

    async def _scrape_detail_with_playwright(self, tender_url: str) -> Optional[str]:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            logger.error("Playwright detail fallback unavailable: %s", exc)
            return None

        logger.info("Agent 2: Playwright detail fallback for %s", tender_url)
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    page = await browser.new_page()
                    page.set_default_timeout(60_000)
                    await page.goto(tender_url, wait_until="load")
                    await page.wait_for_timeout(750)
                    text = (await page.locator("body").inner_text()).strip()
                    links = await page.evaluate(
                        """() => Array.from(document.querySelectorAll('a[href]'))
                            .map((a) => {
                                const text = (a.innerText || a.textContent || '').replace(/\\s+/g, ' ').trim();
                                return { text, href: a.href };
                            })
                            .filter((item) => item.text && item.href)"""
                    )
                finally:
                    await browser.close()

            link_lines = []
            for link in links:
                label = str(link.get("text") or "").strip()
                href = str(link.get("href") or "").strip()
                if label and href.startswith("http"):
                    link_lines.append(f"- {label}: {href}")
            if link_lines:
                text = f"{text}\n\nLinks:\n" + "\n".join(link_lines[:80])
            if len(text) < 100:
                logger.error("Playwright fallback returned minimal text for %s", tender_url)
                return None
            logger.info(
                "Agent 2: Playwright fallback scraped %s characters from %s",
                len(text),
                tender_url,
            )
            return text
        except Exception as exc:
            logger.error("Playwright detail fallback failed for %s: %s", tender_url, exc)
            return None
    
    @staticmethod
    def _nonempty_str(val: Any) -> str:
        if val is None:
            return ""
        s = str(val).strip()
        if s.lower() in ("null", "none", "n/a", "na"):
            return ""
        return s

    def _detail_missing_substance(self, detailed_info: Dict[str, Any]) -> bool:
        """
        True when the model returned no usable notice fields — treat as failure
        so we never persist a fake 'completed' extraction.
        """
        if detailed_info.get("extraction_status") in ("failed", "skipped"):
            return False
        d = detailed_info
        if self._nonempty_str(d.get("detailed_title")):
            return False
        if len(self._nonempty_str(d.get("detailed_description"))) > 30:
            return False
        if len(self._nonempty_str(d.get("requirements"))) > 30:
            return False
        if len(self._nonempty_str(d.get("additional_details"))) > 30:
            return False
        if d.get("deadline") or d.get("submission_deadline"):
            return False
        if self._nonempty_str(d.get("tender_value")):
            return False
        if self._nonempty_str(d.get("duration")):
            return False
        ci = d.get("contact_info")
        if isinstance(ci, dict):
            for k in ("organization", "email", "phone", "contact_person", "address"):
                if self._nonempty_str(ci.get(k)):
                    return False
        return True

    async def _extract_detailed_info_with_dates(
        self,
        page_content: str,
        basic_tender: Dict[str, Any],
        page_http_status: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Uses the LLM to extract detailed and date-focused information from the given tender page content.
        The prompt given to the LLM emphasizes date normalization and urgency.
        """
        try:
            system_prompt = self._build_enhanced_detail_extraction_prompt()
            
            user_message = f"""
BASIC TENDER INFORMATION (from Agent 1):
=======================================
Title: {basic_tender.get('title', 'N/A')}
URL: {basic_tender.get('url', 'N/A')}
Screening Category: {basic_tender.get('category', 'screening_opportunities')}
Step 1 Yes Count: {basic_tender.get('screening', {}).get('yes_count', 'N/A')}
Passes Step 1 Filter: {basic_tender.get('screening', {}).get('passes_filter', 'N/A')}
Source: {basic_tender.get('screening', {}).get('step3', {}).get('source', 'N/A')}
Opportunity Type: {basic_tender.get('screening', {}).get('step3', {}).get('type', 'N/A')}
Publication Date: {basic_tender.get('publication_date', 'N/A')}
Deadline: {basic_tender.get('deadline', 'N/A')}
Date Status: {basic_tender.get('date_status', 'unknown')}

FULL TENDER PAGE CONTENT:
========================
{page_content}
========================

Current Date: {datetime.now().strftime('%Y-%m-%d')}

Please extract detailed information with special attention to dates.
Return ONLY the JSON object with no additional text.
"""
            
            messages = [
                HumanMessage(content=f"{system_prompt}\n\n{user_message}")
            ]
            
            response = await self.llm.ainvoke(messages)
            response_text = response.content.strip()
            
            # Parse JSON response
            detailed_info = self._parse_detail_response(response_text)

            if detailed_info:
                if detailed_info.get("extraction_status") == "failed":
                    return {
                        "extraction_status": "failed",
                        "error_message": detailed_info.get("error_message")
                        or "Model reported extraction failure",
                    }

                from app.agents.portal_detail_hints import enrich_detail_from_page_markdown

                detailed_info = enrich_detail_from_page_markdown(
                    page_content, detailed_info, basic_tender
                )
                # Attach metadata for traceability & analytics
                detailed_info["extracted_at"] = datetime.utcnow().isoformat()
                detailed_info["page_content_length"] = len(page_content)
                detailed_info["source_url"] = basic_tender.get("url")
                if not detailed_info.get("full_content"):
                    detailed_info["full_content"] = page_content[:400_000]

                bad = markdown_indicates_error_or_empty_notice(
                    page_content, http_status=page_http_status
                )
                if bad:
                    return {
                        "extraction_status": "failed",
                        "error_message": f"Content sanity check failed after LLM: {bad}",
                    }

                if self._detail_missing_substance(detailed_info):
                    return {
                        "extraction_status": "failed",
                        "error_message": "No substantive fields in model output",
                    }

                return detailed_info
            else:
                from app.agents.portal_detail_hints import enrich_detail_from_page_markdown

                heur = enrich_detail_from_page_markdown(page_content, {}, basic_tender)
                if heur.get("detailed_title") or heur.get("deadline") or heur.get(
                    "submission_deadline"
                ):
                    heur["extracted_at"] = datetime.utcnow().isoformat()
                    heur["page_content_length"] = len(page_content)
                    heur["source_url"] = basic_tender.get("url")
                    heur["full_content"] = page_content[:400_000]
                    heur["extraction_status"] = "heuristic"
                    if self._detail_missing_substance(heur):
                        return None
                    return heur
                return None
                
        except Exception as e:
            logger.error(f"Error extracting detailed info: {e}")
            return None
    
    def _build_enhanced_detail_extraction_prompt(self) -> str:
        """
        Builds a detailed system prompt instructing the LLM on how to extract the relevant tender fields,
        with special requirements about extracting and validating all dates, translating to English, and structuring the response as required JSON.
        Provides clear requirements and date handling logic.
        """
        return f"""You are Agent 2, a careful procurement detail extraction specialist.
This is Phase 2 after a listing page identified a possible tender. Your job is to read the FULL TENDER PAGE CONTENT and extract only information that is explicitly supported by that content.

ANTI-HALLUCINATION (STRICT):
- If the page is an HTTP error, soft-404, "page not found", access denied, maintenance message, login wall with no public notice text, or otherwise contains NO real procurement notice, you MUST NOT invent a tender.
- Do NOT fill fields from guesses, general knowledge, or from the "BASIC TENDER INFORMATION" block alone when the page body does not support those facts.
- Do NOT fabricate deadlines, budgets, contacts, organizations, or scope. When in doubt, use null.
- If there is no extractable procurement notice, set "extraction_status" to "failed", set "error_message" to a short reason (e.g. "error page", "no notice content"), and set all other substantive fields to null.

Return ONLY one valid JSON object. No markdown fences. No comments. No text before or after JSON.
Use real JSON null for missing values. Never output placeholder strings such as "null", "N/A", "unknown", "not specified", "Issuing organization", or "Budget/estimated value".

CURRENT DATE: {datetime.now().strftime('%Y-%m-%d')}

OUTPUT SCHEMA:
{{
  "detailed_title": "complete procurement title in English, or null",
  "detailed_description": "2-5 sentence English summary of scope, buyer, location, and objective, or null",
  "requirements": "eligibility, qualifications, technical requirements, submission instructions, and required experience, or null",

  "publication_date": "YYYY-MM-DD or null",
  "submission_deadline": "YYYY-MM-DD or null",
  "deadline": "YYYY-MM-DD or null",
  "project_start_date": "YYYY-MM-DD or null",
  "project_end_date": "YYYY-MM-DD or null",

  "date_validation": {{
    "deadline_status": "active|expired|urgent|unknown",
    "days_until_deadline": number or null,
    "urgency_level": "low|medium|high|urgent|expired",
    "all_extracted_dates": ["YYYY-MM-DD"]
  }},

  "tender_value": "amount/range with currency exactly as found, or null",
  "duration": "contract/project duration or implementation timeline exactly as found, or null",
  "contact_info": {{
    "organization": "buyer/procuring entity/issuer, or null",
    "contact_person": "named contact person, or null",
    "phone": "phone number, or null",
    "email": "email address, or null",
    "address": "physical/postal address, or null"
  }},
  "documents_required": "bid documents, forms, certificates, proposal contents, or null",
  "evaluation_criteria": "selection/evaluation method and criteria, or null",
  "additional_details": "important fees, site visits, clarification dates, submission portal/instructions, lots, contract number, or null",
  "tender_type": "RFQ|RFP|EOI|TOR|bid notice|consultancy|goods|works|services|grant|other, or null",
  "procurement_method": "open tender, restricted, quotation, QCBS, CQS, direct procurement, etc., or null",
  "categories": "comma-separated sectors/categories, or null",

  "extraction_status": "ok or failed — use failed when the page is not a real notice or has no extractable content",
  "error_message": "non-null only when extraction_status is failed; short factual reason"
}}

DEADLINE RULES:
- The primary "deadline" must be the final submission/closing/due date for bids, quotations, proposals, EOIs, or applications.
- Look for labels such as: deadline, closing date, submission deadline, bid closing, due date, response deadline, proposal submission, application deadline, tender closing, offer validity, bid opening date.
- If both a submission deadline and bid opening date exist, use the submission/closing deadline as "deadline"; keep opening-related information in "additional_details".
- Do not use publication date, issue date, added date, page date, copyright date, or project start date as the deadline.
- Normalize dates to YYYY-MM-DD. Handle formats like 22 May 2026, May 22, 2026, 22/05/2026, 22-05-2026, 2026-05-22, 28 Apr 2026 at 15:45.
- Preserve all normalized dates you find in date_validation.all_extracted_dates.
- deadline_status: expired if deadline is before CURRENT DATE; urgent if 0-7 days away; active if more than 7 days away; unknown when no deadline is found.
- urgency_level: urgent for 0-7 days, high for 8-30 days, medium for 31-90 days, low for more than 90 days, expired for past deadlines.

BUDGET / VALUE RULES:
- Extract monetary values from labels like budget, estimated value, contract value, bid amount, amount, price, fee, ceiling, financing, grant amount, consultancy fee.
- Include currency and units exactly as shown, e.g. "UGX 120,000,000", "USD 50,000-75,000", "EUR 1.2 million".
- If the tender says there is no stated budget, return null. Do not infer budget from unrelated financing amounts.
- If multiple lots have separate values, summarize as "Lot 1: ...; Lot 2: ...".

CONTACT / ORGANIZATION RULES:
- organization should be the procuring entity, client, buyer, issuer, ministry, agency, bank, NGO, or company issuing the opportunity.
- Do not put a bidder/supplier name as organization unless the page is explicitly an award/bid opening result rather than an open opportunity.
- Extract emails and phone numbers exactly when present.

QUALITY RULES:
- Translate non-English content to clear professional English.
- Prefer specific evidence from the tender body over generic listing information.
- Do not invent missing values. Use null.
- If the page is a PDF/download notice, still extract from visible text and links.
- Be concise but complete; do not copy the whole page into fields.
- On success, set extraction_status to "ok" or omit it; on failure, set extraction_status to "failed" and error_message.
"""
    
    def _validate_extracted_dates(self, detailed_info: Dict[str, Any], 
                                 basic_tender: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates the main date fields (deadline, publication date) in the detailed info.
        Determines if the tender should be skipped, updates validation status annotations.
        Returns a dict of validation metadata, which should be merged into the result.
        """
        try:
            current_date = datetime.now().date()
            validation_result = {
                'skip_processing': False,
                'date_validation_status': 'valid',
                'validation_notes': []
            }
            
            # Step 1: Inspect the primary deadline
            deadline = self._parse_date(detailed_info.get('deadline') or detailed_info.get('submission_deadline'))
            
            if deadline:
                days_until = (deadline - current_date).days
                
                if days_until < 0:
                    validation_result['skip_processing'] = True
                    validation_result['date_validation_status'] = 'expired'
                    validation_result['validation_notes'].append(f"Deadline passed {abs(days_until)} days ago")
                elif days_until <= 7:
                    validation_result['validation_notes'].append(f"URGENT: {days_until} days until deadline")
                elif days_until <= 30:
                    validation_result['validation_notes'].append(f"High priority: {days_until} days until deadline")
                
                # Annotate date_validation in the structured result
                if 'date_validation' not in detailed_info:
                    detailed_info['date_validation'] = {}
                
                detailed_info['date_validation'].update({
                    'days_until_deadline': days_until,
                    'deadline_status': 'expired' if days_until < 0 else 'urgent' if days_until <= 7 else 'active',
                    'urgency_level': self._calculate_urgency_level(days_until)
                })
            
            # Step 2: Check publication date (if deadline isn't found)
            pub_date = self._parse_date(detailed_info.get('publication_date'))
            if pub_date:
                days_old = (current_date - pub_date).days
                if days_old > self.max_days_old and not deadline:
                    validation_result['skip_processing'] = True
                    validation_result['date_validation_status'] = 'too_old'
                    validation_result['validation_notes'].append(f"Tender too old: {days_old} days")
            
            return validation_result
            
        except Exception as e:
            logger.warning(f"Error in date validation: {e}")
            return {
                'skip_processing': False,
                'date_validation_status': 'validation_error',
                'validation_notes': [f"Date validation error: {str(e)}"]
            }
    
    def _calculate_urgency_level(self, days_until_deadline: int) -> str:
        """
        Categorizes urgency for a tender based on days remaining until deadline.
        Returns one of: 'expired', 'urgent', 'high', 'medium', 'low'.
        """
        if days_until_deadline < 0:
            return 'expired'
        elif days_until_deadline <= 7:
            return 'urgent'
        elif days_until_deadline <= 30:
            return 'high'
        elif days_until_deadline <= 90:
            return 'medium'
        else:
            return 'low'
    
    def _parse_date(self, date_value) -> Optional[datetime.date]:
        """
        Attempts to parse a date value from various common formats.
        Returns a datetime.date if possible, else None.
        """
        if not date_value or date_value in ['null', 'N/A']:
            return None
        
        try:
            if isinstance(date_value, datetime):
                return date_value.date()
            
            date_str = str(date_value).strip()
            if re.match(r"\d{4}-\d{2}-\d{2}[ T]\d", date_str):
                for cut in (19, 16, 10):
                    if len(date_str) < cut:
                        continue
                    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                        try:
                            return datetime.strptime(date_str[:cut], fmt).date()
                        except ValueError:
                            continue
                try:
                    return datetime.fromisoformat(
                        date_str.replace("Z", "+00:00").split("+")[0]
                    ).date()
                except ValueError:
                    pass
            for fmt in ['%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y', '%d-%m-%Y']:
                try:
                    return datetime.strptime(date_str, fmt).date()
                except ValueError:
                    continue
            
            return None
        except Exception:
            return None
    
    def _create_skipped_details(self, basic_tender: Dict[str, Any], reason: str) -> Dict[str, Any]:
        """
        Returns a stubbed-out tender info dict indicating the reason it was skipped,
        for transparency in downstream processing.
        """
        return {
            'detailed_title': basic_tender.get('title', 'N/A'),
            'detailed_description': f"Processing skipped: {reason}",
            'requirements': 'Not processed due to date validation',
            'deadline': None,
            'submission_deadline': None,
            'tender_value': None,
            'duration': None,
            'contact_info': {
                'organization': 'Not processed',
                'contact_person': None,
                'phone': None,
                'email': None,
                'address': None
            },
            'date_validation': {
                'deadline_status': 'expired',
                'urgency_level': 'expired',
                'validation_notes': [reason]
            },
            'documents_required': 'Not processed',
            'evaluation_criteria': 'Not processed',
            'additional_details': f'Tender processing skipped: {reason}',
            'tender_type': None,
            'procurement_method': None,
            'categories': None,
            'extracted_at': datetime.utcnow().isoformat(),
            'extraction_status': 'skipped',
            'skip_reason': reason,
            'source_url': basic_tender.get('url', 'N/A')
        }
    
    def _create_fallback_details(self, basic_tender: Dict[str, Any], error_message: str) -> Dict[str, Any]:
        """
        Returns a minimal tender info structure in the event extraction totally fails.
        Ensures program execution can continue and errors are fully annotated for debugging.
        """
        return {
            'detailed_title': basic_tender.get('title', 'N/A'),
            'detailed_description': f"Detailed extraction failed: {error_message}",
            'requirements': 'Information extraction failed',
            'deadline': None,
            'submission_deadline': None,
            'tender_value': None,
            'duration': None,
            'contact_info': {
                'organization': 'Not available',
                'contact_person': None,
                'phone': None,
                'email': None,
                'address': None
            },
            'documents_required': 'Not available',
            'evaluation_criteria': 'Not available',
            'additional_details': f'Processing error: {error_message}',
            'tender_type': None,
            'procurement_method': None,
            'categories': None,
            'extracted_at': datetime.utcnow().isoformat(),
            'extraction_status': 'failed',
            'error_message': error_message,
            'source_url': basic_tender.get('url', 'N/A')
        }
    
    def _parse_detail_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """
        Parses the JSON response from the LLM, handling both plain JSON and Markdown code fences.
        Returns a dictionary, or None on critical error or if response cannot be parsed as a dict.
        """
        import json
        
        try:
            # Clean up markdown code blocks for robust parsing
            cleaned_text = response_text
            if response_text.startswith('```json'):
                cleaned_text = response_text.replace('```json', '').replace('```', '').strip()
            elif response_text.startswith('```'):
                cleaned_text = response_text.replace('```', '').strip()
            
            detailed_info = json.loads(cleaned_text)
            if not isinstance(detailed_info, dict):
                logger.warning("Detailed response is not a dictionary")
                return None
            
            return detailed_info
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse detailed JSON response: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error parsing detailed response: {e}")
            return None
    
    async def process_multiple_tenders(self, tender_list: List[Dict[str, Any]], 
                                     skip_date_validation: bool = False) -> List[Dict[str, Any]]:
        """
        Loops through and processes a list of tender dictionaries, obtaining detailed info for each.
        Honors skip_date_validation flag.
        
        Args:
            tender_list: List of basic tender information from Agent 1
            skip_date_validation: If True, bypass all date filtering
            
        Returns:
            List of processed detailed tender records, most recent on top
        """
        detailed_results = []
        skipped_count = 0
        
        logger.info(f"Agent 2: Processing {len(tender_list)} tenders (date validation: {'OFF' if skip_date_validation else 'ON'})")
        
        for i, tender in enumerate(tender_list, 1):
            try:
                logger.info(f"Processing tender {i}/{len(tender_list)}: {tender.get('title', 'Unknown')[:50]}...")
                
                detailed_info = await self.extract_tender_details(
                    tender_url=tender.get('url'),
                    basic_tender=tender,
                    skip_date_validation=skip_date_validation
                )
                
                if detailed_info:
                    # Was this tender skipped (e.g., expired)?
                    if detailed_info.get('extraction_status') == 'skipped':
                        skipped_count += 1
                        logger.info(f"Skipped tender {i}/{len(tender_list)}: {detailed_info.get('skip_reason', 'Unknown reason')}")
                        
                        # Only log/append skipped tenders if we're not actively filtering by date
                        if skip_date_validation:
                            combined_result = {
                                **tender,
                                'detailed_info': detailed_info,
                                'processing_status': 'skipped',
                                'processed_at': datetime.utcnow().isoformat()
                            }
                            detailed_results.append(combined_result)
                    elif detailed_info.get('extraction_status') == 'failed':
                        combined_result = {
                            **tender,
                            'detailed_info': detailed_info,
                            'processing_status': 'failed',
                            'processed_at': datetime.utcnow().isoformat()
                        }
                        detailed_results.append(combined_result)
                        logger.warning(
                            "Agent 2: extraction failed for %s: %s",
                            tender.get("url"),
                            detailed_info.get("error_message", "unknown"),
                        )
                    else:
                        # Detailed/valid tender result (LLM ok or heuristic enrich)
                        combined_result = {
                            **tender,
                            'detailed_info': detailed_info,
                            'processing_status': 'completed',
                            'processed_at': datetime.utcnow().isoformat()
                        }
                        detailed_results.append(combined_result)
                        logger.info(f"Successfully processed tender {i}/{len(tender_list)}")
                else:
                    logger.error(f"Failed to process tender {i}/{len(tender_list)}")
                    
            except Exception as e:
                logger.error(f"Error processing tender {i}/{len(tender_list)}: {e}")
                continue
        
        logger.info(f"Agent 2 completed: {len(detailed_results)}/{len(tender_list)} tenders processed successfully")
        if skipped_count > 0:
            logger.info(f"Skipped {skipped_count} tenders due to date validation")
        
        return detailed_results

# =====================================================================================================
# ==============================   DETAILED MODULE COMMENTARY (FILE DOC)   =============================
# =====================================================================================================

# File: app/agents/agent2.py

# High-Level Purpose:
#   This file implements "Agent 2" in a multi-stage tender scraping pipeline. Its responsibilities:
#     - Deeply scrape individual tender pages (HTML), using a purpose-built web scraper.
#     - Use an LLM (Language Model, e.g., GPT-style model) to extract rich, well-structured, 
#       deeply normalized tender data into a strict format, focusing on validating and standardizing
#       all significant dates (publication, submission deadline, project start, and end, etc.).
#     - Enforce business logic regarding tender timeliness—skip expired or excessively old tenders
#       before committing to detailed and costly LLM analysis, and validate LLM outputs for compliance.
#     - Support bulk (multi-tender) processing with robust error handling, accurate logging, 
#       and detailed status tracking per tender.
#
# Class: TenderDetailAgent
#   - Core orchestrator. Contains:
#     - Detailed tender extraction workflow (async, heavy on LLM + web scraping).
#     - Multiple helpers for scraping, parsing, urgent/expired recognition, and fallback error handling.
#     - Complete prompt engineering and well-documented extraction requirements for the LLM.
# 
# Major Internal Workflows:
#   1. Pre-Validation: Uses initial metadata from Agent 1 to quickly skip tenders obviously expired or too old.
#   2. Scraping: Grabs tender HTML via TenderScraper, converts to markdown for the LLM.
#   3. Information Extraction: 
#     - Crafts a precise LLM prompt (see _build_enhanced_detail_extraction_prompt) which forces output of dates, translation, and urgency.
#     - Parses JSON results, adds traceable metadata.
#   4. Date Validation Layer: Examines LLM-extracted dates, normalizes and categorizes tenders as expired/urgent/valid, etc.
#   5. Robust Result Structuring: 
#     - Produces structured outputs for success, expired, or failure scenarios, so the pipeline always produces a result.
#     
# Key Features:
#   - Date handling: Covers all likely international date styles, has extensive fallback & normalization.
#   - Translation: All output is forced to be in English, with clear distinctions of all required fields.
#   - Bulk processing ready: Can handle lists of tens/hundreds of tenders asynchronously, logging progress and errors.
#   - Rich logging: All steps and skips/errors are logged, making troubleshooting and downstream statistics robust.
#
# Pipeline Integration:
#   - Assumes pre-filtered agent (Agent1) produces only relevant tenders (e.g., category-wise), so this agent is free to focus on deep extraction and validation.
#   - Designed to be fast-failing (skip obviously non-timely tenders early) and transparent (reasons for skip/failure are always chained in output).
#
# Configuration Points (for future maintenance):
#   - max_days_old: How old can a tender's publication date be before skipping.
#   - urgent_days_threshold: How soon is "urgent" for deadlines.
#
# Extension/Customization Guidance:
#   - Add new post-extraction fields as your business logic evolves by editing the system prompt and result parsing.
#   - For new date formats, add to _parse_date.
#   - For new data sources, extend the scraper used in _scrape_tender_page.
#
# Module Contract:
#   - Always returns a list of tender dicts (for batch) or a detailed dict (for single), always including skip/failure details if applicable.
#
# Related Files:
#   - Agent1: Initial extraction/keyword filtering.
#   - app/core/llm_factory.py: LLM model instantiation/config.
#   - app/services/scraper.py: TenderScraper class.
#
# End of Agent2.py module commentary.