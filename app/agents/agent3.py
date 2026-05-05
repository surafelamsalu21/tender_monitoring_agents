"""
Enhanced Agent 3: Rich Detailed Email Composer Agent
Creates beautiful, detailed emails with full tender information and modern CSS styling
"""
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from langchain_core.messages import HumanMessage

from app.core.config import settings
from app.core.llm_factory import get_chat_llm

logger = logging.getLogger(__name__)

class EmailComposerAgent:
    """
    Agent 3: Compose rich, detailed emails with beautiful formatting
    
    Role:
    - Take detailed tender information from Agent 2
    - Create comprehensive, well-formatted emails
    - Use modern CSS styling for professional appearance
    - Handle multiple tenders efficiently
    """

    def __init__(self):
        # Initializes the LLM used for composing emails, with low temperature for deterministic output
        self.llm = get_chat_llm(temperature=0.1)

    def _get_team_name(self, team_category: str) -> str:
        if team_category == "screening_opportunities":
            return "Opportunities Team"
        return "Opportunity Review Team"
    
    async def compose_tender_email(self, tender_data: Dict[str, Any], 
                                   detailed_info: Dict[str, Any], 
                                   team_category: str) -> Dict[str, Any]:
        """
        Compose rich, detailed email content for a tender notification.
        Args:
            tender_data: Basic tender information from Agent 1
            detailed_info: Detailed tender information from Agent 2
            team_category: Target notification stream (e.g., "screening_opportunities")
        Returns:
            Dictionary with comprehensive email content, or None if failed.
        """
        try:
            logger.info(
                f"Agent 3: Composing detailed email for {team_category} team - {tender_data.get('title', 'Unknown')[:50]}..."
            )

            # Generate a comprehensive, role-focused prompt for the LLM
            email_prompt = self._build_detailed_email_prompt(team_category)

            # Build user message to inject all available tender details
            user_message = f"""
BASIC TENDER INFORMATION:
========================
Title: {tender_data.get('title', 'N/A')}
URL: {tender_data.get('url', 'N/A')}
Screening Category: {tender_data.get('category', 'screening_opportunities')}
Step 1 Yes Count: {tender_data.get('screening', {}).get('yes_count', 'N/A')}
Passes Filter: {tender_data.get('screening', {}).get('passes_filter', 'N/A')}
Date: {tender_data.get('date', 'N/A')}
Description: {tender_data.get('description', 'N/A')}
Matched Keywords: {', '.join(tender_data.get('matched_keywords', []))}

DETAILED INFORMATION FROM AGENT 2:
==================================
{self._format_all_details(detailed_info)}

Please compose a comprehensive, well-formatted email for the {team_category.upper()} team.
Include ALL available details and make it visually appealing with proper sections.
Return ONLY the JSON object with no additional text.
"""

            # Call the LLM with the constructed messages
            messages = [
                HumanMessage(content=f"{email_prompt}\n\n{user_message}")
            ]
            response = await self.llm.ainvoke(messages)
            response_text = response.content.strip()

            # Parse the JSON-like response
            email_content = self._parse_email_response(response_text)

            if email_content:
                # Append generation metadata
                email_content['generated_at'] = datetime.utcnow().isoformat()
                email_content['team_category'] = team_category
                email_content['tender_id'] = tender_data.get('id')
                email_content['agent_version'] = '3.0-enhanced'
                
                logger.info(
                    f"Agent 3: Successfully composed detailed email for {team_category} team"
                )
                return email_content
            else:
                logger.error(
                    f"Agent 3: Failed to parse email response for {team_category} team"
                )
                return None

        except Exception as e:
            logger.error(
                f"Agent 3: Error composing email for {team_category} team: {e}"
            )
            return None

    def _build_detailed_email_prompt(self, team_category: str) -> str:
        """Builds a comprehensive prompt for the LLM to compose an email, customized for the team category."""
        team_name = self._get_team_name(team_category)

        return f"""You are composing a comprehensive, professional email notification for the {team_name}.
This opportunity has already passed the Screening Checklist shortlist stage.

Screening Checklist context to respect:
- Step 1: 5 relevance checks; recommended tier when yes_count >= 3 (emails target this tier)
- Step 2: non-blocking flags (opportunity characteristics, strategic signals, potential concerns)
- Step 3: baseline capture (title, source, country, type, deadline, estimated budget, link)

REQUIREMENTS:
=============
1. Use ALL available detailed information from Agent 2
2. Create a visually appealing, well-structured email
3. Include modern CSS styling for professional appearance
4. Make it comprehensive but scannable
5. Use clear sections and proper formatting
6. Include all contact details, requirements, deadlines
7. Make it actionable with clear next steps

EMAIL STRUCTURE:
================
Compose a detailed email with this structure:

{{
  "subject": "Clear, informative subject line including key details",
  "priority": "High|Medium|Low (based on deadline urgency)",
  "summary": "2-3 sentence executive summary of the opportunity",
  "tender_details": {{
    "title": "Full tender title",
    "organization": "Issuing organization",
    "deadline": "Deadline with urgency assessment",
    "value": "Tender value/budget if available",
    "scope": "What exactly they need",
    "requirements": "Key requirements and qualifications"
  }},
  "contact_info": {{
    "organization": "Contact organization",
    "person": "Contact person name",
    "phone": "Phone number",
    "email": "Email address",
    "address": "Address if available"
  }},
  "next_steps": "Clear action items for the team",
  "html_body": "Complete HTML email with modern CSS styling and all details"
}}

CSS STYLING REQUIREMENTS:
=========================
- Modern, professional design
- Clean typography with good readability
- Color-coded sections for easy scanning
- Responsive design that works on mobile
- Clear visual hierarchy
- Action buttons with hover effects
- Professional color scheme (blues, grays, whites)
- Keep action buttons in a stable horizontal row on desktop
- Use a dedicated button container so buttons never break section alignment

CONTENT REQUIREMENTS:
====================
- Include ALL detailed information from Agent 2
- Show complete requirements list
- Display full contact information
- Include deadline with urgency indicator
- Show tender value/budget if available
- Add clear call-to-action buttons
- Include all relevant dates and timelines
- In "Next Steps", place exactly two primary actions side-by-side:
  1) View Full Details
  2) Start Proposal Preparation

TONE AND STYLE:
===============
- Professional but engaging
- Clear and direct communication
- Well-organized information hierarchy
- Emphasis on actionable next steps
- Include urgency indicators where appropriate

HTML STRUCTURE REQUIREMENTS:
============================
- Header section with opportunity title and screening status
- Executive summary section
- Detailed tender information section
- Requirements section with bullet points
- Contact information section
- Timeline/deadline section with urgency
- Next steps section with action buttons
- Footer with system information
- In Next Steps, render buttons in this pattern:
  - A container with `display:flex; justify-content:center; gap:12px; flex-wrap:nowrap; align-items:center;`
  - Buttons with equal height/padding and consistent width behavior
  - On small screens only, allow vertical stacking using a media query

Use modern HTML/CSS practices and ensure the email looks professional in all email clients."""
    
    def _format_all_details(self, detailed_info: Dict[str, Any]) -> str:
        """
        Formats all detailed tender info as a readable multiline string for prompt context.

        Args:
            detailed_info: dictionary with possibly many tender fields

        Returns:
            string of key: value, one per line
        """
        formatted_details = []
        detail_mapping = {
            'detailed_title': 'Detailed Title',
            'detailed_description': 'Detailed Description',
            'requirements': 'Requirements',
            'deadline': 'Deadline',
            'submission_deadline': 'Submission Deadline',
            'tender_value': 'Tender Value',
            'duration': 'Project Duration',
            'contact_info': 'Contact Information',
            'documents_required': 'Required Documents',
            'evaluation_criteria': 'Evaluation Criteria',
            'additional_details': 'Additional Details',
            'tender_type': 'Tender Type',
            'procurement_method': 'Procurement Method',
            'categories': 'Categories'
        }
        
        for key, label in detail_mapping.items():
            if key in detailed_info and detailed_info[key]:
                value = detailed_info[key]
                if isinstance(value, dict):
                    formatted_details.append(f"{label}: {value}")
                elif isinstance(value, list):
                    formatted_details.append(f"{label}: {', '.join([str(v) for v in value])}")
                else:
                    formatted_details.append(f"{label}: {str(value)}")
        return "\n".join(formatted_details)

    def _parse_email_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """
        Attempts to extract/parse a JSON dict from the (possibly markdown-wrapped) LLM response.

        Args:
            response_text: raw text (should be a JSON object string)

        Returns:
            dict with email components, or None on failure
        """
        import json
        try:
            # Remove any '```json' or '```' delimiters that may be present
            cleaned_text = response_text
            if response_text.startswith('```json'):
                cleaned_text = response_text.replace('```json', '').replace('```', '').strip()
            elif response_text.startswith('```'):
                cleaned_text = response_text.replace('```', '').strip()
            email_content = json.loads(cleaned_text)
            if not isinstance(email_content, dict):
                logger.warning("Email response is not a dictionary")
                return None
            required_fields = ['subject', 'summary', 'html_body']
            if not all(field in email_content for field in required_fields):
                logger.warning("Missing required fields in email response")
                return None
            return email_content
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse email JSON response: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error parsing email response: {e}")
            return None

    def _create_detailed_fallback_email(self, tender_data: Dict[str, Any], 
                                        detailed_info: Dict[str, Any], 
                                        team_category: str) -> Dict[str, Any]:
        """
        Fallback: Build a rich email structure yourself (without LLM) if LLM fails

        Args:
            tender_data: shallow tender info
            detailed_info: more specific details
            team_category: string

        Returns:
            dict with subject, summary, html, etc.
        """
        team_name = self._get_team_name(team_category)
        title = tender_data.get('title', 'New Tender Opportunity')
        deadline = detailed_info.get('deadline', 'Not specified')
        contact_info = detailed_info.get('contact_info', {})
        requirements = detailed_info.get('requirements', 'See tender details')
        tender_value = detailed_info.get('tender_value', 'Not specified')

        # Allow contact_info to be a JSON string
        if isinstance(contact_info, str):
            try:
                import json
                contact_info = json.loads(contact_info)
            except:
                contact_info = {'organization': contact_info}

        # Determine urgency for visual cues and priority
        urgency = self._assess_deadline_urgency(deadline)
        priority = "High" if urgency == "URGENT" else "Medium"

        return {
            'subject': f"New {team_category.upper()} Tender: {title[:40]}..." + (" [URGENT]" if urgency == "URGENT" else ""),
            'priority': priority,
            'summary': (
                f"A new {team_category} tender opportunity has been identified that requires "
                f"immediate attention from the {team_name}."
            ),
            'tender_details': {
                'title': title,
                'organization': contact_info.get('organization', 'Not specified'),
                'deadline': deadline,
                'value': tender_value,
                'scope': detailed_info.get('detailed_description', tender_data.get('description', 'See tender details')),
                'requirements': requirements
            },
            'contact_info': contact_info,
            'next_steps': 'Review tender details, assess our capabilities, and prepare proposal if suitable.',
            'html_body': self._create_rich_html_template(
                title, team_name, team_category, tender_data, detailed_info, contact_info, urgency
            ),
            'generated_at': datetime.utcnow().isoformat(),
            'team_category': team_category,
            'agent_version': '3.0-enhanced-fallback'
        }

    def _assess_deadline_urgency(self, deadline_str: str) -> str:
        """
        Assess urgency of deadline for tender based on current date.

        Args:
            deadline_str: String representation of deadline, expected format: YYYY-MM-DD <...>

        Returns:
            One of "URGENT", "HIGH", "MEDIUM", or "NORMAL"
        """
        if not deadline_str or deadline_str == 'Not specified':
            return "NORMAL"
        try:
            deadline = datetime.strptime(deadline_str.split()[0], '%Y-%m-%d')
            now = datetime.now()
            days_left = (deadline - now).days
            if days_left <= 3:
                return "URGENT"
            elif days_left <= 7:
                return "HIGH"
            elif days_left <= 14:
                return "MEDIUM"
            else:
                return "NORMAL"
        except Exception:
            return "NORMAL"

    def _create_rich_html_template(self, title: str, team_name: str, team_category: str, 
                                   tender_data: Dict[str, Any], detailed_info: Dict[str, Any], 
                                   contact_info: Dict[str, Any], urgency: str) -> str:
        """
        Assembles a visually rich HTML email string using all available information.
        Used if LLM fallback is needed or for fallback previews.

        Args:
            title, team_name, team_category, tender_data, detailed_info, contact_info, urgency

        Returns:
            HTML string, styled for modern email clients
        """
        # Extract/prepare display fields
        deadline = detailed_info.get('deadline', 'Not specified')
        requirements = detailed_info.get('requirements', 'See tender details')
        tender_value = detailed_info.get('tender_value', 'Not specified')
        description = detailed_info.get('detailed_description', tender_data.get('description', ''))

        # Format requirements (try bulleted list if possible)
        if isinstance(requirements, str) and '\n' in requirements:
            req_list = requirements.split('\n')
            requirements_html = "<ul>" + "".join(
                [f"<li>{req.strip()}</li>" for req in req_list if req.strip()]
            ) + "</ul>"
        else:
            requirements_html = f"<p>{requirements}</p>"

        urgency_colors = {
            "URGENT": "#dc3545",
            "HIGH": "#fd7e14",
            "MEDIUM": "#ffc107",
            "NORMAL": "#28a745"
        }
        urgency_color = urgency_colors.get(urgency, "#6c757d")

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Tender Notification</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f8f9fa;
                }}
                .email-container {{
                    background-color: white;
                    border-radius: 10px;
                    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                    overflow: hidden;
                }}
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 30px;
                    text-align: center;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 24px;
                    font-weight: 600;
                }}
                .header .team-badge {{
                    background-color: rgba(255, 255, 255, 0.2);
                    padding: 5px 15px;
                    border-radius: 20px;
                    font-size: 14px;
                    margin-top: 10px;
                    display: inline-block;
                }}
                .urgency-banner {{
                    background-color: {urgency_color};
                    color: white;
                    text-align: center;
                    padding: 10px;
                    font-weight: bold;
                    text-transform: uppercase;
                    letter-spacing: 1px;
                }}
                .content {{
                    padding: 30px;
                }}
                .tender-title {{
                    color: #2c3e50;
                    font-size: 22px;
                    font-weight: 600;
                    margin: 0 0 20px 0;
                    padding-bottom: 10px;
                    border-bottom: 3px solid #667eea;
                }}
                .section {{
                    margin: 25px 0;
                    padding: 20px;
                    background-color: #f8f9fa;
                    border-radius: 8px;
                    border-left: 4px solid #667eea;
                }}
                .section-title {{
                    color: #495057;
                    font-size: 16px;
                    font-weight: 600;
                    margin: 0 0 15px 0;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }}
                .detail-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 15px;
                    margin: 15px 0;
                }}
                .detail-item {{
                    background: white;
                    padding: 15px;
                    border-radius: 6px;
                    border: 1px solid #e9ecef;
                }}
                .detail-label {{
                    font-weight: 600;
                    color: #6c757d;
                    font-size: 12px;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    margin-bottom: 5px;
                }}
                .detail-value {{
                    color: #2c3e50;
                    font-size: 14px;
                }}
                .requirements ul {{
                    margin: 10px 0;
                    padding-left: 20px;
                }}
                .requirements li {{
                    margin: 8px 0;
                    color: #495057;
                }}
                .contact-card {{
                    background: white;
                    border: 1px solid #dee2e6;
                    border-radius: 8px;
                    padding: 20px;
                    margin: 15px 0;
                }}
                .contact-name {{
                    font-weight: 600;
                    color: #2c3e50;
                    font-size: 16px;
                    margin-bottom: 10px;
                }}
                .contact-details {{
                    color: #6c757d;
                    line-height: 1.8;
                }}
                .cta-section {{
                    text-align: center;
                    margin: 30px 0;
                    padding: 25px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    border-radius: 8px;
                    color: white;
                }}
                .cta-button {{
                    display: inline-block;
                    background-color: white;
                    color: #667eea;
                    padding: 12px 30px;
                    text-decoration: none;
                    border-radius: 25px;
                    font-weight: 600;
                    margin: 10px;
                    transition: all 0.3s ease;
                }}
                .cta-button:hover {{
                    background-color: #f8f9fa;
                    transform: translateY(-2px);
                    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
                }}
                .footer {{
                    background-color: #2c3e50;
                    color: white;
                    padding: 20px;
                    text-align: center;
                    font-size: 12px;
                }}
                .deadline-warning {{
                    background-color: #fff3cd;
                    border: 1px solid #ffeaa7;
                    color: #856404;
                    padding: 15px;
                    border-radius: 8px;
                    margin: 15px 0;
                    text-align: center;
                    font-weight: 600;
                }}
            </style>
        </head>
        <body>
            <div class="email-container">
                <div class="header">
                    <h1>New Tender Opportunity</h1>
                    <div class="team-badge">{team_name}</div>
                </div>
                
                {"<div class='urgency-banner'>⚠️ " + urgency + " DEADLINE</div>" if urgency in ["URGENT", "HIGH"] else ""}
                
                <div class="content">
                    <h2 class="tender-title">{title}</h2>
                    
                    <div class="section">
                        <div class="section-title">📋 Overview</div>
                        <p>{description[:300]}{'...' if len(description) > 300 else ''}</p>
                    </div>
                    
                    <div class="section">
                        <div class="section-title">📊 Key Details</div>
                        <div class="detail-grid">
                            <div class="detail-item">
                                <div class="detail-label">Organization</div>
                                <div class="detail-value">{contact_info.get('organization', 'Not specified')}</div>
                            </div>
                            <div class="detail-item">
                                <div class="detail-label">Deadline</div>
                                <div class="detail-value">{deadline}</div>
                            </div>
                            <div class="detail-item">
                                <div class="detail-label">Tender Value</div>
                                <div class="detail-value">{tender_value}</div>
                            </div>
                            <div class="detail-item">
                                <div class="detail-label">Category</div>
                                <div class="detail-value">{team_category.upper()}</div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="section">
                        <div class="section-title">📝 Requirements</div>
                        <div class="requirements">
                            {requirements_html}
                        </div>
                    </div>
                    
                    <div class="section">
                        <div class="section-title">📞 Contact Information</div>
                        <div class="contact-card">
                            <div class="contact-name">{contact_info.get('contact_person', 'Contact Person Not Specified')}</div>
                            <div class="contact-details">
                                <strong>Organization:</strong> {contact_info.get('organization', 'Not specified')}<br>
                                {"<strong>Phone:</strong> " + contact_info.get('phone', 'Not specified') + "<br>" if contact_info.get('phone') else ""}
                                {"<strong>Email:</strong> " + contact_info.get('email', 'Not specified') + "<br>" if contact_info.get('email') else ""}
                                {"<strong>Address:</strong> " + contact_info.get('address', 'Not specified') if contact_info.get('address') else ""}
                            </div>
                        </div>
                    </div>
                    
                    {f"<div class='deadline-warning'>⏰ ATTENTION: Deadline is {deadline} - Immediate action required!</div>" if urgency in ["URGENT", "HIGH"] else ""}
                    
                    <div class="cta-section">
                        <h3 style="margin-top: 0;">Next Steps</h3>
                        <p>Review the full tender details and assess our capability to participate</p>
                        <a href="{tender_data.get('url', '#')}" class="cta-button">📄 View Full Tender</a>
                        <a href="mailto:{contact_info.get('email', '')}" class="cta-button">📧 Contact Issuer</a>
                    </div>
                </div>
                
                <div class="footer">
                    <p>🤖 Automated notification from {settings.APP_NAME} v3.0</p>
                    <p>Processed by Agent 1 (Extraction) → Agent 2 (Details) → Agent 3 (Email Composition)</p>
                    <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
            </div>
        </body>
        </html>
        """

    async def compose_multiple_tenders_email(self, tenders_with_details: List[Dict[str, Any]], 
                                             team_category: str) -> Dict[str, Any]:
        """
        Compose a single digest email containing several tenders.

        Args:
            tenders_with_details: list of tender dicts (each with 'detailed_info')
            team_category: notification stream identifier

        Returns:
            Dictionary with composed email fields (subject, priority, summary, html_body, ...)
        """
        try:
            logger.info(f"Agent 3: Composing multi-tender email for {team_category} team with {len(tenders_with_details)} tenders")
            
            team_name = self._get_team_name(team_category)
            subject = f"New {team_category.upper()} Tenders - {len(tenders_with_details)} Opportunities Found"
            html_body = self._create_multi_tender_html(tenders_with_details, team_name, team_category)
            return {
                'subject': subject,
                'priority': self._assess_multi_tender_priority(tenders_with_details),
                'summary': f"We found {len(tenders_with_details)} new {team_category} tender opportunities that match your criteria and require immediate review.",
                'tender_count': len(tenders_with_details),
                'html_body': html_body,
                'generated_at': datetime.utcnow().isoformat(),
                'team_category': team_category,
                'agent_version': '3.0-enhanced-multi'
            }
        except Exception as e:
            logger.error(f"Agent 3: Error composing multi-tender email: {e}")
            return self._create_simple_multi_tender_fallback(tenders_with_details, team_category)

    def _assess_multi_tender_priority(self, tenders: List[Dict[str, Any]]) -> str:
        """
        Determines the overall priority for a digest email based on the most urgent tender deadlines.
        """
        urgent_count = 0
        high_count = 0
        for tender in tenders:
            detailed_info = tender.get('detailed_info', {})
            deadline = detailed_info.get('deadline', '')
            urgency = self._assess_deadline_urgency(deadline)
            if urgency == "URGENT":
                urgent_count += 1
            elif urgency == "HIGH":
                high_count += 1

        if urgent_count > 0:
            return "High"
        elif high_count > 0:
            return "Medium"
        else:
            return "Medium"

    def _create_multi_tender_html(self, tenders: List[Dict[str, Any]], 
                                 team_name: str, team_category: str) -> str:
        """
        Produces a visually rich HTML digest with a card for each tender and summary statistics.

        Args:
            tenders, team_name, team_category

        Returns:
            HTML string (digest style)
        """
        tender_cards = ""
        urgent_tenders = []
        for i, tender in enumerate(tenders, 1):
            tender_data = tender
            detailed_info = tender.get('detailed_info', {})
            title = tender_data.get('title', 'Untitled Tender')
            deadline = detailed_info.get('deadline', 'Not specified')
            urgency = self._assess_deadline_urgency(deadline)
            contact_info = detailed_info.get('contact_info', {})
            tender_value = detailed_info.get('tender_value', 'Not specified')
            if urgency in ["URGENT", "HIGH"]:
                urgent_tenders.append((i, title, deadline))
            if isinstance(contact_info, str):
                try:
                    import json
                    contact_info = json.loads(contact_info)
                except:
                    contact_info = {'organization': contact_info}
            urgency_colors = {
                "URGENT": "#dc3545",
                "HIGH": "#fd7e14", 
                "MEDIUM": "#ffc107",
                "NORMAL": "#28a745"
            }
            urgency_color = urgency_colors.get(urgency, "#6c757d")
            tender_cards += f"""
            <div class="tender-card">
                <div class="tender-header">
                    <div class="tender-number">#{i}</div>
                    <div class="urgency-badge" style="background-color: {urgency_color};">{urgency}</div>
                </div>
                <h3 class="tender-title">{title}</h3>
                <div class="tender-meta">
                    <div class="meta-item">
                        <span class="meta-label">Organization:</span>
                        <span class="meta-value">{contact_info.get('organization', 'Not specified')}</span>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label">Deadline:</span>
                        <span class="meta-value">{deadline}</span>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label">Value:</span>
                        <span class="meta-value">{tender_value}</span>
                    </div>
                </div>
                <div class="tender-description">
                    {detailed_info.get('detailed_description', tender_data.get('description', 'No description available'))[:200]}...
                </div>
                <div class="tender-actions">
                    <a href="{tender_data.get('url', '#')}" class="action-btn primary">View Details</a>
                    {"<a href='mailto:" + contact_info.get('email', '') + "' class='action-btn secondary'>Contact</a>" if contact_info.get('email') else ""}
                </div>
            </div>
            """
        # Display summary of urgent tenders if present
        urgent_summary = ""
        if urgent_tenders:
            urgent_list = "".join([f"<li>#{num}: {title} (Due: {deadline})</li>" for num, title, deadline in urgent_tenders])
            urgent_summary = f"""
            <div class="urgent-summary">
                <h3>⚠️ Urgent Deadlines Requiring Immediate Attention</h3>
                <ul>{urgent_list}</ul>
            </div>
            """
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Multiple Tender Opportunities</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 900px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f8f9fa;
                }}
                .email-container {{
                    background-color: white;
                    border-radius: 10px;
                    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                    overflow: hidden;
                }}
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 30px;
                    text-align: center;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 28px;
                    font-weight: 600;
                }}
                .header .subtitle {{
                    opacity: 0.9;
                    margin-top: 10px;
                    font-size: 16px;
                }}
                .stats-bar {{
                    background-color: #2c3e50;
                    color: white;
                    padding: 15px;
                    text-align: center;
                    display: flex;
                    justify-content: space-around;
                    flex-wrap: wrap;
                }}
                .stat-item {{
                    text-align: center;
                    margin: 5px;
                }}
                .stat-number {{
                    font-size: 24px;
                    font-weight: bold;
                    display: block;
                }}
                .stat-label {{
                    font-size: 12px;
                    opacity: 0.8;
                    text-transform: uppercase;
                }}
                .urgent-summary {{
                    background-color: #fff3cd;
                    border: 2px solid #ffc107;
                    padding: 20px;
                    margin: 20px;
                    border-radius: 8px;
                }}
                .urgent-summary h3 {{
                    color: #856404;
                    margin-top: 0;
                }}
                .urgent-summary ul {{
                    color: #856404;
                    margin: 10px 0;
                }}
                .content {{
                    padding: 20px;
                }}
                .tender-card {{
                    background: white;
                    border: 1px solid #dee2e6;
                    border-radius: 8px;
                    margin: 20px 0;
                    padding: 25px;
                    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                    transition: all 0.3s ease;
                }}
                .tender-card:hover {{
                    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
                    transform: translateY(-2px);
                }}
                .tender-header {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 15px;
                }}
                .tender-number {{
                    background-color: #667eea;
                    color: white;
                    width: 30px;
                    height: 30px;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-weight: bold;
                    font-size: 14px;
                }}
                .urgency-badge {{
                    padding: 4px 12px;
                    border-radius: 20px;
                    color: white;
                    font-size: 12px;
                    font-weight: bold;
                    text-transform: uppercase;
                }}
                .tender-title {{
                    color: #2c3e50;
                    font-size: 18px;
                    font-weight: 600;
                    margin: 0 0 15px 0;
                    line-height: 1.4;
                }}
                .tender-meta {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 10px;
                    margin: 15px 0;
                    padding: 15px;
                    background-color: #f8f9fa;
                    border-radius: 6px;
                }}
                .meta-item {{
                    display: flex;
                    flex-direction: column;
                }}
                .meta-label {{
                    font-size: 12px;
                    color: #6c757d;
                    font-weight: 600;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }}
                .meta-value {{
                    font-size: 14px;
                    color: #2c3e50;
                    font-weight: 500;
                    margin-top: 2px;
                }}
                .tender-description {{
                    color: #495057;
                    line-height: 1.6;
                    margin: 15px 0;
                }}
                .tender-actions {{
                    display: flex;
                    gap: 10px;
                    margin-top: 20px;
                    flex-wrap: wrap;
                }}
                .action-btn {{
                    padding: 10px 20px;
                    border-radius: 6px;
                    text-decoration: none;
                    font-weight: 600;
                    font-size: 14px;
                    transition: all 0.3s ease;
                    display: inline-block;
                }}
                .action-btn.primary {{
                    background-color: #667eea;
                    color: white;
                }}
                .action-btn.primary:hover {{
                    background-color: #5a67d8;
                    transform: translateY(-1px);
                }}
                .action-btn.secondary {{
                    background-color: #6c757d;
                    color: white;
                }}
                .action-btn.secondary:hover {{
                    background-color: #5a6268;
                }}
                .summary-section {{
                    background-color: #f8f9fa;
                    padding: 25px;
                    margin: 20px 0;
                    border-radius: 8px;
                    border-left: 4px solid #667eea;
                }}
                .footer {{
                    background-color: #2c3e50;
                    color: white;
                    padding: 20px;
                    text-align: center;
                    font-size: 12px;
                }}
                @media (max-width: 600px) {{
                    .tender-meta {{
                        grid-template-columns: 1fr;
                    }}
                    .tender-actions {{
                        flex-direction: column;
                    }}
                    .action-btn {{
                        text-align: center;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="email-container">
                <div class="header">
                    <h1>New Tender Opportunities</h1>
                    <div class="subtitle">{team_name} - {len(tenders)} Opportunities Found</div>
                </div>
                
                <div class="stats-bar">
                    <div class="stat-item">
                        <span class="stat-number">{len(tenders)}</span>
                        <span class="stat-label">Total Tenders</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-number">{len(urgent_tenders)}</span>
                        <span class="stat-label">Urgent Deadlines</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-number">{team_category.upper()}</span>
                        <span class="stat-label">Category</span>
                    </div>
                </div>
                
                {urgent_summary}
                
                <div class="content">
                    <div class="summary-section">
                        <h3>📋 Executive Summary</h3>
                        <p>We've identified {len(tenders)} new tender opportunities that match your {team_category} criteria. 
                        {'Several require immediate attention due to urgent deadlines.' if urgent_tenders else 'Please review each opportunity and assess our capability to participate.'}</p>
                    </div>
                    
                    {tender_cards}
                    
                    <div class="summary-section">
                        <h3>🎯 Recommended Next Steps</h3>
                        <ol>
                            <li><strong>Immediate Review:</strong> {"Focus on urgent deadlines first" if urgent_tenders else "Review all opportunities systematically"}</li>
                            <li><strong>Capability Assessment:</strong> Evaluate our qualifications against each tender's requirements</li>
                            <li><strong>Team Meeting:</strong> Schedule discussion to prioritize opportunities</li>
                            <li><strong>Proposal Planning:</strong> Begin preparation for selected tenders</li>
                        </ol>
                    </div>
                </div>
                
                <div class="footer">
                    <p>🤖 Automated notification from {settings.APP_NAME} v3.0</p>
                    <p>Processed by Agent 1 (Extraction) → Agent 2 (Details) → Agent 3 (Email Composition)</p>
                    <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
            </div>
        </body>
        </html>
        """

    def _create_simple_multi_tender_fallback(self, tenders: List[Dict[str, Any]], 
                                             team_category: str) -> Dict[str, Any]:
        """
        If rich digest formatting fails, compose a dead-simple HTML email as fallback.
        """
        team_name = self._get_team_name(team_category)
        return {
            'subject': f"New {team_category.upper()} Tenders - {len(tenders)} Found",
            'priority': 'Medium',
            'summary': f"We found {len(tenders)} new tender opportunities for the {team_name}.",
            'tender_count': len(tenders),
            'html_body': f"""
            <div style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto;">
                <h2>New Tender Opportunities - {team_name}</h2>
                <p>We found {len(tenders)} new tender(s) that match your criteria.</p>
                {''.join([f'''
                <div style="border: 1px solid #ddd; margin: 15px 0; padding: 15px; border-radius: 5px;">
                    <h3>{tender.get('title', 'Untitled Tender')}</h3>
                    <p><strong>Category:</strong> {team_category.upper()}</p>
                    <p><a href="{tender.get('url', '#')}" style="color: #007bff;">View Tender Details</a></p>
                </div>
                ''' for tender in tenders])}
                <p>Please review these opportunities and assess our capability to participate.</p>
            </div>
            """,
            'generated_at': datetime.utcnow().isoformat(),
            'team_category': team_category,
            'agent_version': '3.0-fallback-multi'
        }

    async def compose_multiple_emails(self, tenders_with_details: List[Dict[str, Any]], 
                                      team_category: str) -> List[Dict[str, Any]]:
        """
        Compose emails for multiple tenders -- determines if digest or individual emails

        Args:
            tenders_with_details: list of tenders, each with details inside (they may have 'detailed_info')
            team_category: notification stream identifier

        Returns:
            List of dicts: each represents an email to be sent, with metadata etc.
        """
        email_compositions = []
        logger.info(f"Agent 3: Composing emails for {len(tenders_with_details)} tenders for {team_category} team")
        # If more than one, send digest, else send individual
        if len(tenders_with_details) > 1:
            logger.info(f"Agent 3: Creating digest email for {len(tenders_with_details)} tenders")
            digest_email = await self.compose_multiple_tenders_email(tenders_with_details, team_category)
            if digest_email:
                email_compositions.append({
                    'tender_data': {'title': f'Multiple Tenders Digest', 'count': len(tenders_with_details)},
                    'email_content': digest_email,
                    'composition_status': 'success',
                    'email_type': 'digest'
                })
        else:
            for tender_data in tenders_with_details:
                try:
                    detailed_info = tender_data.get('detailed_info', {})
                    email_content = await self.compose_tender_email(
                        tender_data=tender_data,
                        detailed_info=detailed_info,
                        team_category=team_category
                    )
                    if email_content:
                        email_compositions.append({
                            'tender_data': tender_data,
                            'email_content': email_content,
                            'composition_status': 'success',
                            'email_type': 'individual'
                        })
                except Exception as e:
                    logger.error(f"Agent 3: Error composing individual email: {e}")
                    continue
        logger.info(f"Agent 3: Completed enhanced email composition - {len(email_compositions)} emails created")
        return email_compositions

# =============================================================
# ==========================  DETAILED COMMENTS  ==========================
#
# File: app/agents/agent3.py
#
# OVERVIEW:
#  - This file defines the EmailComposerAgent class, responsible for assembling
#    rich, well-formatted tender notification emails for a team.
#  - The agent takes structured tender data (from previous agents in the pipeline) 
#    and produces fully detailed notification emails, including modern HTML+CSS design.
#  - The agent supports both (1) individual tender emails, and (2) digest emails covering multiple tenders.
#  - For HTML and text generation, the agent uses a language model (LLM), but has robust local fallbacks.
#
# DESIGN:
#  - The primary interface is EmailComposerAgent, which exposes async methods for composing single 
#    and multiple tender emails.
#    - compose_tender_email: for a single tender (uses LLM if possible, falls back if not)
#    - compose_multiple_tenders_email: creates a digest email listing several tenders
#    - compose_multiple_emails: master coordinator, determines whether to use digest or individual mode
#  - Fallback logic is present throughout: if LLM output cannot be parsed, the agent generates
#    the email using its own templates to avoid disruption.
#  - HTML content generated includes:
#      - sections for title, urgent deadlines, summary, tender details, requirements, contact info, next steps, and a footer
#      - color coding, urgency badges, and call-to-action buttons for professionalism and scanability.
#
# KEY COMPONENTS:
#  - _build_detailed_email_prompt: Creates a precise system+user prompt for the LLM, instructing it about 
#      structure, styling, content, urgency, tone, etc.
#  - _format_all_details: Consolidates all detailed info into a prompt-friendly string.
#  - _parse_email_response: Attempts to safely extract the expected data fields from often-messy LLM results.
#  - _assess_deadline_urgency: Maps tender deadline strings to established urgency bands for human triage.
#  - _create_rich_html_template & _create_multi_tender_html: Responsible for rendering
#      robust, mobile-friendly HTML emails (with fallback content if LLM fails).
#  - Logging is used extensively throughout for tracing all major steps and errors.
#
# USAGE:
#  - This agent is the final "step" in a tender pipeline: it expects tender data already extracted and organized.
#  - It is well-suited for organizations needing professional, actionable, and prioritized notifications for new opportunities.
#  - Robust fallback logic means it is suitable for automated production settings.
#
# EXTENSIBILITY:
#  - Easily modified for new notification formats or additional content fields.
#  - Prompt and template strings are centralized for easier prompt engineering and UI refinement.
#
# LIMITATIONS:
#  - Relies on proper structure of incoming data (from prior agents or scrapers).
#  - Some dependency on the LLM’s consistency; however, robust fallback logic is in place.
#