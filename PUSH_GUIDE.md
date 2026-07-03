# Safe Push Guide (Code Only — Keep Databases Intact)

Quick steps for pushing changes between computers **without overwriting the other machine's database**.

## Golden rule

Push **code only**. Never commit:

- `tender_monitoring.db` (the live database)
- `.env` (secrets — already gitignored)

The other computer keeps its own database and `.env`.

## Push from this computer

```bash
# 1. Discard local DB changes so it never gets committed
git checkout -- tender_monitoring.db

# 2. Stage only the code (everything under app/)
git add app/

# 3. Double-check: tender_monitoring.db must NOT appear under "Changes to be committed"
git status

# 4. Commit and push
git commit -m "your message here"
git push
```

## Pull on the other computer

```bash
git pull
```

A plain `git pull` of code-only commits updates the `.py` files and **does not touch** that machine's `tender_monitoring.db` or `.env`.

> If the other machine ever shows a conflict on `tender_monitoring.db`, run `git checkout -- tender_monitoring.db` there to keep its own database, then pull again.

## Changing the crawl schedule (days per week)

`.env` is gitignored, so the value that travels via git is the **default** in `app/core/config.py`.

- Committed default (reaches other computer on pull): `app/core/config.py`
  - `CRAWL_SCHEDULE_WEEKDAYS` (e.g. `monday,wednesday,friday`)
  - `BACKUP_AFTER_EXTRACTION_WEEKDAYS` (keep aligned with the schedule)
- Local override (this machine only): `.env`
  - `CRAWL_SCHEDULE_WEEKDAYS=...`

After changing either, **restart the app/container** for it to take effect.

> An `.env` value always overrides the `config.py` default. If the other computer's `.env` sets `CRAWL_SCHEDULE_WEEKDAYS`, edit it there too — the pull alone won't change it.

## Permanently protect the database from git (optional, one-time)

```bash
git rm --cached tender_monitoring.db
echo "tender_monitoring.db" >> .gitignore
git commit -m "Stop tracking tender_monitoring.db"
```

After this, git ignores the DB on every machine and you can safely use `git add .`.
