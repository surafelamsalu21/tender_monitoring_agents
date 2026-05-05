"""
Database initialization: default monitored page, checklist-aligned keywords, email settings.

Add more screening phrases anytime in DEFAULT_SCREENING_KEYWORDS (dedupe by phrase+category is handled by _ensure_keyword).
"""
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import Keyword
from app.models.email_settings import EmailNotificationSettings
from app.repositories.page_repository import PageRepository
from app.repositories.keyword_repository import KeywordRepository
from app.repositories.email_settings_repository import EmailSettingsRepository

logger = logging.getLogger(__name__)


# Categories match Keyword Manager (sector / activity_fit / geography / source_tag).
# Aligned with Precise screening checklist — extend lists below as you refine real notices.
DEFAULT_SCREENING_KEYWORDS: dict[str, list[str]] = {
    # Step 1.2 sector relevance (+ thematic overlap with mission / cross-cutting finance-climate-SMEs)
    "sector": [
        "off-grid energy",
        "off-grid solar",
        "standalone solar",
        "solar home systems",
        "mini-grid",
        "micro-grid",
        "decentralized renewable energy",
        "distributed generation",
        "rural electrification",
        "productive use of energy",
        "PUE (productive use of energy)",
        "energy access",
        "agriculture",
        "agribusiness",
        "agrifood",
        "agricultural development",
        "farm productivity",
        "food systems",
        "health electrification",
        "health facility electrification",
        "cold chain",
        "climate finance",
        "green finance",
        "blended finance",
        "rural finance",
        "SME finance (small and medium enterprise)",
        "MSME finance (micro, small and medium enterprise)",
        "financial inclusion",
        "cross-cutting development",
        "climate-smart investment",
    ],
    # Step 1.3 activity fit (+ mission/eligibility-style phrases notices often use)
    "activity_fit": [
        "economic development",
        "enterprise development",
        "industrial development",
        "private sector development",
        "SME (small and medium enterprise)",
        "MSME (micro, small and medium enterprise)",
        "business development services",
        "BDS (business development services)",
        "technical assistance",
        "access to finance",
        "value chain",
        "market systems",
        "market facilitation",
        "climate-smart agriculture",
        "regenerative agriculture",
        "sustainable agriculture",
        "research",
        "survey",
        "baseline survey",
        "feasibility study",
        "studies",
        "assessment",
        "evaluation",
        "capacity building",
        "training",
        "training of trainers",
        "ToT (training of trainers)",
        "policy dialogue",
        "stakeholder engagement",
        "multi-stakeholder",
        "public-private partnership",
        "PPP (public-private partnership)",
        "for-profit eligible",
        "consulting firm",
        "international consultants",
        "eligibility unclear",
        "not restricted to NGOs",
    ],
    # Step 1.4 geographic fit
    "geography": [
        "Ethiopia",
        "East Africa",
        "Horn of Africa",
        "EAC (East African Community)",
        "IGAD (Intergovernmental Authority on Development)",
        "Kenya",
        "Uganda",
        "Tanzania",
        "Rwanda",
        "Burundi",
        "Somalia",
        "Djibouti",
        "Eritrea",
        "South Sudan",
        "Sudan",
    ],
    # Step 3 source / donor / platform names (short labels + recognizable URL fragments)
    "source_tag": [
        "LinkedIn",
        "RFX Now (procurement alerts)",
        "World Bank",
        "WB procurement (World Bank)",
        "wbgeprocure",
        "EU Funding",
        "Funding & Tenders Portal",
        "EU Portal",
        "europa.eu",
        "USAID (United States Agency for International Development)",
        "USAID procurement (United States Agency for International Development)",
        "Gates Foundation",
        "BMGF (Bill & Melinda Gates Foundation)",
        "AGRA (Alliance for a Green Revolution in Africa)",
        "Merkato",
        "Merkato.com",
    ],
}


def _ensure_keyword(db, keyword_repo: KeywordRepository, term: str, category: str) -> None:
    existing = (
        db.query(Keyword)
        .filter(Keyword.keyword == term, Keyword.category == category)
        .first()
    )
    if existing:
        return
    keyword_repo.create_keyword(
        db,
        keyword=term,
        category=category,
        description=f"Precise screening keyword ({category}): {term}",
    )


def ensure_default_screening_keywords(db: Optional[Session] = None) -> None:
    """
    Insert any missing DEFAULT_SCREENING_KEYWORDS rows (idempotent).

    Pass an existing session when called from initialize_default_data; otherwise opens its own.
    """
    close_after = db is None
    if db is None:
        db = SessionLocal()
    try:
        keyword_repo = KeywordRepository()
        for category, terms in DEFAULT_SCREENING_KEYWORDS.items():
            for term in terms:
                t = term.strip()
                if not t:
                    continue
                _ensure_keyword(db, keyword_repo, t, category)
        logger.info(
            "Ensured Precise screening keywords (%s categories)",
            len(DEFAULT_SCREENING_KEYWORDS),
        )
    finally:
        if close_after:
            db.close()


def initialize_default_data():
    """Initialize default pages, keywords, and email settings"""
    db = SessionLocal()
    try:
        page_repo = PageRepository()
        email_repo = EmailSettingsRepository()
        
        # Initialize default monitored page
        existing_page = page_repo.get_page_by_url(db, "https://corp.uzairways.com/ru/press-center/tenders")
        if not existing_page:
            page_repo.create_page(
                db,
                name="Uzbekistan Airways Tenders",
                url="https://corp.uzairways.com/ru/press-center/tenders",
                description="Official tender page for Uzbekistan Airways",
                crawl_frequency_hours=3
            )
            logger.info("Created default monitored page: Uzbekistan Airways")

        ensure_default_screening_keywords(db)

        # Email notification settings (unified screening recipients + preferences)
        logger.info("Initializing email settings...")
        email_repo.migrate_legacy_email_notification_settings(db)

        existing_opportunity = db.query(EmailNotificationSettings).filter(
            EmailNotificationSettings.setting_key == "opportunity_emails"
        ).first()
        existing_prefs = db.query(EmailNotificationSettings).filter(
            EmailNotificationSettings.setting_key == "preferences"
        ).first()

        if not existing_opportunity:
            db.add(
                EmailNotificationSettings(
                    setting_key="opportunity_emails",
                    setting_value=[],
                    description="Recipients for opportunity screening notifications",
                )
            )
            logger.info("Created opportunity_emails notification list")

        if not existing_prefs:
            db.add(
                EmailNotificationSettings(
                    setting_key="preferences",
                    setting_value={
                        "send_for_new_tenders": True,
                        "send_daily_summary": True,
                        "send_urgent_notifications": True,
                    },
                    description="Email notification preferences and settings",
                )
            )
            logger.info("Created notification preferences")

        if not existing_opportunity or not existing_prefs:
            db.commit()
            logger.info("Email settings initialized successfully")
        else:
            logger.info("Email settings already exist")
        
        logger.info("Default data initialization completed")
        
    except Exception as e:
        logger.error(f"Error initializing default data: {e}")
        db.rollback()
        raise
    finally:
        db.close()

def initialize_email_settings_only():
    """Initialize only email settings (helper function)"""
    db = SessionLocal()
    try:
        logger.info("Initializing email settings...")
        email_repo = EmailSettingsRepository()
        email_repo.migrate_legacy_email_notification_settings(db)

        existing_opportunity = db.query(EmailNotificationSettings).filter(
            EmailNotificationSettings.setting_key == "opportunity_emails"
        ).first()
        existing_prefs = db.query(EmailNotificationSettings).filter(
            EmailNotificationSettings.setting_key == "preferences"
        ).first()

        created = False
        if not existing_opportunity:
            db.add(
                EmailNotificationSettings(
                    setting_key="opportunity_emails",
                    setting_value=[],
                    description="Recipients for opportunity screening notifications",
                )
            )
            created = True
        if not existing_prefs:
            db.add(
                EmailNotificationSettings(
                    setting_key="preferences",
                    setting_value={
                        "send_for_new_tenders": True,
                        "send_daily_summary": True,
                        "send_urgent_notifications": True,
                    },
                    description="Email notification preferences and settings",
                )
            )
            created = True

        if created:
            db.commit()
            logger.info("✅ Email settings initialized successfully")
        else:
            logger.info("✅ Email settings already exist")
        return True

    except Exception as e:
        logger.error(f"❌ Error initializing email settings: {e}")
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    # Test email settings initialization
    logging.basicConfig(level=logging.INFO)
    
    print("Initializing email settings...")
    success = initialize_email_settings_only()
    
    if success:
        print("✅ Email settings initialized successfully!")
    else:
        print("❌ Failed to initialize email settings")