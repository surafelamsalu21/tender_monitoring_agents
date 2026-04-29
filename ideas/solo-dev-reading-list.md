# Solo Developer Reading List (What You Must Know)

This is a practical reading plan for this project.  
Goal: know the critical system deeply, not every line.

---

## 1) First priority: understand the main execution path

Read these in order:

1. `app/main.py`
   - Understand app startup and where scheduler starts.
   - Know `lifespan()`, `trigger_manual_extraction()`.

2. `app/services/scheduler.py`
   - This is the runtime orchestrator.
   - Know `run_extraction_once()`, `_process_page_extended_pipeline()`, `_send_intelligent_notifications()`, `_send_fallback_notifications()`.

3. `app/agents/workflow.py`
   - This is the pipeline graph (Agent 1 -> dedupe -> DB1 -> Agent 2 -> DB2 -> Agent 3).
   - Know `_build_workflow()`, `_agent1_extract_node()`, `_check_duplicates_node()`, `_save_to_db1_node()`, `_agent2_details_node()`, `_save_to_db2_node()`, `_agent3_compose_node()`, `process_page()`.

Why this matters: if this file set is clear, you understand how the system actually runs.

---

## 2) Second priority: extraction and data contracts

4. `app/agents/agent1.py`
   - Understand category logic and base extraction schema.
   - Know `extract_and_categorize_tenders()`, `_build_strict_extraction_prompt()`, `_double_check_keyword_matching()`, `_validate_tenders()`.

5. `app/agents/agent2.py`
   - Understand detailed extraction schema and date validation behavior.
   - Know `extract_tender_details()`, `_build_enhanced_detail_extraction_prompt()`, `_validate_extracted_dates()`, `_parse_detail_response()`.

6. `app/models/tender.py`
   - This is the source-of-truth DB structure for tenders.
   - Know `Tender`, `DetailedTender`, and `tender_keywords`.

7. `app/repositories/tender_repository.py`
   - Understand exactly how extracted fields are saved/updated.
   - Know `save_tender()`, `save_detailed_tender()`, `get_unnotified_tenders()`, `check_duplicate_tender()`.

Why this matters: every schema/category change will touch these files.

---

## 3) Third priority: API + frontend contract

8. `app/api/routes/tenders.py`
   - Understand what frontend receives for list/detail/stats.
   - Know `get_tenders()`, `get_tender()`, `get_tender_stats()`.

9. `app/api/routes/keywords.py`
   - Understand how keyword categories are validated and managed.

10. `react-frontend/src/types/index.ts`
    - Frontend type contract for `Tender`, `DetailedTenderInfo`, `Keyword`.

11. `react-frontend/src/services/api.ts`
    - API endpoint mapping used by UI.

12. `react-frontend/src/components/TenderList.tsx`
    - Main consumer of tender + detailed fields in UI.

13. `react-frontend/src/components/KeywordManager.tsx`
    - Category management UI assumptions.

14. `react-frontend/src/components/Dashboard.tsx`
    - Category stats assumptions.

Why this matters: backend changes will break UI here first.

---

## 4) Fourth priority: notifications and team routing

15. `app/agents/agent3.py`
    - Understand email composition payload requirements.
    - Know `compose_tender_email()`, `compose_multiple_tenders_email()`, `compose_multiple_emails()`.

16. `app/services/email_service.py`
    - Understand actual send behavior and DB logging.
    - Know `send_intelligent_notifications()`, `_send_single_intelligent_email_db()`, `send_fallback_notifications()`.

17. `app/repositories/email_settings_repository.py`
    - Understand email config persistence and notification preferences.

18. `app/api/routes/system.py`
    - Understand settings/test endpoints the frontend calls.

---

## 5) Fifth priority: config and defaults

19. `app/core/config.py`
    - Know runtime settings, env variables, timeout/concurrency.

20. `app/core/init_data.py`
    - Know default keyword/category seed behavior.

---

## 6) Optional but good awareness (not deep)

- `database_inspector.py`, `check_db.py`, `test_api.py` (debug utilities)
- `README.md`, `BACKEND_AGENTS_DETAILED.md` (docs, may be stale)
- Root-level legacy stack:
  - `main.py`, `agents.py`, `scheduler.py`, `models.py`, `database.py`, `config.py`

Treat the root-level stack as legacy unless you actively run it.

---

## 7) What you must be able to answer from memory

You are in good shape if you can answer these quickly:

1. Where does extraction start from a page URL?
2. Where is category assignment decided?
3. Where are extracted fields validated?
4. Where are DB writes for basic and detailed tenders?
5. What API shape does frontend depend on?
6. Where does email routing choose recipients by category?
7. Which files break if category names change?

---

## 8) Simple weekly maintenance routine

Each week:

1. Re-read `app/services/scheduler.py` and `app/agents/workflow.py`.
2. Skim diffs in:
   - `app/agents/agent1.py`
   - `app/agents/agent2.py`
   - `app/models/tender.py`
   - `app/repositories/tender_repository.py`
   - `app/api/routes/tenders.py`
   - `react-frontend/src/types/index.ts`
3. Run one end-to-end manual extraction and inspect one tender in DB + UI.

---

## 9) Recommended time split (solo dev)

- 60%: sections 1-3 (core flow + schema + API/UI contract)
- 25%: section 4 (notification side effects)
- 10%: section 5 (config/defaults)
- 5%: section 6 (utilities/legacy awareness)

This keeps your understanding high without wasting time on low-impact code.

