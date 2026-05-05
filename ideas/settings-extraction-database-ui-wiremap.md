# Settings UI: extraction schedule & database management — wire map

Technical reference for the **Settings** page sections **Extraction Schedule** and **Database Management**: intended behavior, what is connected to the backend today, source of truth, and follow-up work if we want full functionality.

_Last reviewed against codebase paths as of authoring._

---

## 1. Context

These blocks live in the React app:

- [`react-frontend/src/components/Settings.tsx`](../react-frontend/src/components/Settings.tsx)

System status (counts + recent crawl activity) is loaded via:

- `apiService.getSystemStatus()` → `GET /api/v1/system/status`
- Handler: [`app/api/routes/system.py`](../app/api/routes/system.py) (`get_system_status`)

Automated crawl/extraction cadence is controlled by the **backend** scheduler:

- [`app/services/scheduler.py`](../app/services/scheduler.py) (`TenderScheduler`, `_periodic_task`)
- Interval: [`app/core/config.py`](../app/core/config.py) — `CRAWL_INTERVAL_HOURS` (env: `CRAWL_INTERVAL_HOURS`, default `3`)

The actual database file URL:

- Same config: `DATABASE_URL` (with optional normalization for relative SQLite paths in `Settings.resolve_sqlite_relative_to_project`)

---

## 2. Extraction Schedule

### 2.1 Intended UX

- User picks **extraction frequency** (e.g. every 3 / 6 / 12 / 24 hours).
- User clicks **Save Schedule** so the running system adopts the new cadence without editing `.env` manually (or with a clear persistence story).
- **Last Extraction** shows when the pipeline last ran (or equivalent), so ops can sanity-check activity.

### 2.2 Current implementation status

| UI element | Wired? | Notes |
|------------|--------|------|
| Frequency `<select>` | **No** | Static options only; no `value`/`onChange`, no state, no persistence. Changing the dropdown has **no effect** on the scheduler. |
| **Save Schedule** button | **No** | Plain `<button>` — no `onClick`, **no API** call. |
| **Last extraction** field | **Yes (read-only)** | Driven by `systemStatus.recent_activity[0].started_at` after status load. API returns recent `CrawlLog` rows ordered by `started_at` descending (`limit 5`). Display uses `new Date(...).toLocaleString()`. Represents **start time of the latest crawl log**, not necessarily a separate “extraction succeeded” semantic. |

### 2.3 Source of truth today

- Scheduler sleep interval: `settings.CRAWL_INTERVAL_HOURS * 3600` seconds (`scheduler.py`).
- Changing frequency **requires** changing configuration (typically `.env` / deployment env) **and restarting** the API process unless we add runtime reload or a persisted setting read each tick.

### 2.4 Follow-up ideas (later)

1. Persist schedule in DB or reuse env-only with documented “restart required”.
2. Add `PATCH /api/v1/system/schedule` (or similar) updating a stored value **and** either restarting/adjusting the asyncio task interval or documenting that restart is mandatory.
3. Bind `<select>` to `CRAWL_INTERVAL_HOURS` from status if we expose it on `GET /status` (today status does **not** return crawl interval).

---

## 3. Database Management

### 3.1 Intended UX

- **Database Location** reflects where the SQLite (or other) DB actually lives.
- **Backup Database** creates a backup artifact (file copy, dump, cloud upload — TBD).
- **Clean Old Records** removes or archives stale rows per policy (TBD: tenders, crawl logs, retention days).

### 3.2 Current implementation status

| UI element | Wired? | Notes |
|------------|--------|------|
| **Database Location** | **No** | Hardcoded string `./data/tender_monitoring.db` in `Settings.tsx`. Does **not** read `DATABASE_URL`. Production/dev may use `tender_monitoring.db` at project root or an absolute SQLite path after config normalization — UI can mislead. |
| **Backup Database** | **No** | No click handler; **no** backup endpoint located under `app/api`. |
| **Clean Old Records** | **No** | No handler; **no** purge/archive endpoint located under `app/api`. |

### 3.3 Follow-up ideas (later)

1. Extend `GET /api/v1/system/status` with a **`database_url_display`** field: safe subset only (e.g. filename + “SQLite”) or configurable allowlist — avoid leaking secrets in networked DB URLs.
2. Implement `POST /api/v1/system/database/backup` (super-admin only): stream or path response; enforce disk quotas and auth.
3. Implement `POST /api/v1/system/database/clean` with explicit retention rules and dry-run mode; audit log entries.

---

## 4. Quick verification checklist

When revisiting implementation:

- [ ] Frequency select reads initial value from API or documented env default.
- [ ] Save persists and scheduler interval updates (or server returns “restart required”).
- [ ] Last extraction label matches product language (crawl started vs extraction completed).
- [ ] DB path matches `settings.DATABASE_URL` resolution rules.
- [ ] Backup/Clean guarded by **`require_super_admin`** (or equivalent) and tested on SQLite + any prod DB.

---

## 5. Related code index

| Area | Path |
|------|------|
| Settings UI | `react-frontend/src/components/Settings.tsx` |
| System status API | `app/api/routes/system.py` (`GET /status`) |
| Scheduler | `app/services/scheduler.py`, `app/main.py` (lifespan) |
| Crawl logs model | `app/models/crawl_log.py` |
| Config | `app/core/config.py` (`CRAWL_INTERVAL_HOURS`, `DATABASE_URL`) |

This file is intentionally **ideas / backlog** only — no behavioral change unless we implement the follow-up sections above.
