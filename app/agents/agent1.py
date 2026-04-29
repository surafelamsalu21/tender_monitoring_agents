"""
FIXED Agent 1: Tender Extraction with STRICT Keyword Filtering
Updated to remove 'both' category - only ESG or Credit Rating
"""
import logging
import json
import re
from typing import Dict, List, Any
from datetime import datetime, timedelta
from langchain_core.messages import HumanMessage

from app.core.llm_factory import get_chat_llm

logger = logging.getLogger(__name__)

class TenderExtractionAgent:
    """
    FIXED Agent 1: Extract tenders with STRICT keyword filtering
    Updated to only use 'esg' or 'credit_rating' categories (no 'both')
    
    Changes:
    - Removed 'both' category logic
    - If tender has keywords from both categories, prioritize by keyword count
    - Enhanced keyword matching logic
    - Better validation of extracted tenders
    """
    
    def __init__(self):
        self.llm = get_chat_llm(temperature=0.1)
        
        # Configurable settings for date filtering
        self.max_days_old = 90
        self.min_days_deadline = 1
    
    async def extract_and_categorize_tenders(self, page_content: str, 
                                           esg_keywords: List[str], 
                                           credit_keywords: List[str],
                                           include_all_tenders: bool = False) -> List[Dict[str, Any]]:
        """
        Main asynchronous method to extract and categorize tenders from provided page content.

        Args:
            page_content (str): HTML/markdown content containing tenders.
            esg_keywords (List[str]): List of ESG-related keywords for strict filtering.
            credit_keywords (List[str]): List of credit rating-related keywords.
            include_all_tenders (bool): If True, process all tenders (for testing) regardless of keywords.

        Returns:
            List[Dict[str, Any]]: List of tenders, each as a dict, categorized as 'esg' or 'credit_rating'.
        """
        try:
            logger.info("Agent 1: Starting STRICT tender extraction (ESG or Credit Rating only)")
            logger.info(f"ESG keywords: {esg_keywords}")
            logger.info(f"Credit keywords: {credit_keywords}")
            logger.info(f"Keyword filtering: {'DISABLED' if include_all_tenders else 'ENABLED (STRICT)'}")
            
            # Step 1: Pre-check if the content contains any relevant keywords
            if not include_all_tenders:
                keyword_found = self._check_keywords_in_content(page_content, esg_keywords + credit_keywords)
                if not keyword_found:
                    logger.info("Agent 1: No ESG or Credit Rating keywords found in content - skipping extraction")
                    return []
            
            # Step 2: Construct strict prompt for LLM
            system_prompt = self._build_strict_extraction_prompt(esg_keywords, credit_keywords, include_all_tenders)
            
            # Step 3: Build the user message with clear extraction and categorization instructions
            user_message = f"""
KEYWORDS TO MATCH (MANDATORY):
=============================
ESG Keywords: {', '.join(esg_keywords)}
Credit Rating Keywords: {', '.join(credit_keywords)}

CONTENT TO ANALYZE:
==================
{page_content}

CRITICAL INSTRUCTION: 
- ONLY extract tenders that contain at least ONE keyword from the lists above
- If a tender doesn't mention these specific keywords, DO NOT include it
- Categorize as either 'esg' OR 'credit_rating' (no 'both' category)
- If tender has keywords from both categories, choose the category with MORE keyword matches
- Return EMPTY ARRAY [] if no tenders contain the keywords

Return ONLY the JSON array with tenders that contain the specified keywords.
"""
            
            # Step 4: Submit the formatted message to the LLM and get a response
            messages = [
                HumanMessage(content=f"{system_prompt}\n\n{user_message}")
            ]
            
            response = await self.llm.ainvoke(messages)
            response_text = response.content.strip()
            
            logger.info(f"Agent 1 raw response: {response_text[:300]}...")
            
            # Step 5: Parse the LLM JSON output
            tenders = self._parse_json_response(response_text)
            
            # Step 6: Validate that extracted tenders strictly match keywords and are categorized correctly
            if not include_all_tenders:
                validated_tenders = self._double_check_keyword_matching(tenders, esg_keywords, credit_keywords)
                logger.info(f"Before keyword validation: {len(tenders)} tenders")
                logger.info(f"After keyword validation: {len(validated_tenders)} tenders")
                tenders = validated_tenders
            
            # Step 7: Remove old or expired tenders based on date
            if not include_all_tenders:
                filtered_tenders = self._apply_date_filtering(tenders)
                logger.info(f"After date filtering: {len(filtered_tenders)} tenders")
                tenders = filtered_tenders
            
            # Step 8: Final validation and cleaning of output tenders
            final_tenders = self._validate_tenders(tenders)
            
            logger.info(f"Agent 1 COMPLETED: {len(final_tenders)} valid tenders extracted")
            self._log_categorization_summary(final_tenders, esg_keywords, credit_keywords)
            
            return final_tenders
            
        except Exception as e:
            logger.error(f"Agent 1 failed: {e}")
            return []
    
    def _check_keywords_in_content(self, content: str, keywords: List[str]) -> bool:
        """
        Fast, simple check: is *any* ESG or Credit Rating keyword present in content?

        Args:
            content (str): The full text content to search.
            keywords (List[str]): List of keywords to search for.

        Returns:
            bool: True if any keyword is found, else False.
        """
        content_lower = content.lower()
        
        for keyword in keywords:
            if keyword.lower() in content_lower:
                logger.info(f"Pre-check: Found keyword '{keyword}' in content")
                return True
        
        logger.info("Pre-check: No keywords found in content")
        return False
    
    def _build_strict_extraction_prompt(self, esg_keywords: List[str], 
                                      credit_keywords: List[str],
                                      include_all_tenders: bool) -> str:
        """
        Build the prompt presented to the LLM. This prompt directs the LLM to enforce mandatory
        keyword-based extraction, with only two allowable categories: 'esg' and 'credit_rating'.
        There is never a 'both' category.

        Args:
            esg_keywords: List of ESG-related keywords as strings.
            credit_keywords: List of credit rating-related keywords.
            include_all_tenders: If true, disables filtering (for test purposes).

        Returns:
            Formatted prompt string for LLM usage.
        """
        
        esg_keywords_str = ", ".join(esg_keywords)
        credit_keywords_str = ", ".join(credit_keywords)
        
        keyword_filtering_rules = ""
        if not include_all_tenders:
            keyword_filtering_rules = f"""
MANDATORY KEYWORD FILTERING:
============================
🚨 CRITICAL: ONLY extract tenders that contain these EXACT keywords:

ESG KEYWORDS (case-insensitive): {esg_keywords_str}
CREDIT RATING KEYWORDS (case-insensitive): {credit_keywords_str}

STRICT RULES:
1. The tender title OR description MUST contain at least ONE keyword from either list
2. If NO keywords are found, DO NOT extract the tender
3. Be case-insensitive but look for EXACT word matches
4. Partial matches are OK (e.g., "environmental" matches "environment")
5. If you find ZERO tenders with keywords, return EMPTY ARRAY []

CATEGORIZATION RULES (NO 'BOTH' CATEGORY):
==========================================
- If tender contains ONLY ESG keywords → category: "esg"
- If tender contains ONLY Credit Rating keywords → category: "credit_rating"
- If tender contains keywords from BOTH lists → choose category with MORE keyword matches
- If equal matches from both → default to "esg"

EXAMPLE MATCHES:
- "Environmental impact assessment" → Contains "environmental" (ESG) → category: "esg"
- "Credit risk evaluation" → Contains "credit" (Credit Rating) → category: "credit_rating"
- "Environmental credit assessment" → Contains both → count matches → assign to category with more
- "Construction project management" → NO KEYWORDS → DO NOT EXTRACT
"""
        else:
            keyword_filtering_rules = """
KEYWORD FILTERING: DISABLED
===========================
Extract ALL tenders regardless of keywords (testing mode).
Categorize randomly as 'esg' or 'credit_rating'.
"""
        
        return f"""You are a STRICT tender extraction specialist. Your task is to:

1. ONLY extract tenders that contain the specified keywords
2. Categorize each tender as EITHER 'esg' OR 'credit_rating' (never 'both')
3. Translate all content to English
4. Return structured JSON format

{keyword_filtering_rules}

EXTRACTION REQUIREMENTS:
========================
1. Extract title, URL, date, and brief description
2. TRANSLATE all non-English content to English
3. Keep URLs unchanged
4. Convert dates to YYYY-MM-DD format
5. Extract ONLY tenders that match the keyword criteria

OUTPUT FORMAT:
==============
Return ONLY a JSON array in this exact format:
[
  {{
    "title": "English translated title",
    "url": "full URL to tender page",
    "date": "YYYY-MM-DD or null",
    "description": "English translated brief description",
    "category": "esg|credit_rating",
    "matched_keywords": ["keyword1", "keyword2"],
    "esg_keyword_count": 2,
    "credit_keyword_count": 0,
    "confidence_score": 0.95
  }}
]

VALIDATION CHECKLIST:
====================
Before including any tender, verify:
✓ Title or description contains at least one specified keyword
✓ Keyword match is case-insensitive but exact
✓ All text is translated to English
✓ Category is ONLY 'esg' or 'credit_rating' (never 'both')
✓ Category reflects the keyword type with more matches
✓ Matched keywords list shows which keywords were found

IMPORTANT:
- Return EMPTY ARRAY [] if no tenders contain the specified keywords
- Do NOT extract tenders about construction, IT, general services unless they mention ESG/credit keywords
- Be STRICT - only extract tenders that actually relate to ESG or credit rating topics
- NO 'both' category allowed - choose esg OR credit_rating based on keyword count"""
    
    def _double_check_keyword_matching(self, tenders: List[Dict[str, Any]], 
                                     esg_keywords: List[str], 
                                     credit_keywords: List[str]) -> List[Dict[str, Any]]:
        """
        Double-check that the returned tenders actually contain the required keywords and are
        properly categorized. This enforces that no 'both' category is present and the highest
        matching type is favored.

        Args:
            tenders: List of tender info dictionaries from LLM.
            esg_keywords: List of ESG keywords.
            credit_keywords: List of Credit Rating keywords.

        Returns:
            List of validated/recategorized tenders (dicts).
        """
        validated_tenders = []
        
        for tender in tenders:
            title = tender.get('title', '').lower()
            description = tender.get('description', '').lower()
            content = f"{title} {description}"
            
            # Track which keywords are actually found in the content
            found_esg_keywords = []
            found_credit_keywords = []
            
            for keyword in esg_keywords:
                if keyword.lower() in content:
                    found_esg_keywords.append(keyword)
            for keyword in credit_keywords:
                if keyword.lower() in content:
                    found_credit_keywords.append(keyword)
            
            total_found_keywords = found_esg_keywords + found_credit_keywords
            
            if total_found_keywords:
                esg_count = len(found_esg_keywords)
                credit_count = len(found_credit_keywords)
                # Determine category: whichever type has more matches, default to esg if tied
                if esg_count > credit_count:
                    category = 'esg'
                elif credit_count > esg_count:
                    category = 'credit_rating'
                else:
                    category = 'esg' if esg_count > 0 else 'credit_rating'
                
                # Update tender dict with new fields and corrected category
                tender['matched_keywords'] = total_found_keywords
                tender['esg_keyword_count'] = esg_count
                tender['credit_keyword_count'] = credit_count
                tender['keyword_count'] = len(total_found_keywords)
                tender['category'] = category
                
                validated_tenders.append(tender)
                
                logger.info(f"✓ Validated: '{tender['title'][:50]}...' → {category}")
                logger.info(f"  ESG keywords: {found_esg_keywords} (count: {esg_count})")
                logger.info(f"  Credit keywords: {found_credit_keywords} (count: {credit_count})")
            else:
                logger.warning(f"✗ REJECTED: '{tender.get('title', 'Unknown')[:50]}...' - No keywords found")
        
        return validated_tenders
    
    def _apply_date_filtering(self, tenders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Remove tenders that are too old, based on a date threshold. If the tender is missing
        a date, it's included with a flagged status.

        Args:
            tenders: List of tender dictionaries.

        Returns:
            Filtered list containing only recent/valid tenders.
        """
        filtered_tenders = []
        current_date = datetime.now().date()
        max_age = timedelta(days=self.max_days_old)
        
        for tender in tenders:
            try:
                date_str = tender.get('date')
                if date_str:
                    tender_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    days_old = (current_date - tender_date).days
                    
                    if days_old <= self.max_days_old:
                        tender['date_status'] = 'recent'
                        filtered_tenders.append(tender)
                        logger.debug(f"✓ Date OK: {tender['title'][:30]}... ({days_old} days old)")
                    else:
                        logger.info(f"✗ Too old: {tender['title'][:30]}... ({days_old} days old)")
                else:
                    # If no date field, allow but mark as 'unknown'
                    tender['date_status'] = 'unknown'
                    filtered_tenders.append(tender)
                    logger.debug(f"✓ No date: {tender['title'][:30]}...")
                    
            except Exception as e:
                logger.warning(f"Date parsing error for tender: {e}")
                tender['date_status'] = 'error'
                filtered_tenders.append(tender)  # Include on error
        
        return filtered_tenders
    
    def _parse_json_response(self, response_text: str) -> List[Dict[str, Any]]:
        """
        Parse LLM output, handling code block markdown and returning an array of dicts.

        Args:
            response_text (str): The LLM's reply (may be a JSON array or wrapped in markdown).

        Returns:
            List[Dict[str, Any]]: Parsed list of tenders, or empty list on parse failure.
        """
        try:
            cleaned_text = response_text
            if response_text.startswith('```json'):
                cleaned_text = response_text.replace('```json', '').replace('```', '').strip()
            elif response_text.startswith('```'):
                cleaned_text = response_text.replace('```', '').strip()
            
            tenders = json.loads(cleaned_text)
            
            if not isinstance(tenders, list):
                logger.warning("Response is not a list, converting to empty list")
                return []
            
            return tenders
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.error(f"Response preview: {response_text[:200]}...")
            return []
        except Exception as e:
            logger.error(f"Unexpected error parsing response: {e}")
            return []
    
    def _validate_tenders(self, tenders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Final cleaning and structuring of tender data, enforcing field requirements
        and allowed category values.

        Args:
            tenders: List of tender dictionaries.

        Returns:
            List of fully validated, structured tenders (dict).
        """
        validated = []
        
        for tender in tenders:
            try:
                if not tender.get('title') or not tender.get('url'):
                    logger.warning(f"Skipping tender with missing title or URL: {tender}")
                    continue
                
                category = tender.get('category', '').lower()
                if category not in ['esg', 'credit_rating']:
                    logger.warning(f"Invalid category '{category}' for tender: {tender.get('title', 'N/A')}")
                    category = 'esg'
                
                if 'matched_keywords' not in tender:
                    tender['matched_keywords'] = []
                
                cleaned_tender = {
                    'title': str(tender.get('title', '')).strip(),
                    'url': str(tender.get('url', '')).strip(),
                    'date': tender.get('date'),
                    'description': str(tender.get('description', '')).strip()[:500],  # Optional: truncate
                    'category': category,
                    'matched_keywords': tender.get('matched_keywords', []),
                    'esg_keyword_count': tender.get('esg_keyword_count', 0),
                    'credit_keyword_count': tender.get('credit_keyword_count', 0),
                    'keyword_count': len(tender.get('matched_keywords', [])),
                    'date_status': tender.get('date_status', 'unknown'),
                    'confidence_score': tender.get('confidence_score', 0.8)
                }
                validated.append(cleaned_tender)
            except Exception as e:
                logger.warning(f"Error validating tender: {e}, tender: {tender}")
                continue
        
        return validated
    
    def _log_categorization_summary(self, tenders: List[Dict[str, Any]], 
                                  esg_keywords: List[str], credit_keywords: List[str]):
        """
        Outputs informational logs, summarizing the number and type of extracted tenders,
        as well as statistics on keyword usage.

        Args:
            tenders: List of final validated tenders.
            esg_keywords: List of ESG keywords.
            credit_keywords: List of credit rating keywords.
        """
        if not tenders:
            logger.info("❌ No tenders found matching ESG or Credit Rating keywords")
            logger.info(f"   Searched for ESG: {esg_keywords}")
            logger.info(f"   Searched for Credit: {credit_keywords}")
            return
        
        esg_count = len([t for t in tenders if t['category'] == 'esg'])
        credit_count = len([t for t in tenders if t['category'] == 'credit_rating'])
        
        # Gather global keyword usage statistics
        all_matched_keywords = []
        for tender in tenders:
            all_matched_keywords.extend(tender.get('matched_keywords', []))
        
        keyword_usage = {}
        for keyword in all_matched_keywords:
            keyword_usage[keyword] = keyword_usage.get(keyword, 0) + 1
        
        logger.info("✅ EXTRACTION SUMMARY (No 'Both' Category):")
        logger.info(f"   ESG tenders: {esg_count}")
        logger.info(f"   Credit Rating tenders: {credit_count}")
        logger.info(f"   Total: {len(tenders)}")
        
        if keyword_usage:
            logger.info("📊 KEYWORD USAGE:")
            for keyword, count in sorted(keyword_usage.items(), key=lambda x: x[1], reverse=True):
                keyword_type = "ESG" if keyword in esg_keywords else "Credit Rating"
                logger.info(f"   '{keyword}' ({keyword_type}): {count} matches")
        
        # Show a few sample tenders
        logger.info("🔍 SAMPLE RESULTS:")
        for i, tender in enumerate(tenders[:3]):
            esg_count = tender.get('esg_keyword_count', 0)
            credit_count = tender.get('credit_keyword_count', 0)
            logger.info(f"   {i+1}. {tender['title'][:50]}... → {tender['category']}")
            logger.info(f"      ESG keywords: {esg_count}, Credit keywords: {credit_count}")
            logger.info(f"      Matched: {tender['matched_keywords']}")
    
    async def save_keyword_matches_to_db(self, tender_id: int, matched_keywords: List[str], 
                                       tender_repo, keyword_repo, db):
        """
        Optional: Save keyword-to-tender associations to the database.
        Useful for analytics, feedback, and reporting on keyword usage.

        Args:
            tender_id (int): Database row id for tender.
            matched_keywords (List[str]): List of found keywords.
            tender_repo: Repo/controller for tender-related DB ops.
            keyword_repo: Repo/controller for keyword-related DB ops.
            db: Database session/connection object.
        """
        try:
            for keyword_str in matched_keywords:
                # Retrieve all ESG and Credit Rating keywords from DB for lookups
                keywords = keyword_repo.get_keywords_by_category(db, "esg") + \
                          keyword_repo.get_keywords_by_category(db, "credit_rating")
                
                for keyword_obj in keywords:
                    if keyword_obj.keyword.lower() == keyword_str.lower():
                        # Create association row and increment keyword usage stats
                        tender_repo.add_keyword_match(db, tender_id, keyword_obj.id)
                        keyword_obj.increment_usage()
                        logger.info(f"Saved keyword match: tender {tender_id} ↔ keyword '{keyword_str}'")
                        break
        except Exception as e:
            logger.error(f"Error saving keyword matches: {e}")


class KeywordMatcher:
    """
    Utility class for advanced keyword matching logic.
    Supports fuzzy/stemmed and word-boundary matching (optional use).
    """

    @staticmethod
    def find_keyword_matches(text: str, keywords: List[str]) -> List[str]:
        """
        Finds keyword matches in text, supporting basic stemming and word boundary logic.

        Args:
            text: Text to be analyzed.
            keywords: List of keywords to try to match/fuzzily find.

        Returns:
            List of matching keywords detected in the text.
        """
        text_lower = text.lower()
        matches = []
        
        for keyword in keywords:
            keyword_lower = keyword.lower()
            
            # Direct substring match
            if keyword_lower in text_lower:
                matches.append(keyword)
                continue
            
            # Basic stemmed match (naive, for items ending in s/ing/ed)
            keyword_stem = keyword_lower.rstrip('s').rstrip('ing').rstrip('ed')
            if len(keyword_stem) > 3 and keyword_stem in text_lower:
                matches.append(keyword)
                continue
            
            # Word boundary regex match (precise)
            pattern = r'\b' + re.escape(keyword_lower) + r'\b'
            if re.search(pattern, text_lower):
                matches.append(keyword)
        
        return list(set(matches))  # Remove duplicates

# -------------------------------------------------------------------
# DETAILED COMMENTS ABOUT THIS CODE AND FILE

# This file (app/agents/agent1.py) defines an extraction agent (TenderExtractionAgent)
# for processing tenders scraped from web pages. Its main focus is on enforcing *strict*
# keyword-based filtering to identify and extract only tenders that are relevant to either
# "ESG" (environmental, social, and governance) or "Credit Rating" topics.
#
# KEY POINTS:
#
# - There are two main categories: 'esg' and 'credit_rating'. *No* 'both' option is allowed.
#   If a tender includes keywords from both areas, the agent picks the category with the most matches.
#
# - The extraction process has several robust layers:
#       1. Fast pre-filter: Checks the content for presence of *any* ESG/Credit keywords.
#       2. Strict system/user prompts for the LLM, commanding it to extract only matching tenders.
#       3. The result is parsed, and post-processed in Python to recheck both keyword matching
#          and strict category assignment—guarding against LLM mistakes.
#       4. Optional date filtering is enforced; tenders older than max_days_old are skipped.
#       5. Extensive validation for each tender's structure, category, and fields before returning.
#
# - Logging is detailed and systematic:
#       * Logs all stages including the initial request, any keyword finds, response statistics,
#         filtering steps, keyword usage stats, and even sample results.
#
# - Helper methods are modular/private, making testing and maintenance easy.
#
# - The KeywordMatcher class (at the end) provides advanced keyword matching logic, including
#   basic stemming and word-boundary regex, which can help in fuzzy matching if needed.
#
# - The class also optionally saves keyword-to-tender correlations to a database for analytics.
#
# - This file is a key "intelligent agent" in the processing pipeline: it bridges raw scraped
#   tender content, the LLM for semantic extraction, and rigorous post-extraction checks to
#   guarantee data is relevant, accurate, and useful.
#
# HOW TO USE / EXTEND:
#
# - Main entrypoint is extract_and_categorize_tenders (async method).
# - Keyword lists must be provided: esg_keywords, credit_keywords.
# - Database functions are abstracted and optional (not required for core extraction).
# - The prompt and filtering logic are completely focused on strict inclusiveness/exclusiveness
#   for only the two categories of interest.
#
# The combination of LLM-powered structured extraction + hard Python-side validation provides
# high reliability for downstream use (analytics, display, storage).
#
# -------------------------------------------------------------------