"""
Manual re-run of Agent 2 (detail extraction) for tenders stuck without is_processed.
"""
import logging
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.agents.agent2 import TenderDetailAgent
from app.agents.agent3 import EmailComposerAgent
from app.repositories.tender_repository import TenderRepository
from app.services.email_service import EnhancedEmailService

logger = logging.getLogger(__name__)

_tender_repo = TenderRepository()


async def _notify_processed_recommended_unnotified(
    db: Session,
    tender_ids: List[int],
) -> Dict[str, Any]:
    """
    Compose+send notifications only for rows that are:
    - in tender_ids
    - passes_screening=True
    - is_processed=True
    - is_notified=False
    """
    if not tender_ids:
        return {"attempted": 0, "composed": 0, "sent": 0, "message": "No tender IDs"}

    candidates = []
    for tid in tender_ids:
        tender = _tender_repo.get_tender_by_id(db, tid)
        if not tender:
            continue
        if not bool(tender.passes_screening):
            continue
        if not bool(tender.is_processed):
            continue
        if bool(tender.is_notified):
            continue
        detailed = _tender_repo.get_detailed_tender_by_tender_id(db, tid)
        if not detailed:
            continue

        # Agent3 expects this contract from workflow/simple orchestrator.
        payload = _tender_repo.tender_to_agent2_basic_payload(tender)
        payload["detailed_info"] = {
            "detailed_title": detailed.detailed_title,
            "detailed_description": detailed.detailed_description,
            "requirements": detailed.requirements,
            "deadline": detailed.deadline.isoformat() if detailed.deadline else None,
            "tender_value": detailed.tender_value,
            "duration": detailed.duration,
            "contact_info": detailed.contact_info,
            "additional_details": detailed.additional_details,
            "processing_status": detailed.processing_status,
            "processed_at": detailed.processed_at.isoformat() if detailed.processed_at else None,
        }
        candidates.append(payload)

    if not candidates:
        return {
            "attempted": len(tender_ids),
            "composed": 0,
            "sent": 0,
            "message": "No newly processed recommended unnotified tenders",
        }

    agent3 = EmailComposerAgent()
    compositions = await agent3.compose_multiple_emails(
        candidates,
        "screening_opportunities",
    )
    if not compositions:
        return {
            "attempted": len(tender_ids),
            "composed": 0,
            "sent": 0,
            "message": "No email compositions created",
        }

    email_service = EnhancedEmailService()
    send_result = await email_service.send_intelligent_notifications(compositions)
    return {
        "attempted": len(tender_ids),
        "composed": len(compositions),
        "sent": int(send_result.get("sent_successfully", 0) or 0),
        "failed_sends": int(send_result.get("failed_sends", 0) or 0),
    }


async def retry_agent2_detail_for_tender(
    db: Session,
    tender_id: int,
    *,
    skip_date_validation: bool = False,
    send_notifications: bool = True,
) -> Dict[str, Any]:
    tender = _tender_repo.get_tender_by_id(db, tender_id)
    if not tender:
        return {"success": False, "error": "not_found", "message": "Tender not found"}
    if not (tender.url or "").strip():
        return {
            "success": False,
            "error": "no_url",
            "message": "Tender has no URL for extraction",
        }

    basic = _tender_repo.tender_to_agent2_basic_payload(tender)
    agent = TenderDetailAgent()
    results = await agent.process_multiple_tenders(
        [basic], skip_date_validation=skip_date_validation
    )
    if not results:
        return {
            "success": False,
            "error": "no_result",
            "message": "Agent 2 returned no result",
        }

    r = results[0]
    if r.get("processing_status") != "completed":
        di = r.get("detailed_info") or {}
        msg = (
            di.get("skip_reason")
            or di.get("error_message")
            or f"Extraction status: {r.get('processing_status')}"
        )
        return {
            "success": False,
            "error": r.get("processing_status") or "not_completed",
            "message": msg,
            "processing_status": r.get("processing_status"),
        }

    detailed = r.get("detailed_info")
    if not detailed:
        return {
            "success": False,
            "error": "no_detailed_info",
            "message": "Missing detailed_info from Agent 2",
        }

    try:
        saved = _tender_repo.save_detailed_tender(db, tender_id, detailed)
    except Exception as e:
        logger.exception("save_detailed_tender failed on retry for tender_id=%s", tender_id)
        return {"success": False, "error": "save_failed", "message": str(e)}

    notification_result: Dict[str, Any] = {
        "attempted": 0,
        "composed": 0,
        "sent": 0,
        "message": "Notification send disabled",
    }
    if send_notifications:
        try:
            notification_result = await _notify_processed_recommended_unnotified(
                db, [tender_id]
            )
        except Exception as exc:
            logger.exception("Single retry: notification step failed")
            notification_result = {
                "attempted": 1,
                "composed": 0,
                "sent": 0,
                "message": f"Notification step failed: {exc}",
            }

    return {
        "success": True,
        "tender_id": tender_id,
        "detailed_tender_id": saved.id if saved else None,
        "notification": notification_result,
    }


async def retry_pending_details_bulk(
    db: Session,
    *,
    limit: int = 20,
    only_passed_screening: bool = True,
    skip_date_validation: bool = False,
    send_notifications: bool = True,
) -> Dict[str, Any]:
    pending = _tender_repo.get_pending_detail_tenders(
        db,
        only_passed_screening=only_passed_screening,
        limit=limit,
    )
    outcomes: List[Dict[str, Any]] = []
    completed = 0
    successful_ids: List[int] = []
    for t in pending:
        one = await retry_agent2_detail_for_tender(
            db,
            t.id,
            skip_date_validation=skip_date_validation,
        )
        outcomes.append({"tender_id": t.id, **one})
        if one.get("success"):
            completed += 1
            successful_ids.append(t.id)

    notification_result: Dict[str, Any] = {
        "attempted": 0,
        "composed": 0,
        "sent": 0,
        "message": "Notification send disabled",
    }
    if send_notifications:
        try:
            notification_result = await _notify_processed_recommended_unnotified(
                db, successful_ids
            )
        except Exception as exc:
            logger.exception("Bulk retry: notification step failed")
            notification_result = {
                "attempted": len(successful_ids),
                "composed": 0,
                "sent": 0,
                "message": f"Notification step failed: {exc}",
            }

    return {
        "success": True,
        "attempted": len(pending),
        "completed": completed,
        "outcomes": outcomes,
        "notification": notification_result,
    }
