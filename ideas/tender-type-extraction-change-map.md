# Tender Type and Extraction Change Map

This document lists where to update the codebase when changing:

1. the tender type taxonomy (currently centered around `esg` / `credit_rating` / `both`), and
2. the extracted tender fields (basic + detailed extraction schema).

---

## 1) Core backend (active stack) - required changes

### Agents and workflow

- `app/agents/agent1.py`
  - Hardcoded category logic and prompt output schema.
  - Basic extraction fields are defined and validated here.
- `app/agents/workflow.py`
  - Passes category keyword sets through the pipeline.
  - Routes processing and email composition by category.
  - Maps basic and detailed payloads between agents and repositories.
- `app/agents/agent2.py`
  - Defines detailed extraction schema (deadline, requirements, contact info, etc.).
  - Validation logic depends on current extracted field names.
- `app/agents/agent3.py`
  - Email generation references team category labels and field names from Agent 2.

### Models and repositories

- `app/models/tender.py`
  - Main DB schema for `Tender` and `DetailedTender`.
  - Update columns if extraction fields are added/renamed/removed.
- `app/models/keyword.py`
  - Keyword category model currently aligned with existing tender categories.
- `app/repositories/tender_repository.py`
  - Save/load mappings for extracted fields.
  - Category filtering and legacy `both` behavior.
- `app/repositories/keyword_repository.py`
  - Keyword retrieval by category used during extraction.

### Services

- `app/services/scheduler.py`
  - Fetches keyword sets by category and orchestrates processing.
  - Notification flow still depends on existing category names.
- `app/services/email_service.py`
  - Team routing and template/content generation by category.

### API routes

- `app/api/routes/tenders.py`
  - Query validation and stats are hardcoded to existing categories.
- `app/api/routes/keywords.py`
  - Category validation and CRUD assumptions.
- `app/api/routes/system.py`
  - Email/category validation paths use existing category names.

### Initialization

- `app/core/init_data.py`
  - Seeds category-specific default keywords and settings.

---

## 2) Frontend updates - required changes

- `react-frontend/src/types/index.ts`
  - Category union type and detailed field typings.
- `react-frontend/src/services/api.ts`
  - Request/response typing and category literals.
- `react-frontend/src/hooks/useApi.ts`
  - Stats and grouping currently split by ESG vs Credit.
- `react-frontend/src/components/TenderList.tsx`
  - Category filters, badges, labels, and detailed field rendering.
- `react-frontend/src/components/KeywordManager.tsx`
  - Category creation/filter UI currently fixed to two categories.
- `react-frontend/src/components/Dashboard.tsx`
  - Category-specific cards and counters.
- `react-frontend/src/components/Settings.tsx`
  - Category naming in team email settings.

---

## 3) Tools, docs, and scripts to align

- `database_inspector.py`
- `check_db.py`
- `test_api.py`
- `README.md`
- `BACKEND_AGENTS_DETAILED.md`

These should be updated so diagnostics and docs stay consistent with the new schema and taxonomy.

---

## 4) Legacy duplicate backend stack (update if still used)

If any team members still run root-level scripts, also update:

- `main.py`
- `agents.py`
- `scheduler.py`
- `models.py`
- `database.py`
- `config.py`

These files also contain category and extraction assumptions.

---

## Practical implementation order

1. Define new category enum and extraction schema.
2. Update `app/models/tender.py` and plan DB migration.
3. Update Agent 1 and Agent 2 schema/prompt/validation.
4. Update workflow + repository save/load mappings.
5. Update API validators and response contracts.
6. Update frontend types and UI filters/rendering.
7. Update scheduler/email routing logic.
8. Update diagnostics/docs/tests.

