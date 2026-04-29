"""
AI Agents Service
Multi-agent system using langgraph for tender extraction and processing
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, TypedDict
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END
import asyncio

from app.core.config import settings
from app.services.scraper import TenderScraper

logger = logging.getLogger(__name__)

class AgentState(TypedDict):
    """State shared between agents"""
    page_url: str
    page_content: str
    keywords_esg: List[str]
    keywords_credit: List[str]
    categorized_tenders: List[Dict[str, Any]]
    detailed_tenders: List[Dict[str, Any]]
    error: str

class TenderAgent:
    """Multi-agent system for tender extraction and processing"""
    
    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.OPENAI_MODEL,
            api_key=settings.OPENAI_API_KEY,
            temperature=0.1
        )
        self.workflow = self.create_workflow()
    
    def create_workflow(self) -> StateGraph:
        """Create the multi-agent workflow"""
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("extract_tenders", self.extract_tenders_node)
        workflow.add_node("process_details", self.process_tender_details_node)
        
        # Add edges
        workflow.set_entry_point("extract_tenders")
        workflow.add_edge("extract_tenders", "process_details")
        workflow.add_edge("process_details", END)
        
        return workflow.compile()
    
    async def extract_tenders_node(self, state: AgentState) -> AgentState:
        """Agent 1: Extract and filter tenders by keywords"""
        try:
            logger.info("Agent 1: Starting tender extraction")
            
            # Log page content length only (avoid Unicode issues)
            logger.info(f"Total page content length: {len(state['page_content'])} characters")
            
            system_prompt = """You are a tender extraction specialist. Your task is to:
1. Extract ONLY procurement/tender opportunities that contain the specified ESG or Credit Rating keywords
2. Be STRICT - only extract tenders that actually mention the provided keywords
3. ALWAYS respond in ENGLISH, even if the source content is in another language
4. DO NOT extract general tenders that don't contain the specified keywords

IMPORTANT FILTERING RULES:
- ONLY extract tenders that contain at least one ESG keyword OR one Credit Rating keyword
- ESG keywords: environmental, sustainability, green, carbon, climate, renewable, social responsibility, governance, ESG
- Credit Rating keywords: credit, rating, financial, risk, assessment, audit, creditworthiness
- If a tender doesn't contain any of these keywords, DO NOT include it
- Be case-insensitive when matching keywords

Extract information with:
- Title/name (TRANSLATE TO ENGLISH)
- URL/link (use page URL if no specific link found)
- Date (extract any date you find, even if not directly related)
- Brief description (TRANSLATE TO ENGLISH)

Categorize each tender as:
- 'esg' if it mentions: environmental, sustainability, green, carbon, climate, renewable, social responsibility, governance, ESG
- 'credit_rating' if it mentions: credit, rating, financial, risk, assessment, audit, creditworthiness
- 'both' if it contains both types of keywords

Return ONLY a valid JSON array:
[
  {
    "title": "tender title (IN ENGLISH)",
    "url": "full URL or page URL",
    "date": "YYYY-MM-DD or null",
    "category": "esg|credit_rating|both",
    "description": "brief description (IN ENGLISH)",
    "matched_keywords": ["keyword1", "keyword2"]
  }
]

CRITICAL: Only include tenders that contain the specified keywords. If no tenders match the keywords, return an empty array [].
IMPORTANT: Your response must be ONLY valid JSON, no additional text. ALL TEXT FIELDS MUST BE IN ENGLISH."""

            user_prompt = f"""
Page URL: {state['page_url']}
ESG Keywords: {', '.join(state['keywords_esg'])}
Credit Rating Keywords: {', '.join(state['keywords_credit'])}

Page Content (look for procurement opportunities that contain the specified keywords):
{state['page_content']}

Extract ONLY tenders that contain at least one ESG keyword OR one Credit Rating keyword. Be strict and only include tenders that actually mention the provided keywords. Return ONLY valid JSON."""

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            response = await self.llm.ainvoke(messages)
            
            logger.info(f"Agent 1 raw response: {response.content[:200]}...")
            
            try:
                # Parse JSON response
                response_content = response.content.strip()
                if response_content.startswith('```json'):
                    start = response_content.find('[')
                    end = response_content.rfind(']') + 1
                    json_str = response_content[start:end]
                else:
                    json_str = response_content
                
                tenders = json.loads(json_str)
                
                if not isinstance(tenders, list):
                    tenders = []
                
                logger.info(f"Agent 1: Extracted {len(tenders)} tenders")
                state['categorized_tenders'] = tenders
                
            except json.JSONDecodeError as e:
                logger.error(f"Agent 1: Failed to parse JSON response: {e}")
                logger.error(f"Raw response: {response.content}")
                
                # Fallback extraction using regex
                tenders = self.fallback_extraction(state['page_content'], state['page_url'], state['keywords_esg'], state['keywords_credit'])
                state['categorized_tenders'] = tenders
                logger.info(f"Agent 1: Fallback extraction found {len(tenders)} tenders")
            
        except Exception as e:
            logger.error(f"Agent 1 error: {e}")
            state['error'] = str(e)
            state['categorized_tenders'] = []
        
        return state
    
    def fallback_extraction(self, content: str, page_url: str, esg_keywords: List[str], credit_keywords: List[str]) -> List[Dict[str, Any]]:
        """Fallback extraction using regex patterns"""
        import re
        from datetime import datetime
        
        tenders = []
        
        # Combine all keywords for matching
        all_keywords = esg_keywords + credit_keywords
        
        # Look for tender-like patterns that contain keywords
        content_lower = content.lower()
        
        # Check if any keywords are present
        found_keywords = []
        for keyword in all_keywords:
            if keyword.lower() in content_lower:
                found_keywords.append(keyword)
        
        if found_keywords:
            # Simple extraction - create one tender entry for the page
            category = 'esg' if any(k in esg_keywords for k in found_keywords) else 'credit_rating'
            if any(k in esg_keywords for k in found_keywords) and any(k in credit_keywords for k in found_keywords):
                category = 'both'
            
            tender = {
                'title': f"Tender opportunity containing {', '.join(found_keywords[:3])}",
                'url': page_url,
                'date': datetime.now().strftime('%Y-%m-%d'),
                'category': category,
                'description': content[:200] + "..." if len(content) > 200 else content,
                'matched_keywords': found_keywords[:5]  # Limit to first 5
            }
            tenders.append(tender)
        
        return tenders
    
    async def process_tender_details_node(self, state: AgentState) -> AgentState:
        """Agent 2: Extract full details for filtered tenders"""
        try:
            logger.info("Agent 2: Processing tender details")
            
            detailed_tenders = []
            
            # Process only the tenders that Agent 1 has already filtered
            async with TenderScraper() as scraper:
                for tender in state['categorized_tenders']:
                    try:
                        logger.info(f"Agent 2: Processing detailed info for: {tender.get('title', 'N/A')[:50]}...")
                        
                        # Scrape the tender's specific URL for detailed information
                        result = await scraper.scrape_page(tender['url'])
                        
                        if result['status'] == 'success':
                            # Generate detailed description using AI
                            system_prompt = """You are a tender detail extraction specialist. Your task is to:
1. Extract comprehensive details from tender pages
2. Provide all information in ENGLISH, regardless of source language
3. Be thorough and accurate

Extract the following information:
- Full tender title (TRANSLATE TO ENGLISH)
- Complete description (TRANSLATE TO ENGLISH)
- Requirements and specifications (TRANSLATE TO ENGLISH)
- Deadline/closing date
- Contact information
- Any other relevant details

Return ONLY a valid JSON object:
{
  "title": "full tender title (IN ENGLISH)",
  "description": "comprehensive description (IN ENGLISH)",
  "requirements": "key requirements (IN ENGLISH)",
  "deadline": "YYYY-MM-DD or null",
  "contact_info": "contact details (IN ENGLISH)",
  "additional_details": "other relevant information (IN ENGLISH)"
}

IMPORTANT: ALL TEXT MUST BE IN ENGLISH. Return only valid JSON."""
                            
                            user_prompt = f"""
Tender Title: {tender.get('title', 'N/A')}
Category: {tender.get('category', 'N/A')}
Original Description: {tender.get('description', 'N/A')}

Full Page Content:
{result['markdown']}

Generate a detailed professional summary of this tender."""

                            messages = [
                                SystemMessage(content=system_prompt),
                                HumanMessage(content=user_prompt)
                            ]
                            
                            response = await self.llm.ainvoke(messages)
                            
                            try:
                                # Parse the AI response
                                response_content = response.content.strip()
                                if response_content.startswith('```json'):
                                    start = response_content.find('{')
                                    end = response_content.rfind('}') + 1
                                    json_str = response_content[start:end]
                                else:
                                    json_str = response_content
                                
                                detailed_info = json.loads(json_str)
                                
                                # Add full content to detailed info
                                detailed_info['full_content'] = result['markdown']
                                
                                detailed_tender = {
                                    **tender,
                                    'detailed_info': detailed_info,
                                    'processing_status': 'processed',
                                    'processed_at': datetime.utcnow().isoformat()
                                }
                                
                                detailed_tenders.append(detailed_tender)
                                logger.info(f"Agent 2: Successfully processed detailed info for: {tender.get('title', 'N/A')[:50]}...")
                                
                            except json.JSONDecodeError as e:
                                logger.error(f"Agent 2: Failed to parse detailed response for {tender.get('title', 'N/A')}: {e}")
                                # Create fallback detailed info
                                detailed_tender = {
                                    **tender,
                                    'detailed_info': {
                                        'title': tender.get('title', 'N/A'),
                                        'description': result['markdown'][:1000] + "..." if len(result['markdown']) > 1000 else result['markdown'],
                                        'requirements': 'Information extraction failed',
                                        'deadline': None,
                                        'contact_info': 'Not available',
                                        'additional_details': 'Processing error occurred'
                                    },
                                    'full_content': result['markdown'],
                                    'processing_status': 'partial',
                                    'processed_at': datetime.utcnow().isoformat()
                                }
                                detailed_tenders.append(detailed_tender)
                        else:
                            logger.error(f"Agent 2: Failed to scrape tender details: {result.get('error', 'Unknown error')}")
                            
                    except Exception as e:
                        logger.error(f"Agent 2: Error processing tender {tender.get('title', 'N/A')}: {e}")
                        continue
            
            state['detailed_tenders'] = detailed_tenders
            logger.info(f"Agent 2: Processed {len(detailed_tenders)} detailed tenders")
            
        except Exception as e:
            logger.error(f"Agent 2 error: {e}")
            state['error'] = str(e)
            state['detailed_tenders'] = []
        
        return state
    
    async def process_page(self, page_url: str, keywords_esg: List[str], keywords_credit: List[str]) -> Dict[str, Any]:
        """Process a single page through the agent workflow"""
        try:
            logger.info(f"Processing page: {page_url}")
            
            # Scrape the page first
            async with TenderScraper() as scraper:
                result = await scraper.scrape_page(page_url)
            
            if result['status'] != 'success':
                return {
                    'status': 'failed',
                    'error': result.get('error', 'Failed to scrape page'),
                    'categorized_tenders': [],
                    'detailed_tenders': []
                }
            
            # Initialize state
            initial_state = {
                'page_url': page_url,
                'page_content': result['markdown'],
                'keywords_esg': keywords_esg,
                'keywords_credit': keywords_credit,
                'categorized_tenders': [],
                'detailed_tenders': [],
                'error': ''
            }
            
            # Run the workflow
            final_state = await self.workflow.ainvoke(initial_state)
            
            return {
                'status': 'success',
                'categorized_tenders': final_state.get('categorized_tenders', []),
                'detailed_tenders': final_state.get('detailed_tenders', []),
                'error': final_state.get('error', '')
            }
            
        except Exception as e:
            logger.error(f"Error processing page {page_url}: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'categorized_tenders': [],
                'detailed_tenders': []
            }
