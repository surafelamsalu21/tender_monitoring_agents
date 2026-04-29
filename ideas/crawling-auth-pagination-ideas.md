# Ideas: Authenticated Crawling and Pagination Strategy

## Why this note

Many tender and procurement sources require authentication, and many also use pagination or infinite listing pages.  
This note outlines a practical design approach for handling both in the Precise opportunity monitoring system.

## 1) Managing websites that require login

### A. Credential and secret management
- Never hardcode credentials in source code.
- Store credentials in environment variables or a proper secret manager.
- Keep only source metadata in DB; store secrets encrypted or by secret reference key.

### B. Source-level auth profiles
Define an auth profile per monitored source:
- `auth_type`: `none | form_login | cookie_session | token_api | sso_manual`
- `login_url`
- `username_secret_ref`
- `password_secret_ref`
- `mfa_required` (boolean)
- `session_ttl_minutes`
- `last_auth_status`

### C. Session reuse pattern
Use one login per source-run and reuse session cookies/tokens for all pages in that run:
1. authenticate once
2. save session in memory (or secure cache)
3. crawl listing + detail pages
4. refresh only when session expires/fails

### D. MFA/captcha handling
For hard-protected portals:
- support manual auth bootstrap (admin logs in once)
- save valid session artifact securely
- reuse until expiry
- raise an admin re-auth task when session fails

### E. Compliance and safety
- Respect source terms/policies and rate limits.
- Add audit logs for auth attempts and failures.
- Never write raw passwords/tokens to app logs.

## 2) Handling many pages and "next page" flow

### A. Per-source pagination configuration
Each source should declare a pagination strategy:
- `next_button` selector
- `page_query_param` (e.g. `?page=2`)
- `offset_limit` style
- `infinite_scroll`

Also include:
- `max_pages_per_run`
- `max_items_per_run`
- stop conditions (old date reached, no new links, duplicate threshold)

### B. Two-phase crawl model
1. **Listing phase**: walk paginated listings and collect opportunity links/IDs.
2. **Detail phase**: fetch each new detail page and extract full structured fields.

This scales better than deep extraction on every listing page in one pass.

### C. Deduplication keys
Use deterministic dedup keys:
- normalized URL, or
- `(source_id + external_opportunity_id)`, or
- fallback hash of `title + issuer + deadline`

### D. Incremental crawling checkpoints
Track source checkpoints:
- last seen publish date
- last seen external ID / cursor
- last processed page number

During each run:
- stop once data is older than checkpoint
- update checkpoint after successful completion

### E. Run guardrails
To avoid overload:
- cap total pages per run
- cap detail pages per run
- prioritize items by deadline + strategic fit
- queue overflow for next run

## 3) Suggested data model additions

### `auth_profiles`
- `id`
- `source_name`
- `auth_type`
- `login_url`
- `username_secret_ref`
- `password_secret_ref`
- `token_secret_ref` (optional)
- `mfa_required`
- `is_active`
- `last_auth_status`
- `last_authenticated_at`

### `source_pagination_config`
- `id`
- `source_name`
- `pagination_type`
- `next_selector`
- `page_param_name`
- `start_page`
- `max_pages_per_run`
- `max_items_per_run`
- `stop_on_duplicate_ratio`
- `is_active`

### `source_crawl_state`
- `id`
- `source_name`
- `last_checkpoint_cursor`
- `last_checkpoint_date`
- `last_page_processed`
- `last_run_started_at`
- `last_run_completed_at`
- `last_run_status`
- `last_error`

## 4) MVP implementation order

1. Add auth profile and pagination config schemas.
2. Build authenticated session manager.
3. Implement listing pagination walker.
4. Add dedup + checkpoint logic.
5. Add admin controls for auth/pagination per source.
6. Add monitoring dashboard widgets (auth health, source freshness, crawl backlog).

## 5) Design principle

Do not treat all sources as identical.  
Model each source with explicit authentication and pagination strategies, then run a common orchestrator around those configurations.
