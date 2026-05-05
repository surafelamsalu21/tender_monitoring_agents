#!/usr/bin/env python3
"""
Remove ALL monitored pages and ALL tenders (basic + detailed + crawl logs + tender-keyword links).

Does NOT touch: users, keywords, email_notification_* settings (only optional log cleanup).

After running, use the Pages UI to add your example URL, then trigger extraction.

Examples (repo root, venv active):

  python scripts/reset_pages_and_tenders.py --dry-run
  python scripts/reset_pages_and_tenders.py --yes
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reset_pages_and_tenders")


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete all monitored pages and tenders.")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually delete (required to modify the database).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print row counts only; do not delete.",
    )
    parser.add_argument(
        "--purge-email-notification-logs",
        action="store_true",
        help="Also truncate email_notification_logs (optional audit table).",
    )
    args = parser.parse_args()

    import app.models  # noqa: F401 — register models

    from sqlalchemy import delete, func, select

    from app.core.database import SessionLocal
    from app.models import CrawlLog, MonitoredPage
    from app.models.email_settings import EmailNotificationLog
    from app.models.tender import DetailedTender, Tender, tender_keywords

    db = SessionLocal()
    try:
        n_detailed = db.query(DetailedTender).count()
        n_links = db.execute(
            select(func.count()).select_from(tender_keywords)
        ).scalar() or 0
        n_tenders = db.query(Tender).count()
        n_logs = db.query(CrawlLog).count()
        n_pages = db.query(MonitoredPage).count()
        n_email_logs = db.query(EmailNotificationLog).count()

        logger.info(
            "Current counts: pages=%s, tenders=%s, detailed_tenders=%s, "
            "crawl_logs=%s, tender_keyword_links=%s, email_notification_logs=%s",
            n_pages,
            n_tenders,
            n_detailed,
            n_logs,
            n_links,
            n_email_logs,
        )

        if args.dry_run:
            logger.info("--dry-run: no changes.")
            return

        if not args.yes:
            logger.warning("Refusing to delete without --yes (use --dry-run to preview counts).")
            sys.exit(1)

        db.query(DetailedTender).delete(synchronize_session=False)
        db.execute(delete(tender_keywords))
        db.query(Tender).delete(synchronize_session=False)
        db.query(CrawlLog).delete(synchronize_session=False)
        db.query(MonitoredPage).delete(synchronize_session=False)
        if args.purge_email_notification_logs:
            db.query(EmailNotificationLog).delete(synchronize_session=False)
        db.commit()

        logger.info(
            "Done. Removed pages, tenders, detailed rows, crawl logs, and keyword links."
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
