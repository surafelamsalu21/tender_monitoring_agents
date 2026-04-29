import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict
from config import Config
from models import Tender
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        self.smtp_server = Config.SMTP_SERVER
        self.smtp_port = Config.SMTP_PORT
        self.email_user = Config.EMAIL_USER
        self.email_password = Config.EMAIL_PASSWORD
    
    def create_tender_email(self, tenders: List[Tender], category: str) -> str:
        """Create HTML email content for tenders"""
        team_name = "ESG Team" if category == "esg" else "Credit Rating Team"
        
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
            </div>
        """
        
        for tender in tenders:
            tender_date = tender.tender_date.strftime("%Y-%m-%d") if tender.tender_date else "Date not specified"
            
            html_content += f"""
            <div class="tender">
                <div class="tender-title">{tender.title}</div>
                <div style="margin: 5px 0;">
                    <span class="tender-category">{tender.category.upper()}</span>
                    <span class="tender-date">Date: {tender_date}</span>
                </div>
                <div class="tender-description">
                    {tender.description[:500]}{'...' if len(tender.description) > 500 else ''}
                </div>
                <div>
                    <a href="{tender.url}" class="tender-link">View Full Tender →</a>
                </div>
            </div>
            """
        
        html_content += """
            <div class="footer">
                <p>This is an automated notification from the Tender Monitoring System.</p>
                <p>If you no longer wish to receive these notifications, please contact your administrator.</p>
            </div>
        </body>
        </html>
        """
        
        return html_content
    
    def send_tender_notifications(self, tenders: List[Tender], category: str) -> bool:
        """Send email notifications for new tenders"""
        try:
            if not tenders:
                logger.info(f"No tenders to notify for category: {category}")
                return True
            
            # Determine recipient email
            if category == "esg":
                recipient_email = Config.ESG_TEAM_EMAIL
                subject = f"New ESG Tenders - {len(tenders)} Found"
            elif category == "credit_rating":
                recipient_email = Config.CREDIT_RATING_TEAM_EMAIL
                subject = f"New Credit Rating Tenders - {len(tenders)} Found"
            else:
                logger.warning(f"Unknown category: {category}")
                return False
            
            if not recipient_email:
                logger.warning(f"No email configured for category: {category}")
                return False
            
            # Create email
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.email_user
            msg['To'] = recipient_email
            
            # Create HTML content
            html_content = self.create_tender_email(tenders, category)
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email_user, self.email_password)
                server.send_message(msg)
            
            logger.info(f"Email sent successfully to {recipient_email} for {len(tenders)} {category} tenders")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email for category {category}: {e}")
            return False
    
    def send_test_email(self, recipient: str) -> bool:
        """Send a test email to verify email configuration"""
        try:
            msg = MIMEMultipart()
            msg['Subject'] = "Tender Agent Test Email"
            msg['From'] = self.email_user
            msg['To'] = recipient
            
            body = """
            <html>
            <body>
                <h2>Tender Agent Test Email</h2>
                <p>This is a test email from the Tender Monitoring System.</p>
                <p>If you received this email, the email configuration is working correctly.</p>
                <p>Timestamp: {}</p>
            </body>
            </html>
            """.format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            
            html_part = MIMEText(body, 'html')
            msg.attach(html_part)
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email_user, self.email_password)
                server.send_message(msg)
            
            logger.info(f"Test email sent successfully to {recipient}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send test email: {e}")
            return False

def test_email_service():
    """Test email service"""
    email_service = EmailService()
    
    # Create mock tender data
    from datetime import datetime
    
    class MockTender:
        def __init__(self, title, url, category, description, tender_date=None):
            self.title = title
            self.url = url
            self.category = category
            self.description = description
            self.tender_date = tender_date or datetime.now()
    
    mock_tenders = [
        MockTender(
            "Environmental Impact Assessment Tender",
            "https://example.com/tender1",
            "esg",
            "This tender is for conducting an environmental impact assessment for a new construction project. The assessment should cover air quality, water resources, and biodiversity impacts."
        ),
        MockTender(
            "Credit Rating Services Procurement",
            "https://example.com/tender2", 
            "credit_rating",
            "Procurement of credit rating services for corporate bond issuance. The service provider should have international recognition and experience in emerging markets."
        )
    ]
    
    print("Testing email service...")
    
    # Test ESG email
    if Config.ESG_TEAM_EMAIL:
        result = email_service.send_tender_notifications([mock_tenders[0]], "esg")
        print(f"ESG email test: {'✓ Success' if result else '✗ Failed'}")
    else:
        print("ESG email test: ⚠ No ESG_TEAM_EMAIL configured")
    
    # Test Credit Rating email
    if Config.CREDIT_RATING_TEAM_EMAIL:
        result = email_service.send_tender_notifications([mock_tenders[1]], "credit_rating")
        print(f"Credit Rating email test: {'✓ Success' if result else '✗ Failed'}")
    else:
        print("Credit Rating email test: ⚠ No CREDIT_RATING_TEAM_EMAIL configured")

if __name__ == "__main__":
    from datetime import datetime
    test_email_service()
