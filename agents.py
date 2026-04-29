from typing import Dict, List, Optional, TypedDict
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from datetime import datetime, timedelta
import json
import re
from config import Config
from scraper import TenderScraper
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AgentState(TypedDict):
    page_url: str
    page_content: str
    raw_tenders: List[Dict]
    categorized_tenders: List[Dict]
    detailed_tenders: List[Dict]
    keywords_esg: List[str]
    keywords_credit: List[str]
    error: Optional[str]

class TenderAgent:
    def __init__(self):
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            api_key=Config.OPENAI_API_KEY
        )
    
    async def extract_tenders_node(self, state: AgentState) -> AgentState:
        """Agent 1: Extract tenders from page content and categorize them"""
        try:
            logger.info("Agent 1: Extracting and categorizing tenders")
            
            # Debug: Log a sample of the page content
            content_sample = state['page_content'].replace('\n', ' ')
            #logger.info(f"Page content sample: {content_sample}")
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
            response_content = response.content.strip()
            
            logger.info(f"Agent 1 raw response: {response_content[:200]}...")
            
            try:
                # Try to extract JSON from response if it contains extra text
                if response_content.startswith('```json'):
                    # Extract JSON from markdown code block
                    start = response_content.find('[')
                    end = response_content.rfind(']') + 1
                    if start != -1 and end != 0:
                        json_str = response_content[start:end]
                    else:
                        json_str = response_content
                elif response_content.startswith('['):
                    json_str = response_content
                else:
                    # Try to find JSON array in the response
                    start = response_content.find('[')
                    end = response_content.rfind(']') + 1
                    if start != -1 and end != 0:
                        json_str = response_content[start:end]
                    else:
                        logger.warning("No JSON array found in response, using fallback extraction")
                        fallback_tenders = self.fallback_extraction(state)
                        state['categorized_tenders'] = fallback_tenders
                        logger.info(f"Agent 1: Using fallback extraction, found {len(fallback_tenders)} tenders")
                        return state
                
                # Parse JSON response
                tenders_data = json.loads(json_str)
                if not isinstance(tenders_data, list):
                    logger.warning("Response is not a list, wrapping in array")
                    tenders_data = [tenders_data] if tenders_data else []
                
                # If AI found nothing, try fallback extraction
                if len(tenders_data) == 0:
                    logger.info("AI found no tenders, trying fallback extraction")
                    fallback_tenders = self.fallback_extraction(state)
                    if len(fallback_tenders) > 0:
                        tenders_data = fallback_tenders
                        logger.info(f"Fallback extraction found {len(fallback_tenders)} tenders")
                
                state['categorized_tenders'] = tenders_data
                logger.info(f"Agent 1: Extracted {len(tenders_data)} tenders")
                
            except json.JSONDecodeError as e:
                logger.error(f"Agent 1: Failed to parse JSON response: {e}")
                logger.error(f"Raw response: {response_content}")
                # Create a fallback result based on simple text analysis
                fallback_tenders = self.fallback_extraction(state)
                state['categorized_tenders'] = fallback_tenders
                logger.info(f"Agent 1: Using fallback extraction, found {len(fallback_tenders)} tenders")
                
        except Exception as e:
            logger.error(f"Agent 1 error: {e}")
            state['error'] = str(e)
            state['categorized_tenders'] = []
        
        return state
    
    def fallback_extraction(self, state: AgentState) -> List[Dict]:
        """Fallback tender extraction using simple text analysis"""
        try:
            content = state['page_content']
            base_url = state['page_url'].split('/')[0] + '//' + state['page_url'].split('/')[2]
            
            logger.info("Running fallback extraction...")
            
            # Look for date patterns in the content
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
            
            tenders = []
            lines = content.split('\n')
            
            # Look for lines with dates (common in tender listings)
            for i, line in enumerate(lines):
                line_clean = line.strip()
                if not line_clean or len(line_clean) < 5:
                    continue
                
                # Check if line contains a date
                date_found = None
                for pattern in date_patterns:
                    match = re.search(pattern, line_clean)
                    if match:
                        try:
                            if 'января' in pattern or 'февраля' in pattern:  # Russian month names
                                day, month_name, year = match.groups()
                                month = months_ru.get(month_name.lower())
                                if month:
                                    date_found = f"{year}-{month:02d}-{int(day):02d}"
                            else:  # Numeric dates
                                groups = match.groups()
                                if len(groups) == 3:
                                    if '.' in pattern or '/' in pattern:
                                        day, month, year = groups
                                        date_found = f"{year}-{int(month):02d}-{int(day):02d}"
                                    else:  # YYYY-MM-DD format
                                        year, month, day = groups
                                        date_found = f"{year}-{int(month):02d}-{int(day):02d}"
                            break
                        except (ValueError, TypeError):
                            continue
                
                # If we found a date, this might be a tender listing
                if date_found:
                    # Look for context around this line
                    context_lines = []
                    for j in range(max(0, i-2), min(len(lines), i+3)):
                        if lines[j].strip():
                            context_lines.append(lines[j].strip())
                    
                    context = ' '.join(context_lines)
                    
                    # Determine category based on keywords
                    category = 'other'
                    matched_keywords = []
                    context_lower = context.lower()
                    
                    # Check ESG keywords
                    for keyword in state['keywords_esg']:
                        if keyword.lower() in context_lower:
                            category = 'esg'
                            matched_keywords.append(keyword)
                            break
                    
                    # Check Credit Rating keywords
                    if category == 'other':
                        for keyword in state['keywords_credit']:
                            if keyword.lower() in context_lower:
                                category = 'credit_rating'
                                matched_keywords.append(keyword)
                                break
                    
                    # Create tender entry
                    title = line_clean[:100] if len(line_clean) <= 100 else line_clean[:97] + "..."
                    
                    tender = {
                        'title': title,
                        'url': state['page_url'],  # Use the main page URL
                        'date': date_found,
                        'category': category,
                        'description': context[:200] + "..." if len(context) > 200 else context,
                        'matched_keywords': matched_keywords
                    }
                    
                    tenders.append(tender)
                    logger.info(f"Found potential tender: {title[:50]}... on {date_found}")
            
            # If no date-based tenders found, look for tender-related keywords
            if len(tenders) == 0:
                logger.info("No date-based tenders found, looking for keyword-based matches...")
                
                tender_keywords = [
                    'тендер', 'конкурс', 'закупка', 'tender', 'procurement', 'bid', 'rfp',
                    'внутренние тендеры', 'международные тендеры', 'ознакомиться'
                ]
                
                for line in lines:
                    line_clean = line.strip().lower()
                    if any(keyword in line_clean for keyword in tender_keywords):
                        # Found a tender-related line
                        category = 'other'
                        matched_keywords = []
                        
                        # Check for category keywords
                        for keyword in state['keywords_esg']:
                            if keyword.lower() in line_clean:
                                category = 'esg'
                                matched_keywords.append(keyword)
                                break
                        
                        if category == 'other':
                            for keyword in state['keywords_credit']:
                                if keyword.lower() in line_clean:
                                    category = 'credit_rating'
                                    matched_keywords.append(keyword)
                                    break
                        
                        tender = {
                            'title': line.strip()[:100],
                            'url': state['page_url'],
                            'date': None,
                            'category': category,
                            'description': line.strip(),
                            'matched_keywords': matched_keywords
                        }
                        
                        tenders.append(tender)
                        logger.info(f"Found keyword-based tender: {line.strip()[:50]}...")
                        
                        if len(tenders) >= 5:  # Limit to avoid too many results
                            break
            
            logger.info(f"Fallback extraction completed: {len(tenders)} tenders found")
            return tenders[:10]  # Limit to first 10 matches
            
        except Exception as e:
            logger.error(f"Fallback extraction error: {e}")
            return []
    
    def parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string to datetime object"""
        if not date_str or date_str == 'null':
            return None
        
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except:
            try:
                return datetime.strptime(date_str, '%Y-%m-%d')
            except:
                return None

    async def process_tender_details_node(self, state: AgentState) -> AgentState:
        """Agent 2: Extract full details for filtered tenders and save to detailed_tender database"""
        try:
            logger.info("Agent 2: Processing tender details")
            
            # Import database manager here to avoid circular imports
            from database import DatabaseManager
            db_manager = DatabaseManager()
            
            detailed_tenders = []
            
            # Process only the tenders that Agent 1 has already filtered and saved
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
                                
                                # Save to detailed_tender database
                                # First, we need the tender_id from the basic tender saved by Agent 1
                                # For now, we'll store it in the state and let the scheduler handle DB operations
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
    
    def create_workflow(self) -> StateGraph:
        """Create the LangGraph workflow"""
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("extract_tenders", self.extract_tenders_node)
        workflow.add_node("process_details", self.process_tender_details_node)
        
        # Add edges
        workflow.set_entry_point("extract_tenders")
        workflow.add_edge("extract_tenders", "process_details")
        workflow.add_edge("process_details", END)
        
        return workflow.compile()

async def test_agents():
    """Test the agent workflow"""
    agent = TenderAgent()
    workflow = agent.create_workflow()
    
    # Test with sample data
    initial_state = {
        'page_url': 'https://corp.uzairways.com/ru/press-center/tenders',
        'page_content': '''
        Тендеры
        
        04 июня 2025 - Тендер на экологическую оценку проекта
        29 мая 2025 - Конкурс на кредитный рейтинг компании
        20 мая 2025 - Закупка устойчивых материалов для строительства
        ''',
        'raw_tenders': [],
        'categorized_tenders': [],
        'detailed_tenders': [],
        'keywords_esg': Config.ESG_KEYWORDS,
        'keywords_credit': Config.CREDIT_RATING_KEYWORDS,
        'error': None
    }
    
    try:
        result = await workflow.ainvoke(initial_state)
        print("✓ Agent workflow completed successfully")
        print(f"Categorized tenders: {len(result['categorized_tenders'])}")
        print(f"Detailed tenders: {len(result['detailed_tenders'])}")
        
        for tender in result['categorized_tenders']:
            print(f"- {tender.get('title', 'N/A')} [{tender.get('category', 'N/A')}]")
            
    except Exception as e:
        print(f"✗ Agent workflow failed: {e}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_agents())
