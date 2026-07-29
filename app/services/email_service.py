"""
Enhanced Email Notification Service with Database Integration
Updated to use email addresses from database and log all email activities
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Any, Optional
from html import escape
from datetime import datetime, timedelta
import logging
import json
import hashlib
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.email_settings import EmailNotificationSettings
from app.models.tender import Tender
from app.repositories.email_settings_repository import EmailSettingsRepository
from app.utils.tender_expiry import partition_notifiable

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

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _retry_setting_key() -> str:
        return "pending_email_retries"

    @staticmethod
    def _utcnow_iso() -> str:
        return datetime.utcnow().isoformat()

    def _retry_interval_minutes(self) -> int:
        return max(1, int(getattr(settings, "EMAIL_RETRY_INTERVAL_MINUTES", 30)))

    def _retry_max_attempts(self) -> int:
        return max(1, int(getattr(settings, "EMAIL_RETRY_MAX_ATTEMPTS", 48)))

    def _build_retry_key(
        self,
        recipient_email: str,
        team_category: str,
        subject: str,
        tender_ids: List[int],
    ) -> str:
        payload = "|".join(
            [
                recipient_email.strip().lower(),
                team_category.strip().lower(),
                subject.strip(),
                ",".join(str(tid) for tid in sorted(set(tender_ids))),
            ]
        )
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    def _load_pending_retries(self, db: Session) -> List[Dict[str, Any]]:
        row = (
            db.query(EmailNotificationSettings)
            .filter(EmailNotificationSettings.setting_key == self._retry_setting_key())
            .first()
        )
        if not row or not row.setting_value:
            return []
        if isinstance(row.setting_value, list):
            return list(row.setting_value)
        return []

    def _save_pending_retries(self, db: Session, items: List[Dict[str, Any]]) -> None:
        row = (
            db.query(EmailNotificationSettings)
            .filter(EmailNotificationSettings.setting_key == self._retry_setting_key())
            .first()
        )
        if row:
            row.setting_value = items
            row.updated_at = datetime.utcnow()
        else:
            db.add(
                EmailNotificationSettings(
                    setting_key=self._retry_setting_key(),
                    setting_value=items,
                    description=(
                        "Queued retry payloads for failed recipient sends "
                        "(per recipient, digest subject, and tender set)."
                    ),
                )
            )
        db.commit()

    def _parse_iso_datetime(self, raw: Any) -> Optional[datetime]:
        if not raw:
            return None
        text = str(raw).strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return None

    def _queue_failed_recipient_retry(
        self,
        db: Session,
        *,
        recipient_email: str,
        team_category: str,
        email_content: Dict[str, Any],
        tender_ids: List[int],
        tender_title: str,
        error_message: str,
    ) -> None:
        if not bool(getattr(settings, "EMAIL_RETRY_ENABLED", True)):
            return

        subject = str(email_content.get("subject") or "Tender Notification")
        retry_key = self._build_retry_key(
            recipient_email=recipient_email,
            team_category=team_category,
            subject=subject,
            tender_ids=tender_ids,
        )

        now = datetime.utcnow()
        next_attempt = now + timedelta(minutes=self._retry_interval_minutes())
        queue = self._load_pending_retries(db)
        payload = {
            "retry_key": retry_key,
            "recipient_email": recipient_email,
            "team_category": team_category,
            "subject": subject,
            "html_body": str(email_content.get("html_body") or ""),
            "priority": str(email_content.get("priority") or "Medium"),
            "tender_ids": sorted(set(int(t) for t in tender_ids if str(t).isdigit())),
            "tender_title": tender_title[:200],
            "attempts": 0,
            "max_attempts": self._retry_max_attempts(),
            "created_at": self._utcnow_iso(),
            "last_error": error_message[:1000],
            "last_attempt_at": self._utcnow_iso(),
            "next_attempt_at": next_attempt.isoformat(),
        }

        replaced = False
        for idx, item in enumerate(queue):
            if item.get("retry_key") == retry_key:
                payload["attempts"] = int(item.get("attempts") or 0)
                payload["created_at"] = str(item.get("created_at") or payload["created_at"])
                queue[idx] = payload
                replaced = True
                break
        if not replaced:
            queue.append(payload)

        self._save_pending_retries(db, queue)
        logger.info(
            "Queued retry for failed recipient %s (next attempt at %s)",
            recipient_email,
            payload["next_attempt_at"],
        )

    def _remove_retry_item(self, db: Session, retry_key: str) -> None:
        queue = self._load_pending_retries(db)
        new_queue = [item for item in queue if item.get("retry_key") != retry_key]
        if len(new_queue) != len(queue):
            self._save_pending_retries(db, new_queue)

    def _merge_to_single_digest_composition(
        self,
        email_compositions: List[Dict[str, Any]],
        db: Session,
    ) -> List[Dict[str, Any]]:
        """
        Collapse multiple compositions into one digest composition so each run sends a
        single email containing all tenders across all sources/pages.
        """
        first = email_compositions[0]
        first_content = first.get("email_content") or {}
        team_category = first_content.get("team_category") or "screening_opportunities"

        tender_ids: List[int] = []
        fallback_items: List[Dict[str, str]] = []

        for composition in email_compositions:
            tender_data = composition.get("tender_data") or {}
            email_content = composition.get("email_content") or {}

            one_tid = self._safe_int(email_content.get("tender_id"))
            if one_tid is None:
                one_tid = self._safe_int(tender_data.get("id"))
            if one_tid is not None:
                tender_ids.append(one_tid)

            many_ids = tender_data.get("tender_ids") or email_content.get("tender_ids") or []
            if isinstance(many_ids, list):
                for raw_tid in many_ids:
                    parsed_tid = self._safe_int(raw_tid)
                    if parsed_tid is not None:
                        tender_ids.append(parsed_tid)

        unique_tender_ids = sorted(set(tender_ids))
        db_items: List[Dict[str, str]] = []
        suppressed_expired = 0

        if unique_tender_ids:
            rows = db.query(Tender).filter(Tender.id.in_(unique_tender_ids)).all()
            # Last line of defence: every digest funnels through here, so a closed
            # opportunity cannot reach a recipient no matter which caller composed it.
            rows, expired_rows = partition_notifiable(rows)
            suppressed_expired = len(expired_rows)
            if suppressed_expired:
                logger.info(
                    "Digest body: suppressed %s closed opportunity/ies", suppressed_expired
                )
            by_id = {r.id: r for r in rows}
            unique_tender_ids = [tid for tid in unique_tender_ids if tid in by_id]
            for tid in unique_tender_ids:
                row = by_id.get(tid)
                if not row:
                    continue
                db_items.append(
                    {
                        "title": str(row.title or "Untitled Tender"),
                        "deadline": row.tender_date.strftime("%Y-%m-%d") if row.tender_date else "Not specified",
                        "source": str(row.source or "N/A"),
                        "country": str(row.country or "N/A"),
                        "opportunity_type": str(row.opportunity_type or "N/A"),
                        "url": str(row.url or "#"),
                    }
                )

        # Fallback only when DB details are unavailable. Skipped when rows existed
        # but were all closed, otherwise the expiry gate above would be undone by
        # rebuilding the same tenders from the compositions.
        if not db_items and not suppressed_expired:
            for composition in email_compositions:
                tender_data = composition.get("tender_data") or {}
                fallback_items.append(
                    {
                        "title": str(tender_data.get("title") or "Untitled Tender"),
                        "deadline": str(tender_data.get("date") or "Not specified"),
                        "source": str((tender_data.get("screening") or {}).get("step3", {}).get("source") or "N/A"),
                        "country": str((tender_data.get("screening") or {}).get("step3", {}).get("country") or "N/A"),
                        "opportunity_type": str((tender_data.get("screening") or {}).get("step3", {}).get("type") or "N/A"),
                        "url": str(tender_data.get("url") or "#"),
                    }
                )

        all_items = db_items or fallback_items
        if not all_items:
            logger.info("Digest body: nothing open to send, skipping the digest email")
            return []

        total = len(all_items)
        list_rows = []
        for index, item in enumerate(all_items, 1):
            list_rows.append(
                f"""
                <tr>
                  <td style="padding:10px 8px; border-bottom:1px solid #e5e7eb; vertical-align:top;">{index}</td>
                  <td style="padding:10px 8px; border-bottom:1px solid #e5e7eb; vertical-align:top; max-width:420px;">
                    <div style="font-weight:600; color:#111827;">{escape(item["title"])}</div>
                    <div style="margin-top:4px; font-size:12px; color:#4b5563;">
                      Source: {escape(item["source"])} | Country: {escape(item["country"])} | Type: {escape(item["opportunity_type"])}
                    </div>
                  </td>
                  <td style="padding:10px 8px; border-bottom:1px solid #e5e7eb; vertical-align:top;">{escape(item["deadline"])}</td>
                  <td style="padding:10px 8px; border-bottom:1px solid #e5e7eb; vertical-align:top;">
                    <a href="{escape(item['url'], quote=True)}" style="color:#2563eb; text-decoration:none;">Open</a>
                  </td>
                </tr>
                """
            )

        subject = f"New SCREENING OPPORTUNITIES Tenders - {total} Opportunities Found"
        html_body = f"""
        <html>
          <body style="font-family: Arial, sans-serif; margin: 20px;">
            <div style="background: #f8f9fa; border-radius: 8px; padding: 16px;">
              <h2 style="margin-top: 0;">New Tender Opportunities Digest</h2>
              <p style="margin-bottom: 4px;">
                We found <strong>{total}</strong> new tender(s) across monitored sources in this cycle.
              </p>
              <p style="color: #666; margin-top: 0;">
                All tenders are listed below with key information.
              </p>
            </div>
            <table style="width:100%; border-collapse:collapse; margin-top:14px; font-size:14px;">
              <thead>
                <tr style="background:#f3f4f6; color:#111827; text-align:left;">
                  <th style="padding:10px 8px; border-bottom:1px solid #d1d5db; width:36px;">#</th>
                  <th style="padding:10px 8px; border-bottom:1px solid #d1d5db;">Tender Name</th>
                  <th style="padding:10px 8px; border-bottom:1px solid #d1d5db; white-space:nowrap;">Deadline</th>
                  <th style="padding:10px 8px; border-bottom:1px solid #d1d5db;">Link</th>
                </tr>
              </thead>
              <tbody>
                {''.join(list_rows)}
              </tbody>
            </table>
            <div style="margin-top: 22px; color: #666; font-size: 12px;">
              Automated notification from {escape(settings.APP_NAME)}
            </div>
          </body>
        </html>
        """

        merged = {
            "tender_data": {
                "title": "Multiple Tenders Digest",
                "count": total,
                "tender_ids": unique_tender_ids,
            },
            "email_content": {
                "subject": subject,
                "priority": "Medium",
                "summary": f"Consolidated digest with {total} opportunities.",
                "html_body": html_body,
                "generated_at": datetime.utcnow().isoformat(),
                "team_category": team_category,
                "agent_version": "3.0-single-digest",
                "tender_ids": unique_tender_ids,
            },
            "composition_status": "success",
            "email_type": "digest",
        }
        logger.info(
            "Merged %s intelligent email compositions into one digest composition",
            len(email_compositions),
        )
        return [merged]

    def _send_html_email(
        self,
        *,
        recipient_email: str,
        subject: str,
        html_body: str,
        priority: str,
    ) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.email_user
        msg["To"] = recipient_email
        if priority == "High":
            msg["X-Priority"] = "1"
            msg["Importance"] = "high"
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
            server.starttls()
            server.login(self.email_user, self.email_password)
            refused = server.send_message(msg)
            if refused:
                raise RuntimeError(f"SMTP refused recipients: {refused}")

    async def retry_failed_notifications(self) -> Dict[str, Any]:
        """
        Retry queued recipient-level email failures (e.g. transient network/SMTP issues).
        Retries only due items and only for recipients that previously failed.
        """
        summary = {"due": 0, "retried": 0, "sent": 0, "failed": 0, "dropped": 0}
        if not bool(getattr(settings, "EMAIL_RETRY_ENABLED", True)):
            return summary

        db = SessionLocal()
        try:
            queue = self._load_pending_retries(db)
            if not queue:
                return summary

            now = datetime.utcnow()
            preferences = self.email_repo.get_notification_preferences(db)
            if not preferences.get("send_for_new_tenders", True):
                logger.info("Skipping retry queue: send_for_new_tenders is disabled")
                return summary

            remaining: List[Dict[str, Any]] = []
            for item in queue:
                next_due = self._parse_iso_datetime(item.get("next_attempt_at"))
                if next_due and next_due > now:
                    remaining.append(item)
                    continue

                summary["due"] += 1
                attempts = int(item.get("attempts") or 0)
                max_attempts = int(item.get("max_attempts") or self._retry_max_attempts())
                recipient = str(item.get("recipient_email") or "").strip()
                subject = str(item.get("subject") or "Tender Notification")
                team_category = str(item.get("team_category") or "screening_opportunities")
                priority = str(item.get("priority") or "Medium")
                html_body = str(item.get("html_body") or "")

                if not recipient or not html_body:
                    summary["dropped"] += 1
                    logger.warning("Dropping malformed retry item: %s", item.get("retry_key"))
                    continue

                try:
                    summary["retried"] += 1
                    self._send_html_email(
                        recipient_email=recipient,
                        subject=subject,
                        html_body=html_body,
                        priority=priority,
                    )
                    self.email_repo.log_email_notification(
                        db=db,
                        recipient_email=recipient,
                        email_type="retry_new_tender",
                        team_category=team_category,
                        subject=subject,
                        status="sent",
                        tender_id=None,
                    )
                    summary["sent"] += 1
                    logger.info("Retry succeeded for %s", recipient)
                except Exception as exc:
                    attempts += 1
                    item["attempts"] = attempts
                    item["last_error"] = str(exc)[:1000]
                    item["last_attempt_at"] = self._utcnow_iso()
                    item["next_attempt_at"] = (
                        now + timedelta(minutes=self._retry_interval_minutes())
                    ).isoformat()
                    self.email_repo.log_email_notification(
                        db=db,
                        recipient_email=recipient,
                        email_type="retry_new_tender",
                        team_category=team_category,
                        subject=subject,
                        status="failed",
                        error_message=str(exc),
                        tender_id=None,
                    )
                    if attempts >= max_attempts:
                        summary["dropped"] += 1
                        logger.error(
                            "Dropping retry item after max attempts (%s): %s",
                            attempts,
                            recipient,
                        )
                    else:
                        remaining.append(item)
                        summary["failed"] += 1

            self._save_pending_retries(db, remaining)
            return summary
        finally:
            db.close()

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

            db = SessionLocal()
            try:
                # Business rule: one email per run containing all tenders.
                email_compositions = self._merge_to_single_digest_composition(email_compositions, db)
                logger.info(f"Sending {len(email_compositions)} intelligent email notifications using database emails...")

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
            ids_to_mark: List[int] = []
            one_tid = email_content.get("tender_id") or tender_data.get("id")
            if one_tid is not None:
                try:
                    ids_to_mark.append(int(one_tid))
                except (TypeError, ValueError):
                    logger.warning("Invalid tender_id in intelligent email composition: %r", one_tid)
            many_ids = tender_data.get("tender_ids") or email_content.get("tender_ids") or []
            if isinstance(many_ids, list):
                for raw in many_ids:
                    try:
                        ids_to_mark.append(int(raw))
                    except (TypeError, ValueError):
                        continue
            unique_ids = sorted(set(ids_to_mark))
            # Loop through recipients and send individual emails
            for recipient_email in recipient_emails:
                try:
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
                    self._send_html_email(
                        recipient_email=recipient_email,
                        subject=email_content['subject'],
                        html_body=html_content,
                        priority=email_content.get('priority', 'Medium'),
                    )

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
                    recipient_retry_key = self._build_retry_key(
                        recipient_email=recipient_email,
                        team_category=team_category,
                        subject=email_content.get("subject") or "Tender Notification",
                        tender_ids=unique_ids,
                    )
                    self._remove_retry_item(db, recipient_retry_key)
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
                    self._queue_failed_recipient_retry(
                        db,
                        recipient_email=recipient_email,
                        team_category=team_category,
                        email_content=email_content,
                        tender_ids=unique_ids,
                        tender_title=str(tender_data.get('title') or 'Tender'),
                        error_message=str(e),
                    )

            emails_sent = len(sent_details)
            success = emails_sent > 0

            if success:
                if unique_ids:
                    rows = db.query(Tender).filter(Tender.id.in_(unique_ids)).all()
                    for row in rows:
                        row.is_notified = True
                        row.updated_at = datetime.utcnow()
                    db.commit()

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

            tenders, expired_tenders = partition_notifiable(tenders)
            if expired_tenders:
                logger.info(
                    "Fallback email: suppressed %s closed opportunity/ies", len(expired_tenders)
                )
            if not tenders:
                logger.info(f"No open tenders left to notify for category: {category}")
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
                            refused = server.send_message(msg)
                            if refused:
                                raise RuntimeError(f"SMTP refused recipients: {refused}")

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
                refused = server.send_message(msg)
                if refused:
                    raise RuntimeError(f"SMTP refused recipients: {refused}")

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