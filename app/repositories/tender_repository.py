"""
Enhanced Tender Repository with Keyword Tracking
"""
import json
import hashlib
import re
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, text
import logging

logger = logging.getLogger(__name__)

from app.models.tender import Tender, DetailedTender
from app.models.keyword import Keyword
from app.models.page import MonitoredPage

class TenderRepository:
    """Enhanced repository for tender database operations with keyword tracking"""

    @staticmethod
    def _normalize_url(value: Optional[str]) -> str:
        if not value:
            return ""
        return str(value).strip().rstrip("/")

    def _is_listing_page_url(self, db: Session, page_id: int, url: str) -> bool:
        """True when the row URL is just the monitored listing page, not a notice URL."""
        normalized = self._normalize_url(url)
        if not normalized:
            return False
        page = db.query(MonitoredPage.url).filter(MonitoredPage.id == page_id).first()
        if not page:
            return False
        return normalized == self._normalize_url(page[0])

    @staticmethod
    def _prefer_detail_url(existing_url: Optional[str], incoming_url: str) -> str:
        """
        When dedup returns an older row, its URL may still point at the listing page while
        the pipeline now has the per-notice URL. Prefer the more specific path so DB2 URL
        matching and the UI link stay correct.
        """
        if not incoming_url or not str(incoming_url).strip():
            return (existing_url or "").strip()
        if not existing_url or not str(existing_url).strip():
            return str(incoming_url).strip()
        ex = str(existing_url).rstrip("/")
        inc = str(incoming_url).rstrip("/")
        if ex == inc:
            return ex
        if "/bid/notice/" in inc and "/bid/notice/" not in ex:
            return inc
        if inc.count("/") > ex.count("/") and len(inc) > len(ex) + 5:
            return inc
        return ex

    @staticmethod
    def _normalize_text(value: Optional[str]) -> str:
        if not value:
            return ""
        cleaned = re.sub(r"\s+", " ", str(value)).strip().lower()
        return cleaned

    _PLACEHOLDER_VALUES = {
        "null",
        "none",
        "n/a",
        "na",
        "unknown",
        "not specified",
        "not available",
        "not provided",
        "not stated",
        "no information",
        "no information provided",
        "budget/estimated value",
        "budget/estimated value with currency",
        "project duration/timeline",
        "issuing organization",
        "contact person name",
        "phone number",
        "email address",
        "physical address",
        "other important information",
        "relevant categories",
    }

    @classmethod
    def _clean_optional_text(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        text_value = str(value).strip()
        if not text_value:
            return None
        normalized = re.sub(r"\s+", " ", text_value).strip().lower()
        if normalized in cls._PLACEHOLDER_VALUES:
            return None
        return text_value

    @classmethod
    def _clean_contact_info(cls, value: Any) -> Optional[Any]:
        if isinstance(value, dict):
            cleaned = {
                key: cls._clean_optional_text(item)
                for key, item in value.items()
            }
            return cleaned if any(v for v in cleaned.values()) else None
        return cls._clean_optional_text(value)

    def build_opportunity_fingerprint(
        self,
        page_id: int,
        title: str,
        screening_result: Optional[Dict[str, Any]] = None,
        tender_date: Optional[str] = None,
    ) -> str:
        """
        Build a stable fingerprint for opportunity-level dedupe.
        Same source page can contain many opportunities; dedupe by identity fields,
        not by page URL.
        """
        step3 = (screening_result or {}).get("step3", {}) or {}
        parts = [
            f"page:{page_id}",
            f"title:{self._normalize_text(title)}",
            f"deadline:{self._normalize_text(step3.get('deadline') or tender_date)}",
            f"source:{self._normalize_text(step3.get('source'))}",
            f"type:{self._normalize_text(step3.get('type'))}",
            f"country:{self._normalize_text(step3.get('country'))}",
        ]
        payload = "|".join(parts)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
    
    def save_tender(
        self,
        db: Session,
        page_id: int,
        title: str,
        url: str,
        tender_date: Optional[str],
        description: str,
        screening_result: Optional[Dict[str, Any]] = None,
        matched_keywords: Optional[List[str]] = None,
        keyword_count: int = 0,
        category: Optional[str] = None,
    ) -> Optional[Tender]:
        """
        Save a tender with keyword tracking.

        - Parses the input tender_date with robust format fallback.
        - Avoids duplicate tenders by checking an opportunity fingerprint.
        - Serializes matched keywords to JSON for storage.
        - Associates tender with matching keywords (for reporting/statistics).
        - Commits changes safely and handles rollback on exceptions.
        """
        try:
            # Parse date if provided, attempt multiple formats if needed.
            parsed_date = None
            if tender_date:
                try:
                    parsed_date = datetime.strptime(tender_date, '%Y-%m-%d')
                except ValueError:
                    for fmt in ['%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d']:
                        try:
                            parsed_date = datetime.strptime(tender_date, fmt)
                            break
                        except ValueError:
                            continue
            
            fingerprint = self.build_opportunity_fingerprint(
                page_id=page_id,
                title=title,
                screening_result=screening_result,
                tender_date=tender_date,
            )

            # Avoid saving duplicate tenders (opportunity identity).
            existing = db.query(Tender).filter(Tender.opportunity_fingerprint == fingerprint).first()
            if existing:
                merged_url = self._prefer_detail_url(existing.url, url)
                prev = (existing.url or "").strip().rstrip("/")
                if merged_url.rstrip("/") != prev:
                    existing.url = merged_url
                    db.commit()
                    db.refresh(existing)
                logger.info(f"Tender already exists: {title[:50]}...")
                return existing

            # Detail URLs are the most stable identity when Agent 1 changes title/source wording.
            normalized_url = self._normalize_url(url)
            if normalized_url and not self._is_listing_page_url(db, page_id, normalized_url):
                existing_by_url = db.query(Tender).filter(
                    and_(
                        Tender.page_id == page_id,
                        Tender.url.in_([normalized_url, f"{normalized_url}/"]),
                    )
                ).first()
                if existing_by_url:
                    logger.info("Tender already exists by URL: %s", normalized_url)
                    return existing_by_url
            
            step1 = screening_result.get("step1", {}) if screening_result else {}
            step2_raw = screening_result.get("step2", {}) if screening_result else {}
            step2: Dict[str, Any] = dict(step2_raw) if isinstance(step2_raw, dict) else {}
            if screening_result:
                lang = screening_result.get("source_language")
                if isinstance(lang, str) and lang.strip():
                    step2["source_language"] = lang.strip()[:32].lower()
            step3 = screening_result.get("step3", {}) if screening_result else {}
            yes_count = int(screening_result.get("yes_count", 0)) if screening_result else 0
            passes_screening = bool(screening_result.get("passes_filter", False)) if screening_result else False
            screening_version = screening_result.get("screening_version", "v1_checklist") if screening_result else "legacy"

            # Create the new Tender object.
            tender = Tender(
                title=title,
                url=normalized_url or url,
                opportunity_fingerprint=fingerprint,
                tender_date=parsed_date,
                category=category or "legacy",
                description=description,
                page_id=page_id,
                matched_keywords_json=matched_keywords or [],
                keyword_count=keyword_count,
                source=step3.get("source"),
                country=step3.get("country"),
                opportunity_type=step3.get("type"),
                estimated_budget=step3.get("estimated_budget"),
                screening_version=screening_version,
                screening_yes_count=yes_count,
                passes_screening=passes_screening,
                screening_step1=step1,
                screening_step2=step2,
                screening_step3=step3,
            )
            
            db.add(tender)
            db.flush()  # Assigns an ID to the new tender.
            
            # Store associations with matching keywords (if any keywords matched).
            if matched_keywords:
                self._save_keyword_associations(db, tender.id, matched_keywords)
            
            db.commit()
            db.refresh(tender)
            
            logger.info(f"Saved tender: {title[:50]}... (Keywords: {keyword_count})")
            return tender
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error saving tender: {e}")
            raise e
    
    def _save_keyword_associations(self, db: Session, tender_id: int, matched_keywords: List[str]):
        """
        Save tender-keyword associations in the database.

        - Retrieves all active keywords from the database and builds a lowercase map.
        - For each matched keyword string:
            - If found in active keywords, creates a link in the association table using a raw SQL INSERT OR IGNORE (robust for many-to-many).
            - Increments the keyword usage stats.
            - Logs association or missing keyword.
        """
        try:
            all_keywords = db.query(Keyword).filter(Keyword.is_active == True).all()
            keyword_map = {kw.keyword.lower(): kw for kw in all_keywords}
            
            for keyword_str in matched_keywords:
                keyword_lower = keyword_str.lower()
                if keyword_lower in keyword_map:
                    keyword_obj = keyword_map[keyword_lower]
                    
                    # Association creation via SQL.
                    db.execute(text("""
                        INSERT OR IGNORE INTO tender_keywords (tender_id, keyword_id, created_at)
                        VALUES (:tender_id, :keyword_id, :created_at)
                    """), {
                        'tender_id': tender_id,
                        'keyword_id': keyword_obj.id,
                        'created_at': datetime.utcnow()
                    })
                    
                    # Increment stats.
                    keyword_obj.increment_usage()
                    
                    logger.debug(f"Associated tender {tender_id} with keyword '{keyword_str}'")
                else:
                    logger.warning(f"Keyword '{keyword_str}' not found in database")
            
        except Exception as e:
            logger.error(f"Error saving keyword associations: {e}")
    
    def save_detailed_tender(self, db: Session, tender_id: int, detailed_info: Dict[str, Any]) -> Optional[DetailedTender]:
        """
        Save detailed tender information, handling multiple possible data types and enrichment.

        - Checks if a DetailedTender already exists for the given tender_id.
        - Converts possibly mixed data types to appropriate DB storage format for:
            - Title, description, requirements, deadline, contact_info, validation info.
        - Updates main Tender to mark as processed.
        - Handles commit/rollback robustly.
        """
        try:
            existing = db.query(DetailedTender).filter(DetailedTender.tender_id == tender_id).first()
            if existing:
                logger.info(f"Updating existing detailed tender for tender_id {tender_id}")
                return self._update_existing_detailed_tender(db, existing, detailed_info)
            
            detailed_title = self._clean_optional_text(detailed_info.get('detailed_title')) or ''
            detailed_description = self._clean_optional_text(detailed_info.get('detailed_description')) or ''
            
            # Handle requirements list/str/None.
            requirements = detailed_info.get('requirements')
            if isinstance(requirements, list):
                requirements_str = '\n'.join(
                    [
                        item
                        for item in (self._clean_optional_text(req) for req in requirements)
                        if item
                    ]
                ) or None
            elif requirements:
                requirements_str = self._clean_optional_text(requirements)
            else:
                requirements_str = None
            
            deadline = self._parse_deadline(detailed_info.get('deadline'))
            
            contact_info = self._clean_contact_info(detailed_info.get('contact_info'))
            if isinstance(contact_info, dict):
                contact_info_str = json.dumps(contact_info)
            elif contact_info:
                contact_info_str = str(contact_info)
            else:
                contact_info_str = None
            
            date_validation = detailed_info.get('date_validation')
            if date_validation:
                date_validation_str = json.dumps(date_validation)
            else:
                date_validation_str = None

            tender_value = self._clean_optional_text(detailed_info.get('tender_value'))
            duration = self._clean_optional_text(detailed_info.get('duration'))
            if not tender_value or not duration:
                inferred_value, inferred_duration = self._infer_value_and_duration_from_text(
                    detailed_description=detailed_description,
                    additional_details=self._clean_optional_text(detailed_info.get('additional_details')),
                    full_content=str(detailed_info.get('full_content', '')) if detailed_info.get('full_content') else None,
                )
                tender_value = tender_value or inferred_value
                duration = duration or inferred_duration

            additional_details = self._clean_optional_text(detailed_info.get('additional_details'))
            
            # Compose the new DetailedTender
            detailed_tender = DetailedTender(
                tender_id=tender_id,
                detailed_title=detailed_title,
                detailed_description=detailed_description,
                requirements=requirements_str,
                deadline=deadline,
                tender_value=tender_value,
                duration=duration,
                contact_info=contact_info_str,
                additional_details=additional_details,
                full_content=str(detailed_info.get('full_content', '')) if detailed_info.get('full_content') else '',
                processing_status="processed",
                date_validation=date_validation_str,
                processed_at=datetime.utcnow()
            )
            
            # Mark the main tender as processed as well.
            db_tender = db.query(Tender).filter(Tender.id == tender_id).first()
            if db_tender:
                db_tender.is_processed = True
                db_tender.updated_at = datetime.utcnow()
                self._maybe_upgrade_tender_title_from_detail(
                    db, tender_id, detailed_title or None
                )

            db.add(detailed_tender)
            db.commit()
            db.refresh(detailed_tender)
            
            logger.info(f"Successfully saved detailed info for tender ID: {tender_id}")
            return detailed_tender
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error saving detailed tender {tender_id}: {str(e)}")
            raise e
    
    def _update_existing_detailed_tender(self, db: Session, existing: DetailedTender, detailed_info: Dict[str, Any]) -> DetailedTender:
        """
        Update an already existing DetailedTender with new info.

        - Only fields present in new detailed_info are updated.
        - Handles lists/dicts for requirements/contact info similarly to the create method.
        - Sets updated/processed timestamps and status.
        - Commits the change.
        """
        try:
            detailed_title = self._clean_optional_text(detailed_info.get('detailed_title'))
            if detailed_title:
                existing.detailed_title = detailed_title
            detailed_description = self._clean_optional_text(detailed_info.get('detailed_description'))
            if detailed_description:
                existing.detailed_description = detailed_description
            
            # Requirements update
            if detailed_info.get('requirements'):
                requirements = detailed_info['requirements']
                if isinstance(requirements, list):
                    existing.requirements = '\n'.join(
                        [
                            item
                            for item in (self._clean_optional_text(req) for req in requirements)
                            if item
                        ]
                    )
                else:
                    cleaned_requirements = self._clean_optional_text(requirements)
                    if cleaned_requirements:
                        existing.requirements = cleaned_requirements
            
            # Contact info update
            if detailed_info.get('contact_info'):
                contact_info = self._clean_contact_info(detailed_info['contact_info'])
                if isinstance(contact_info, dict):
                    existing.contact_info = json.dumps(contact_info)
                elif contact_info:
                    existing.contact_info = str(contact_info)
            
            additional_details = self._clean_optional_text(detailed_info.get('additional_details'))
            if additional_details:
                existing.additional_details = additional_details
            if detailed_info.get('full_content'):
                existing.full_content = str(detailed_info['full_content'])
            tender_value = self._clean_optional_text(detailed_info.get('tender_value'))
            if tender_value:
                existing.tender_value = tender_value
            duration = self._clean_optional_text(detailed_info.get('duration'))
            if duration:
                existing.duration = duration
            
            # Deadline/date validation
            if detailed_info.get('deadline'):
                existing.deadline = self._parse_deadline(detailed_info['deadline'])
            
            if detailed_info.get('date_validation'):
                existing.date_validation = json.dumps(detailed_info['date_validation'])

            if not existing.tender_value or not existing.duration:
                inferred_value, inferred_duration = self._infer_value_and_duration_from_text(
                    detailed_description=existing.detailed_description,
                    additional_details=existing.additional_details,
                    full_content=existing.full_content,
                )
                if not existing.tender_value and inferred_value:
                    existing.tender_value = inferred_value
                if not existing.duration and inferred_duration:
                    existing.duration = inferred_duration
            
            existing.updated_at = datetime.utcnow()
            existing.processed_at = datetime.utcnow()
            existing.processing_status = "processed"

            db_tender = db.query(Tender).filter(Tender.id == existing.tender_id).first()
            if db_tender:
                db_tender.is_processed = True
                db_tender.updated_at = datetime.utcnow()

            if detailed_title:
                self._maybe_upgrade_tender_title_from_detail(
                    db, existing.tender_id, detailed_title
                )

            db.commit()
            return existing
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating detailed tender: {e}")
            raise e

    def _infer_value_and_duration_from_text(
        self,
        detailed_description: Optional[str],
        additional_details: Optional[str],
        full_content: Optional[str],
    ) -> tuple[Optional[str], Optional[str]]:
        """Infer tender value and duration from free text when Agent 2 omits structured fields."""
        text_blob = " ".join(
            [
                str(detailed_description or ""),
                str(additional_details or ""),
                str(full_content or ""),
            ]
        )
        text_blob = re.sub(r"\s+", " ", text_blob).strip()
        if not text_blob:
            return None, None

        value = None
        duration = None

        budget_match = re.search(
            r"(?:budget|value|estimated budget)\s*[:\-]\s*([A-Za-z]{2,5}\s?[\d,]+(?:\.\d+)?)",
            text_blob,
            re.IGNORECASE,
        )
        if budget_match:
            value = budget_match.group(1).strip()

        start_match = re.search(r"(?:project start date|start date)\s*[:\-]\s*(\d{4}-\d{2}-\d{2})", text_blob, re.IGNORECASE)
        end_match = re.search(r"(?:project end date|end date)\s*[:\-]\s*(\d{4}-\d{2}-\d{2})", text_blob, re.IGNORECASE)
        if start_match and end_match:
            duration = f"{start_match.group(1)} to {end_match.group(1)}"
        else:
            duration_match = re.search(r"(?:duration|timeline)\s*[:\-]\s*([^.;\n]+)", text_blob, re.IGNORECASE)
            if duration_match:
                duration = duration_match.group(1).strip()

        return value, duration
    
    def _parse_deadline(self, deadline_value) -> Optional[datetime]:
        """
        Parse a deadline value (str, datetime or None) to a datetime object.

        - Tries multiple string date formats.
        - Returns None if parsing fails or value isn't set.
        """
        if not deadline_value:
            return None

        try:
            if isinstance(deadline_value, datetime):
                return deadline_value

            deadline_str = str(deadline_value).strip()
            if deadline_str.lower() in ("null", "n/a", "none", ""):
                return None

            # ISO-8601 datetime (e.g. 2026-04-28T15:45:00)
            if "T" in deadline_str and re.match(r"\d{4}-\d{2}-\d{2}T", deadline_str):
                try:
                    iso = deadline_str.replace("Z", "+00:00")
                    return datetime.fromisoformat(iso)
                except ValueError:
                    try:
                        return datetime.fromisoformat(deadline_str.split("+")[0].split(".")[0])
                    except ValueError:
                        pass

            human_opening = (
                "%d %b %Y at %H:%M",
                "%d %B %Y at %H:%M",
            )
            fmts = [
                "%Y-%m-%d",
                "%Y-%m-%d %H:%M",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f",
                "%d.%m.%Y",
                "%d/%m/%Y",
            ] + list(human_opening)

            for fmt in fmts:
                try:
                    return datetime.strptime(deadline_str, fmt)
                except ValueError:
                    continue

            logger.warning(f"Could not parse deadline: {deadline_value}")
            return None

        except Exception as e:
            logger.warning(f"Deadline parsing error: {e}")
            return None

    def _maybe_upgrade_tender_title_from_detail(
        self,
        db: Session,
        tender_id: int,
        detailed_title: Optional[str],
    ) -> None:
        """Replace ref-number-only list titles with the real subject when Agent 2 provides it."""
        if not detailed_title:
            return
        try:
            from app.agents.portal_detail_hints import title_upgrade_warranted
        except Exception:
            return
        t = db.query(Tender).filter(Tender.id == tender_id).first()
        if not t or not title_upgrade_warranted(t.title, detailed_title):
            return
        dt = str(detailed_title).strip()
        t.title = dt[:500]
        t.updated_at = datetime.utcnow()
    
    def get_unnotified_tenders(
        self,
        db: Session,
        only_passed: bool = True,
        require_processed: bool = False,
    ) -> List[Tender]:
        """
        Returns non-notified tenders.

        - only_passed: restrict to checklist-recommended rows (passes_screening).
        - require_processed: when True, only rows with Agent 2 complete (is_processed).
          Use for fallback digest so we never mark "notified" before detail extraction.
        """
        query = db.query(Tender).filter(Tender.is_notified == False)
        if only_passed:
            query = query.filter(Tender.passes_screening == True)
        if require_processed:
            query = query.filter(Tender.is_processed == True)
        return query.all()

    @staticmethod
    def tender_to_agent2_basic_payload(tender: Tender) -> Dict[str, Any]:
        """Rebuild Agent-1-shaped dict from a DB row for Agent 2 / retry."""
        step3 = tender.screening_step3 if isinstance(tender.screening_step3, dict) else {}
        deadline_str = None
        if step3.get("deadline"):
            deadline_str = str(step3["deadline"])
        elif tender.tender_date:
            deadline_str = tender.tender_date.strftime("%Y-%m-%d")
        screening: Dict[str, Any] = {
            "unrelated_to_precise_scope": False,
            "step1": tender.screening_step1 if isinstance(tender.screening_step1, dict) else {},
            "step2": tender.screening_step2 if isinstance(tender.screening_step2, dict) else {},
            "step3": step3,
            "yes_count": tender.screening_yes_count or 0,
            "passes_filter": bool(tender.passes_screening),
            "screening_version": tender.screening_version or "v1_checklist",
        }
        return {
            "id": tender.id,
            "title": tender.title,
            "url": tender.url,
            "date": deadline_str,
            "description": tender.description or "",
            "screening": screening,
            "date_status": "unknown",
        }

    def get_pending_detail_tenders(
        self,
        db: Session,
        *,
        only_passed_screening: bool = True,
        limit: int = 50,
    ) -> List[Tender]:
        """Tenders with no successful Agent 2 flag (is_processed False), for bulk retry."""
        q = db.query(Tender).filter(Tender.is_processed == False)
        if only_passed_screening:
            q = q.filter(Tender.passes_screening == True)
        return q.order_by(Tender.created_at.asc()).limit(max(1, min(limit, 100))).all()
    
    def get_tenders_with_keywords(self, db: Session, keywords: List[str], limit: int = 100) -> List[Tender]:
        """
        Returns up to limit tenders where any matched_keywords_json entry matches one of the provided keywords.
        (Case insensitive, slow for large numbers but keeps SQLite compatibility.)

        - Doubles the query limit for filtering, then only returns the first 'limit' matches.
        - Safe JSON loads with error skip.
        """
        tenders = []
        for tender in db.query(Tender).limit(limit * 2).all():
            if tender.matched_keywords_json:
                try:
                    if isinstance(tender.matched_keywords_json, str):
                        tender_keywords = json.loads(tender.matched_keywords_json)
                    else:
                        tender_keywords = tender.matched_keywords_json
                    if any(kw.lower() in [tk.lower() for tk in tender_keywords] for kw in keywords):
                        tenders.append(tender)
                        if len(tenders) >= limit:
                            break
                except json.JSONDecodeError:
                    continue
        
        return tenders
    
    def get_keyword_usage_stats(self, db: Session) -> Dict[str, Any]:
        """
        Returns usage statistics for keywords.

        - Tallies up keyword usage, splits by category.
        - Returns top 10 keywords by usage (with last used time).
        - Used for reports/monitoring keyword relevance.
        """
        try:
            keywords_with_usage = db.query(Keyword).filter(Keyword.usage_count > 0).all()
            
            stats = {
                'total_keywords_used': len(keywords_with_usage),
                'top_keywords': [],
                'category_breakdown': {},
                'total_keyword_matches': sum(kw.usage_count for kw in keywords_with_usage)
            }
            
            sorted_keywords = sorted(keywords_with_usage, key=lambda x: x.usage_count, reverse=True)
            stats['top_keywords'] = [
                {
                    'keyword': kw.keyword,
                    'category': kw.category,
                    'usage_count': kw.usage_count,
                    'last_used': kw.last_used.isoformat() if kw.last_used else None
                }
                for kw in sorted_keywords[:10]
            ]
            
            # Build per-category breakdown (sector, activity_fit, geography, source_tag, ...)
            for kw in keywords_with_usage:
                cat = kw.category or "uncategorized"
                stats["category_breakdown"][cat] = (
                    stats["category_breakdown"].get(cat, 0) + kw.usage_count
                )
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting keyword usage stats: {e}")
            return {}
    
    def mark_tender_notified(self, db: Session, tender_id: int):
        """
        Mark a tender as having been notified to a user/subscriber.

        - Sets is_notified = True and updates the timestamp.
        """
        tender = db.query(Tender).filter(Tender.id == tender_id).first()
        if tender:
            tender.is_notified = True
            tender.updated_at = datetime.utcnow()
            db.commit()
    
    def get_tenders_by_page(self, db: Session, page_id: int, limit: int = 50) -> List[Tender]:
        """
        Get most recent tenders for a specific source/page, descending by creation.
        """
        return db.query(Tender).filter(Tender.page_id == page_id).order_by(Tender.created_at.desc()).limit(limit).all()
    
    def get_recent_tenders(self, db: Session, days: int = 7, limit: int = 100) -> List[Tender]:
        """
        Get tenders added within the last N days, up to a limit.
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        return (
            db.query(Tender)
            .options(joinedload(Tender.detailed_tender))
            .filter(Tender.created_at >= cutoff_date)
            .order_by(Tender.created_at.desc())
            .limit(limit)
            .all()
        )
    
    def get_tender_by_id(self, db: Session, tender_id: int) -> Optional[Tender]:
        """
        Get a tender by its unique database ID.
        """
        return db.query(Tender).filter(Tender.id == tender_id).first()

    def delete_tender(self, db: Session, tender_id: int) -> bool:
        """
        Delete a tender by ID. The DetailedTender row (if any) is removed via
        the configured cascade on the relationship.

        Returns True on success, False if no tender with that ID exists.
        """
        tender = db.query(Tender).filter(Tender.id == tender_id).first()
        if not tender:
            return False
        try:
            tender.matched_keywords.clear()
            db.delete(tender)
            db.commit()
            logger.info("Deleted tender id=%s title=%r", tender_id, tender.title[:80])
            return True
        except Exception as exc:
            db.rollback()
            logger.error("Failed to delete tender id=%s: %s", tender_id, exc)
            raise
    
    def get_detailed_tender_by_tender_id(self, db: Session, tender_id: int) -> Optional[DetailedTender]:
        """
        Get a detailed tender record (if any exists) for the given tender_id.
        """
        return db.query(DetailedTender).filter(DetailedTender.tender_id == tender_id).first()
    
    def check_duplicate_tender(
        self,
        db: Session,
        title: str,
        url: str,
        page_id: int,
        screening_result: Optional[Dict[str, Any]] = None,
        tender_date: Optional[str] = None,
    ) -> bool:
        """
        Check for duplicates for a given opportunity (fingerprint primarily, then title/date fallback).

        - Returns True if a duplicate (by URL or by title/page) exists, False otherwise.
        """
        fingerprint = self.build_opportunity_fingerprint(
            page_id=page_id,
            title=title,
            screening_result=screening_result,
            tender_date=tender_date,
        )

        existing_by_fingerprint = db.query(Tender).filter(
            Tender.opportunity_fingerprint == fingerprint
        ).first()
        if existing_by_fingerprint:
            return True

        # Same detail URL means same notice, even if the LLM extracted a shorter title/source.
        normalized_url = self._normalize_url(url)
        if normalized_url and not self._is_listing_page_url(db, page_id, normalized_url):
            existing_by_url = db.query(Tender).filter(
                and_(
                    Tender.page_id == page_id,
                    Tender.url.in_([normalized_url, f"{normalized_url}/"]),
                )
            ).first()
            if existing_by_url:
                return True

        # Fallback: exact title + same page + same tender date (if available)
        normalized_tender_date = None
        step3 = (screening_result or {}).get("step3", {}) or {}
        raw_date = step3.get("deadline") or tender_date
        if raw_date:
            try:
                normalized_tender_date = datetime.strptime(str(raw_date), "%Y-%m-%d")
            except ValueError:
                normalized_tender_date = None

        query = db.query(Tender).filter(
            and_(
                Tender.title == title,
                Tender.page_id == page_id,
            )
        )
        if normalized_tender_date:
            query = query.filter(Tender.tender_date == normalized_tender_date)
        existing_by_title = query.first()
        
        return existing_by_title is not None

# ------------------------------------------------------------------------------------------
# FILE COMMENTS:
#
# File: app/repositories/tender_repository.py
# 
# This file defines the core persistence/repository logic for dealing with tender (procurement/invitation) records
# in the application's database. It uses SQLAlchemy ORM for all its database interactions and also works with
# two primary data models: Tender (basic tender info) and DetailedTender (richer, parsed info per tender). It also
# leverages the Keyword model for keyword tracking and statistics.
#
# Main Capabilities:
# - Inserting new tenders and associating them with detected keywords, tracking keyword usage.
# - Saving and updating detailed parsed tender information, flexibly converting source data into stable database formats.
# - Avoiding duplicates via checks on URLs and titles per source ('page').
# - Marking tenders as notified to users/subscribers.
# - Retrieving tenders by a variety of filters: by recency, by page, by keyword, or to support notifications.
# - Collecting statistics on keyword usage and tender keyword matches, enabling monitoring and reporting.
# - Uses robust error handling, rollback on failure, and logs all major actions and issues.
# 
# Notable Implementation Details:
# - Keyword associations are managed with direct SQL for reliability in many-to-many junctions.
# - Dates are parsed flexibly from strings with various possible formats.
# - Some database fields (matched_keywords_json, contact_info, etc.) use JSON serialization for structure.
# - Designed for extendibility, as seen in helper methods and conventions.
#
# This is a core backend file supporting tender aggregation, notification, and keyword analytics services.