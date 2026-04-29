# Tender Monitoring Agents - Backend & Agents Guide

This document explains the backend structure of the project and what each backend/agent file does.  
It intentionally excludes anything inside `react-frontend/`.

> Test note v2: this line verifies green/red diff review mode is active.

## 1) Backend Architecture (High Level)

The repository currently contains **two backend tracks**:

- **Primary track (recommended):** modular FastAPI backend under `app/`
  - API server: `app/main.py`
  - API routes: `app/api/routes/*`
  - DB/session/config: `app/core/*`
  - ORM models: `app/models/*`
  - data access layer: `app/repositories/*`
  - processing services (scheduler/scraper/email): `app/services/*`
  - multi-agent workflow (Agent1/2/3): `app/agents/*`
- **Legacy track (still present):** root-level scripts/modules (`main.py`, `scheduler.py`, `agents.py`, etc.)
  - older monolithic flow
  - different config/model/database defaults in some places

## 2) Startup and Execution Paths

### Recommended startup path

- Run `run.py`
  1. Configures logging (`app/core/logging.py`)
  2. Creates DB tables (`app/core/database.py`)
  3. Seeds defaults (`app/core/init_data.py`)
  4. Starts FastAPI (`app.main:app`)

### App lifecycle behavior

- `app/main.py` defines FastAPI lifespan hooks:
  - on startup: starts async `TenderScheduler` (`app/services/scheduler.py`)
  - on shutdown: stops scheduler cleanly

### Manual extraction trigger

- API endpoint in `app/main.py`: `POST /trigger-extraction`
  - starts one extraction run in the background via scheduler

## 3) Folder-by-Folder File Responsibilities

## Root-Level Backend Files (Legacy + Utilities)

### `main.py`
- Legacy command-style entrypoint with menu actions like test/run/schedule.
- Uses root modules (`scheduler.py`, `database.py`, `agents.py`, etc.).

### `run.py`
- Main app launcher for modern backend.
- Initializes DB and default data before running uvicorn.

### `config.py`
- Legacy environment config class.
- Contains legacy interval/database defaults (separate from `app/core/config.py`).

### `models.py`
- Legacy SQLAlchemy models/base/session setup.
- Not the same model package used by the `app/` modular backend.

### `database.py`
- Legacy `DatabaseManager` abstraction for CRUD and retrieval operations.
- Used by legacy scheduler/flow.

### `agents.py`
- Legacy tender agent orchestration using LangGraph.
- Older style compared to `app/agents/workflow.py`.

### `scraper.py`
- Legacy scraper implementation for monitored pages.

### `email_service.py`
- Legacy SMTP email sender service.

### `scheduler.py`
- Legacy scheduler based on `schedule` library and blocking loop.
- Runs periodic extraction using legacy stack.

### `database_inspector.py`
- SQLite inspection and export utility script.

### `check_db.py`
- Interactive DB checks/inspection helper script.

### `create_email_settings_tables.py`
- Utility script to create/initialize email settings tables.

### `test.py`
- Scratch/simple crawl4ai test script.

### `test_api.py`
- Script-style API test for backend endpoints.

### `test_email_api.py`
- Script-style API test for email settings endpoints.

### `email_test.py`
- Script to validate email settings and related DB behavior.

---

## `app/` Package (Primary Backend)

### `app/main.py`
- Creates FastAPI app and registers router from `app/api/main.py`.
- Hosts health/root endpoints.
- Controls scheduler lifecycle through lifespan hooks.

---

## `app/api/`

### `app/api/main.py`
- Central API router aggregator.
- Includes route groups: tenders, pages, keywords, system.

---

## `app/api/routes/`

### `app/api/routes/tenders.py`
- Endpoints for listing/filtering tender data and related tender operations.

### `app/api/routes/pages.py`
- Endpoints to manage monitored pages (CRUD-style operations).

### `app/api/routes/keywords.py`
- Endpoints to manage keyword configuration used by extraction/classification.

### `app/api/routes/system.py`
- System-level endpoints:
  - status/info
  - email settings get/save
  - test email
  - test crawler/extraction helpers

### `app/api/routes/email_settings.py`
- Alternate/duplicate email settings route module.
- Not typically mounted by `app/api/main.py`.

---

## `app/core/`

### `app/core/config.py`
- Pydantic settings loaded from environment variables.
- Defines DB URL, OpenAI/SMTP params, intervals, CORS, and runtime settings.

### `app/core/database.py`
- SQLAlchemy engine/session creation and DB dependency provider.
- `create_tables()` for initializing schema.

### `app/core/init_data.py`
- Seeds initial project data:
  - default monitored pages
  - default keywords
  - default email settings

### `app/core/logging.py`
- Logging configuration used by startup/runtime.

---

## `app/models/`

### `app/models/__init__.py`
- Re-export module for all ORM models.

### `app/models/page.py`
- `MonitoredPage` model (tracked URLs/pages to scrape).

### `app/models/tender.py`
- Tender models for extracted tenders and detailed tender records.

### `app/models/keyword.py`
- Keyword model used for categories/filters/rules.

### `app/models/crawl_log.py`
- Crawl and run logging model for monitoring extraction history.

### `app/models/email_settings.py`
- Email settings/log models for notification system.

---

## `app/repositories/`

### `app/repositories/page_repository.py`
- Data-access logic for monitored pages.

### `app/repositories/tender_repository.py`
- Data-access logic for tenders/detailed tenders.

### `app/repositories/keyword_repository.py`
- Data-access logic for keyword records and category lookups.

### `app/repositories/email_settings_repository.py`
- Data-access logic for email recipients/settings/logging.

---

## `app/services/`

### `app/services/scheduler.py`
- Primary async scheduler for periodic extraction.
- Core pipeline orchestration per active page:
  1. scrape page
  2. run agent workflow
  3. send intelligent/fallback notifications

### `app/services/scraper.py`
- Primary crawl4ai scraping service used by app scheduler.
- Returns structured scrape result (including markdown/text used by agents).

### `app/services/email_service.py`
- Enhanced email sender:
  - sends intelligent notifications from Agent 3 outputs
  - supports fallback notifications
  - uses DB-configured recipients/settings

### `app/services/agents.py`
- Alternative service-level agent implementation.
- Often treated as secondary/unreferenced compared to `app/agents/workflow.py`.

---

## `app/agents/` (Core Multi-Agent Logic)

### `app/agents/__init__.py`
- Exposes `TenderAgent` from `workflow.py`.

### `app/agents/workflow.py`
- Main LangGraph-based multi-step orchestrator (`TenderAgent`).
- Coordinates Agent1 -> Agent2 -> Agent3 flow and persistence handoffs.

### `app/agents/agent1.py`
- Agent 1: initial extraction from scraped markdown/content.
- Produces candidate tender entries.

### `app/agents/agent2.py`
- Agent 2: enrichment/detailing of extracted tenders.
- Adds deeper structured fields and refinement.

### `app/agents/agent3.py`
- Agent 3: notification composition/intelligence layer.
- Generates human-friendly email-ready summaries/alerts.

## 4) Important Notes About Current Codebase State

- There is overlap between legacy root modules and modular `app/` modules.
- File names repeat across layers (`scheduler.py`, `agents.py`, `scraper.py`, `email_service.py`, `config.py`, `models.py`).
- Route overlap also exists (`system.py` vs `email_settings.py` for email settings behavior).
- For most production-like usage, the `run.py` + `app/` path is the cleanest and most complete backend path.

## 5) End-to-End Backend Flow (App Path)

1. Scheduler tick starts in `app/services/scheduler.py`.
2. Active pages are fetched from `PageRepository`.
3. Each page is scraped using `app/services/scraper.py`.
4. Scraped markdown/content goes through `app/agents/workflow.py`:
   - Agent1 extracts tenders.
   - Agent2 enriches details.
   - Agent3 prepares intelligent communication output.
5. Results are persisted via repositories/models.
6. Email notifications are sent by `app/services/email_service.py`.
7. Crawl and notification outcomes are logged to DB.

## 6) Quick File Focus (If You Want to Read Core Logic First)

If you want the smallest set of files to understand the main backend quickly, start with:

1. `run.py`
2. `app/main.py`
3. `app/services/scheduler.py`
4. `app/services/scraper.py`
5. `app/agents/workflow.py`
6. `app/agents/agent1.py`
7. `app/agents/agent2.py`
8. `app/agents/agent3.py`
9. `app/services/email_service.py`
10. `app/repositories/tender_repository.py`

