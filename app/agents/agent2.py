"""
Enhanced Agent 2: Detail Extraction with Date Validation
Validates tender dates and filters out expired tenders
"""
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from langchain_core.messages import HumanMessage

from app.core.llm_factory import get_chat_llm
from app.services.scraper import TenderScraper

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
            page_content = await self._scrape_tender_page(tender_url)
            
            if not page_content:
                logger.error(f"Agent 2: Failed to scrape tender page: {tender_url}")
                return self._create_fallback_details(basic_tender, "Failed to scrape page")
            
            # Step 2: Extract detailed tender information using the LLM, with focus on date fields
            detailed_info = await self._extract_detailed_info_with_dates(page_content, basic_tender)
            
            if not detailed_info:
                logger.error(f"Agent 2: Failed to extract details from: {tender_url}")
                return self._create_fallback_details(basic_tender, "Failed to extract details")
            
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
    
    async def _scrape_tender_page(self, tender_url: str) -> Optional[str]:
        """
        Scrapes the tender page using the TenderScraper service and returns its content (in markdown).
        """
        try:
            logger.info(f"Scraping tender page: {tender_url}")
            
            async with TenderScraper() as scraper:
                result = await scraper.scrape_page(tender_url)
                
                if result['status'] == 'success':
                    content = result['markdown']
                    logger.info(f"Successfully scraped {len(content)} characters from {tender_url}")
                    return content
                else:
                    logger.error(f"Scraping failed for {tender_url}: {result.get('error', 'Unknown error')}")
                    return None
                    
        except Exception as e:
            logger.error(f"Exception while scraping {tender_url}: {e}")
            return None
    
    async def _extract_detailed_info_with_dates(self, page_content: str, 
                                              basic_tender: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
Category: {basic_tender.get('category', 'N/A')}
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
                # Attach metadata for traceability & analytics
                detailed_info['extracted_at'] = datetime.utcnow().isoformat()
                detailed_info['page_content_length'] = len(page_content)
                detailed_info['source_url'] = basic_tender.get('url')
                
                return detailed_info
            else:
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
        return f"""You are a professional tender analysis specialist. Extract comprehensive details with special focus on DATE VALIDATION.

CRITICAL DATE REQUIREMENTS:
============================
1. Extract ALL dates mentioned in the tender
2. Identify publication date, submission deadline, project start/end dates
3. Convert all dates to YYYY-MM-DD format
4. Validate that deadlines are in the future (after {datetime.now().strftime('%Y-%m-%d')})
5. Mark urgency level based on deadline proximity

TRANSLATION REQUIREMENTS:
=========================
- TRANSLATE ALL non-English content to English
- Maintain original meaning and context
- Use clear, professional English

EXTRACTION REQUIREMENTS:
========================
Extract and return as JSON:

{{
  "detailed_title": "Complete translated title",
  "detailed_description": "Full translated description",
  "requirements": "Technical requirements and qualifications",
  
  "publication_date": "YYYY-MM-DD or null",
  "submission_deadline": "YYYY-MM-DD or null",
  "deadline": "YYYY-MM-DD or null (primary deadline)",
  "project_start_date": "YYYY-MM-DD or null",
  "project_end_date": "YYYY-MM-DD or null",
  
  "date_validation": {{
    "deadline_status": "active|expired|urgent|unknown",
    "days_until_deadline": number or null,
    "urgency_level": "low|medium|high|expired",
    "all_extracted_dates": ["YYYY-MM-DD", ...]
  }},
  
  "tender_value": "Budget/estimated value with currency",
  "duration": "Project duration/timeline",
  "contact_info": {{
    "organization": "Issuing organization",
    "contact_person": "Contact person name",
    "phone": "Phone number",
    "email": "Email address",
    "address": "Physical address"
  }},
  "documents_required": "Required documents/certificates",
  "evaluation_criteria": "Evaluation criteria",
  "additional_details": "Other important information",
  "tender_type": "Type of tender",
  "procurement_method": "Procurement method",
  "categories": "Relevant categories"
}}

DATE EXTRACTION RULES:
======================
- Look for keywords: "deadline", "submission date", "closing date", "due date"
- Look for: "срок подачи", "до", "крайний срок", "дедлайн"
- Parse formats: DD.MM.YYYY, DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD
- If deadline is past current date, mark as "expired"
- If deadline is within 7 days, mark as "urgent"
- If deadline is within 30 days, mark as "high" urgency

URGENCY LEVELS:
===============
- expired: Deadline has passed
- urgent: Deadline within 7 days
- high: Deadline within 30 days
- medium: Deadline within 90 days
- low: Deadline beyond 90 days

IMPORTANT:
==========
- Be comprehensive and accurate
- All text must be in English
- Focus on date accuracy and validation
- If dates are unclear, mark as "unknown"
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
            
            date_str = str(date_value)
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
                    else:
                        # Detailed/valid tender result
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