"""
Enhanced Email Notification Service with Database Integration
Updated to use email addresses from database and log all email activities
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Any
from datetime import datetime
import logging
import json
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.tender import Tender
from app.repositories.email_settings_repository import EmailSettingsRepository

logger = logging.getLogger(__name__)

class EnhancedEmailService:
    """
    Enhanced email service class that sends tender notifications via email.
    Utilizes database-stored recipient addresses, logs all email activities,
    and integrates with an intelligent email content agent for improved message composition.
    """

    def __init__(self):
        # SMTP configuration from application settings
        self.smtp_server = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.email_user = settings.EMAIL_USER
        self.email_password = settings.EMAIL_PASSWORD
        # Repository for accessing and logging email settings and activities
        self.email_repo = EmailSettingsRepository()

    async def send_intelligent_notifications(self, email_compositions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Sends out multiple tender notifications using AI-composed content,
        retrieving recipient emails for each tender's team category from the database.
        Logs activity and errors in the database.

        Args:
            email_compositions: List of dicts containing 'tender_data' and 'email_content'

        Returns:
            Dict summarizing results of all send attempts
        """
        try:
            results = {
                'total_compositions': len(email_compositions),
                'sent_successfully': 0,
                'failed_sends': 0,
                'errors': [],
                'sent_emails': []
            }
            
            if not email_compositions:
                logger.info("No email compositions to send")
                return results

            logger.info(f"Sending {len(email_compositions)} intelligent email notifications using database emails...")

            db = SessionLocal()
            try:
                for composition in email_compositions:
                    try:
                        # Delegate sending to per-composition worker
                        result = await self._send_single_intelligent_email_db(composition, db)
                        td = composition.get('tender_data') or {}
                        title_short = (td.get('title') or 'Unknown')[:50]

                        if result['success']:
                            results['sent_successfully'] += result.get('emails_sent', 0)
                            details = result.get('sent_details') or []
                            # Scheduler / logs expect team_category + tender_title on each row
                            for row in details:
                                if 'tender_title' not in row:
                                    row['tender_title'] = title_short
                                if 'team_category' not in row:
                                    row['team_category'] = (
                                        (composition.get('email_content') or {}).get('team_category')
                                        or 'screening_opportunities'
                                    )
                            results['sent_emails'].extend(details)
                            logger.info("Successfully sent intelligent emails for: %s...", title_short)
                        else:
                            results['failed_sends'] += 1
                            results['errors'].append({
                                'tender_title': title_short + '...',
                                'error': result['error']
                            })
                            logger.error(f"Failed to send intelligent emails: {result['error']}")
                    except Exception as e:
                        results['failed_sends'] += 1
                        results['errors'].append({
                            'tender_title': composition.get('tender_data', {}).get('title', 'Unknown')[:50] + "...",
                            'error': str(e)
                        })
                        logger.error(f"Error sending intelligent email: {e}")
            finally:
                db.close()
            
            logger.info(f"Intelligent email notifications completed: {results['sent_successfully']} emails sent successfully")
            return results

        except Exception as e:
            logger.error(f"Error in intelligent notifications: {e}")
            return {
                'total_compositions': len(email_compositions),
                'sent_successfully': 0,
                'failed_sends': len(email_compositions),
                'errors': [{'tender_title': 'All', 'error': str(e)}],
                'sent_emails': []
            }

    async def _send_single_intelligent_email_db(self, composition: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """
        Sends an intelligent (AI/composed) email for a single tender composition
        to all recipients in the appropriate team category.
        Handles successes and failures per recipient and logs all activities.

        Args:
            composition: Dict containing 'tender_data' and 'email_content'
            db: SQLAlchemy database session

        Returns:
            Dict with details on the send attempt
        """
        try:
            tender_data = composition['tender_data']
            email_content = composition['email_content']
            team_category = email_content['team_category']
            
            # Retrieve recipient emails for the corresponding team category from DB
            recipient_emails = self.email_repo.get_emails_by_category(db, team_category)
            
            if not recipient_emails:
                error_msg = f"No email addresses configured for {team_category} team in database"
                logger.warning(error_msg)
                return {
                    'success': False,
                    'error': error_msg,
                    'emails_sent': 0
                }
            
            # Check global notification preferences from DB
            preferences = self.email_repo.get_notification_preferences(db)
            if not preferences.get('send_for_new_tenders', True):
                logger.info(f"New tender notifications disabled for {team_category} team")
                return {
                    'success': True,
                    'message': 'Notifications disabled',
                    'emails_sent': 0
                }
            
            sent_details = []
            failed_sends = 0

            # Loop through recipients and send individual emails
            for recipient_email in recipient_emails:
                try:
                    # Assemble the email message
                    msg = MIMEMultipart('alternative')
                    msg['Subject'] = email_content['subject']
                    msg['From'] = self.email_user
                    msg['To'] = recipient_email

                    # Mark as high-priority if applicable
                    if email_content.get('priority') == 'High':
                        msg['X-Priority'] = '1'
                        msg['Importance'] = 'high'

                    # Main HTML body, plus a snippet of metadata in hidden HTML comments for audit/tracking
                    html_content = email_content['html_body']
                    html_content += f"""
                    <!-- Email Metadata -->
                    <!-- Agent Version: {email_content.get('agent_version', '3.0')} -->
                    <!-- Tender ID: {email_content.get('tender_id', 'N/A')} -->
                    <!-- Generated At: {email_content.get('generated_at', 'N/A')} -->
                    <!-- Team Category: {team_category} -->
                    <!-- Priority: {email_content.get('priority', 'Medium')} -->
                    <!-- Recipient: {recipient_email} -->
                    """

                    html_part = MIMEText(html_content, 'html', 'utf-8')
                    msg.attach(html_part)

                    # Perform SMTP transaction
                    with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                        server.starttls()
                        server.login(self.email_user, self.email_password)
                        server.send_message(msg)

                    # Log success in notification log table via repository
                    self.email_repo.log_email_notification(
                        db=db,
                        recipient_email=recipient_email,
                        email_type='new_tender',
                        team_category=team_category,
                        subject=email_content['subject'],
                        status='sent',
                        tender_id=email_content.get('tender_id')
                    )

                    td_title = str(tender_data.get('title') or 'Tender')[:200]
                    sent_details.append({
                        'recipient': recipient_email,
                        'subject': email_content['subject'],
                        'priority': email_content.get('priority', 'Medium'),
                        'sent_at': datetime.utcnow().isoformat(),
                        'tender_title': td_title,
                        'team_category': team_category,
                    })
                    logger.info(f"Email sent successfully to {recipient_email} for {team_category} team")

                except Exception as e:
                    # Track and log any failures per recipient
                    failed_sends += 1
                    error_msg = f"Failed to send to {recipient_email}: {str(e)}"
                    logger.error(error_msg)

                    # Log failure in notification log
                    self.email_repo.log_email_notification(
                        db=db,
                        recipient_email=recipient_email,
                        email_type='new_tender',
                        team_category=team_category,
                        subject=email_content['subject'],
                        status='failed',
                        error_message=str(e),
                        tender_id=email_content.get('tender_id')
                    )

            emails_sent = len(sent_details)
            success = emails_sent > 0

            return {
                'success': success,
                'emails_sent': emails_sent,
                'failed_sends': failed_sends,
                'sent_details': sent_details,
                'message': f"Sent to {emails_sent}/{len(recipient_emails)} recipients"
            }

        except Exception as e:
            error_msg = f"Error in single email send: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'emails_sent': 0
            }

    async def send_fallback_notifications(self, tenders: List[Tender], category: str) -> bool:
        """
        Sends a simple/fallback tender notification (no AI composition)
        to all recipients in a given team category, using the plain fallback template.
        This is used when Agent 3 or enriched notification fails/is unavailable.

        Args:
            tenders: List of Tender ORM instances
            category: Notification stream/category (e.g., 'screening_opportunities')

        Returns:
            True if process completed (regardless of recipient-level errors), False on early runtime error
        """
        try:
            if not tenders:
                logger.info(f"No tenders to notify for category: {category}")
                return True

            db = SessionLocal()
            try:
                recipient_emails = self.email_repo.get_emails_by_category(db, category)
                if not recipient_emails:
                    logger.warning(f"No email addresses configured for {category} team in database")
                    return False

                preferences = self.email_repo.get_notification_preferences(db)
                if not preferences.get('send_for_new_tenders', True):
                    logger.info(f"New tender notifications disabled for {category} team")
                    return True

                subject = f"New {category.upper()} Tenders - {len(tenders)} Found"

                # Send basic/fallback email to each recipient
                for recipient_email in recipient_emails:
                    try:
                        msg = MIMEMultipart('alternative')
                        msg['Subject'] = subject
                        msg['From'] = self.email_user
                        msg['To'] = recipient_email

                        # Compose fallback HTML (non-AI) notification
                        html_content = self._create_fallback_tender_email(tenders, category)
                        html_part = MIMEText(html_content, 'html', 'utf-8')
                        msg.attach(html_part)

                        with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                            server.starttls()
                            server.login(self.email_user, self.email_password)
                            server.send_message(msg)

                        # Log success
                        self.email_repo.log_email_notification(
                            db=db,
                            recipient_email=recipient_email,
                            email_type='fallback_notification',
                            team_category=category,
                            subject=subject,
                            status='sent'
                        )
                        logger.info(f"Fallback email sent successfully to {recipient_email}")

                    except Exception as e:
                        # Log failure for this recipient
                        error_msg = f"Failed to send fallback email to {recipient_email}: {str(e)}"
                        logger.error(error_msg)
                        self.email_repo.log_email_notification(
                            db=db,
                            recipient_email=recipient_email,
                            email_type='fallback_notification',
                            team_category=category,
                            subject=subject,
                            status='failed',
                            error_message=str(e)
                        )

                logger.info(f"Successfully sent fallback email notifications to {len(recipient_emails)} recipients for {len(tenders)} {category} tenders")
                return True

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Failed to send fallback email notifications: {e}")
            return False

    def _create_fallback_tender_email(self, tenders: List[Tender], category: str) -> str:
        """
        Internal utility to create the HTML body for non-AI fallback tender notifications.

        Args:
            tenders: List of Tender ORM objects
            category: Category/team string

        Returns:
            HTML string for use in email body
        """
        # Human-readable team label
        if category == "screening_opportunities":
            team_name = "Opportunities Team"
        else:
            team_name = "Opportunity Review Team"

        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background-color: #f8f9fa; padding: 20px; border-radius: 5px; }}
                .tender {{ border: 1px solid #ddd; margin: 15px 0; padding: 15px; border-radius: 5px; }}
                .tender-title {{ font-size: 18px; font-weight: bold; color: #333; }}
                .tender-category {{ background-color: #007bff; color: white; padding: 3px 8px; border-radius: 3px; font-size: 12px; }}
                .tender-date {{ color: #666; font-size: 14px; }}
                .tender-description {{ margin: 10px 0; line-height: 1.5; }}
                .tender-link {{ color: #007bff; text-decoration: none; }}
                .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; color: #666; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>New Tender Notifications - {team_name}</h2>
                <p>We found {len(tenders)} new tender(s) that match your criteria.</p>
                <p><em>Enhanced AI email composition was not available. Using basic notification format.</em></p>
            </div>
        """
        # Render each tender in the fallback card style
        for tender in tenders:
            tender_date = tender.tender_date.strftime("%Y-%m-%d") if tender.tender_date else "Date not specified"
            html_content += f"""
            <div class="tender">
                <div class="tender-title">{tender.title}</div>
                <div style="margin: 5px 0;">
                    <span class="tender-category">SCREENED OPPORTUNITY</span>
                    <span class="tender-date">Date: {tender_date}</span>
                </div>
                <div class="tender-description">
                    {tender.description[:500] if tender.description else 'No description available'}{'...' if tender.description and len(tender.description) > 500 else ''}
                </div>
                <div>
                    <a href="{tender.url}" class="tender-link">View Full Tender →</a>
                </div>
            </div>
            """
        html_content += f"""
            <div class="footer">
                <p>This is an automated notification from {settings.APP_NAME} using database-stored email addresses.</p>
                <p>If you no longer wish to receive these notifications, please contact your administrator.</p>
            </div>
        </body>
        </html>
        """
        return html_content

    async def test_email_connection(self) -> Dict[str, Any]:
        """
        Utility function to check email connection/configuration
        via a quick starttls/login test. Does not send actual mail.

        Returns:
            Dict with 'status' and 'message'
        """
        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email_user, self.email_password)
            return {
                "status": "success",
                "message": "Email connection successful"
            }
        except Exception as e:
            return {
                "status": "failed",
                "message": f"Email connection failed: {str(e)}"
            }

    async def send_test_intelligent_email(self, recipient: str, test_tender_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Sends a test email (for debugging/validation) using Agent 3 for composition,
        to a single recipient address and logs the attempt (success or failure) to the DB.
        Intended for system administrators and development validation.

        Args:
            recipient: Email address to send the test mail to
            test_tender_data: Optionally override the dummy tender content

        Returns:
            Dict summarizing result and preview of composed content
        """
        try:
            from datetime import datetime

            # Prepare canned or provided test tender data
            if not test_tender_data:
                test_tender_data = {
                    "title": "Test Screening Opportunity - Rural Productive Use of Energy",
                    "url": "https://example.com/test-screening-opportunity",
                    "category": "screening_opportunities",
                    "description": "Test opportunity aligned to the 3-step screening checklist workflow.",
                    "matched_keywords": ["off-grid energy", "PUE", "SMEs", "Ethiopia"],
                    "screening": {
                        "step1": {
                            "mission_alignment": True,
                            "sector_relevance": True,
                            "activity_fit": True,
                            "geographic_fit": True,
                            "eligibility_quick_check": True,
                        },
                        "yes_count": 5,
                        "passes_filter": True,
                        "step2": {
                            "opportunity_characteristics": ["implementation_heavy"],
                            "strategic_signals": ["private_sector_focused"],
                            "potential_concerns": [],
                        },
                        "step3": {
                            "title": "Test Screening Opportunity - Rural Productive Use of Energy",
                            "source": "Internal test source",
                            "country": "Ethiopia",
                            "type": "consultancy",
                            "deadline": "2026-06-30",
                            "estimated_budget": "USD 50,000 - 100,000",
                            "link": "https://example.com/test-screening-opportunity",
                        },
                    },
                }

            # Sample additional details, as Agent 3 expects rich structure
            test_detailed_info = {
                "detailed_title": "Rural Productive Use of Energy Support for SMEs",
                "detailed_description": "Implementation-focused assignment to support SMEs with productive use of energy interventions, market systems facilitation, and partner coordination.",
                "requirements": "Experience in SME support, private sector development, market systems, and energy access programs",
                "deadline": "2026-06-30",
                "tender_value": "USD 50,000 - 100,000",
                'contact_info': {
                    "organization": "Precise Test Programs",
                    "contact_person": "Screening Test Contact",
                    "email": "test@example.com",
                    "phone": "+251-11-000-0000",
                }
            }

            # Compose the actual AI email content using Agent 3
            from app.agents.agent3 import EmailComposerAgent
            agent3 = EmailComposerAgent()
            email_content = await agent3.compose_tender_email(
                tender_data=test_tender_data,
                detailed_info=test_detailed_info,
                team_category=test_tender_data['category']
            )

            # If Agent 3 fails (e.g., OpenAI error), report clearly to user
            if not email_content:
                return {
                    'status': 'failed',
                    'message': 'Agent 3 failed to compose test email content. Check OPENAI settings and agent logs.'
                }

            subject = email_content.get('subject', 'Tender Notification')
            html_body = email_content.get('html_body', '<p>No HTML content generated by Agent 3.</p>')
            priority = email_content.get('priority', 'Medium')

            # Assemble a test mail including test warning and metadata banner
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"[TEST] {subject}"
            msg['From'] = self.email_user
            msg['To'] = recipient
            test_html = f"""
            <div style="background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 10px; margin: 10px 0; border-radius: 5px;">
                <strong>🧪 TEST EMAIL</strong> - This is a test of the Agent 3 intelligent email composition system using database configuration.
            </div>
            {html_body}
            <div style="background-color: #f8f9fa; padding: 10px; margin: 10px 0; border-radius: 5px; font-size: 12px; color: #666;">
                <strong>Test Metadata:</strong><br>
                Generated by: Agent 3 Email Composer<br>
                Test Time: {datetime.utcnow().isoformat()}<br>
                System: {settings.APP_NAME} v3.0 with Database Integration
            </div>
            """
            html_part = MIMEText(test_html, 'html', 'utf-8')
            msg.attach(html_part)

            # Perform SMTP send
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email_user, self.email_password)
                server.send_message(msg)

            # Log the test attempt (success) to database
            db = SessionLocal()
            try:
                self.email_repo.log_email_notification(
                    db=db,
                    recipient_email=recipient,
                    email_type='test',
                    team_category=test_tender_data['category'],
                    subject=f"[TEST] {subject}",
                    status='sent'
                )
            finally:
                db.close()

            return {
                'status': 'success',
                'message': f'Test intelligent email sent successfully to {recipient} using database configuration',
                'email_content_preview': {
                    'subject': subject,
                    'priority': priority,
                    'summary': email_content.get('summary', 'Test email summary')
                }
            }
        except Exception as e:
            # Log the test mail failure to the DB
            db = SessionLocal()
            try:
                self.email_repo.log_email_notification(
                    db=db,
                    recipient_email=recipient,
                    email_type='test',
                    team_category='test',
                    subject='Test Email (Failed)',
                    status='failed',
                    error_message=str(e)
                )
            finally:
                db.close()

            return {
                'status': 'failed',
                'message': f'Failed to send test intelligent email: {str(e)}'
            }

# Re-export the class as EmailService for compatibility with previous code base
EmailService = EnhancedEmailService

# ---------------------------------------------------------------------------------
# FILE & CLASS STRUCTURE - DETAILED COMMENTS AND EXPLANATION
# ---------------------------------------------------------------------------------
#
# This file implements the email notification logic for the Tender Monitoring system.
#
# Main responsibilities:
#   - Uses database-stored recipient emails (per team/category) and notification preferences
#   - Composes and sends intelligent notification emails via SMTP for new tender opportunities
#   - Integrates with Agent 3 (AI email composer) where possible to generate enriched HTML content
#   - Provides a fallback notification mechanism if AI composition fails or is unavailable
#   - Tracks/logs all email attempts and failures to the database for audit trail and debugging
#
# Core classes and functions:
#   - EnhancedEmailService: Main service class encapsulating the notification process
#     - __init__: Loads SMTP settings and sets up the email repository
#     - send_intelligent_notifications: Entry point for batch-sending AI-composed notifications
#     - _send_single_intelligent_email_db: Handles a single AI-composed notification per tender/category
#     - send_fallback_notifications: Sends a simple, non-AI notification when enhanced composition is not available
#     - _create_fallback_tender_email: Utility for making a basic HTML notification for a set of tenders
#     - test_email_connection: Tests login and connection for configured SMTP credentials
#     - send_test_intelligent_email: Sends a test notification, useful for admin/system tests
#
# Techniques and architecture:
#   - All recipient addresses are fetched from the database using category/team as key
#   - Email send logic is robust to partial failures: if one recipient fails, others can still receive
#   - Each send (success/failure) is committed to a database notification log for traceability
#   - Fallback logic ensures admins/users are notified even if the AI-based system fails
#   - Detailed logging (both via logger and DB) to ease troubleshooting in production
#   - SMTP connection is established and torn down for each email (smaller loads), which is simple,
#     but could be adjusted for higher scale by connection pooling, async SMTP clients, or similar
#
# Requirements:
#   - app.core.config.settings must provide SMTP credentials and details
#   - app.repositories.email_settings_repository.EmailSettingsRepository provides methods
#     to get recipient emails, preferences, and log email sends/failures
#   - app.agents.agent3.EmailComposerAgent expected to implement compose_tender_email (async)
#
# File exposes: EnhancedEmailService (as EmailService) for app-wide use.
#
# ---------------------------------------------------------------------------------