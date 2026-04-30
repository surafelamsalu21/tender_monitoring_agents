# Authentication (`app/auth`)

Self-contained module for login, JWT sessions, and protecting APIs.

| Module | Role |
|--------|------|
| `security.py` | Password hashing (`pbkdf2_sha256`), JWT signing |
| `deps.py` | `OAuth2PasswordBearer`, `get_current_user` |
| `bootstrap.py` | Default admin creation, company email domain rules |
| `router.py` | `POST /login`, `GET /me`, `POST /change-password` |
| `admin_router.py` | `POST /admin/users` — super admin creates company users (temporary password; no email sent yet) |

## API summary (under `/api/v1`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/login` | No | Login; bootstraps default admin on first use |
| GET | `/auth/me` | Bearer | Current user |
| POST | `/auth/change-password` | Bearer | Body: `old_password`, `new_password` (min 8 chars) |
| POST | `/admin/users` | Bearer + super admin | Body: `email`, `password`, optional `full_name`, `role` in `viewer` / `analyst` / `admin` |

Company email domains: `ALLOWED_COMPANY_EMAIL_DOMAINS` in config (comma-separated).  
Default bootstrap account: `DEFAULT_ADMIN_EMAIL` / `DEFAULT_ADMIN_PASSWORD`.

## Automated tests

From project root (with venv activated). Run **two separate commands** — do not paste `# …` comments on the same line as `pip`, or pip may treat `#` as a package name.

```bash
.venv/bin/pip install pytest
.venv/bin/python -m pytest tests/test_auth_api.py -v
```

Tests use an isolated SQLite file per run (see `tests/conftest.py`).

## Manual checks (server running on port 8000)

1. Login: `POST /api/v1/auth/login` with JSON `email` + `password`.
2. Copy `access_token`; call `GET /api/v1/auth/me` with header `Authorization: Bearer <token>`.
3. Change password: `POST /api/v1/auth/change-password` with same header and JSON `old_password`, `new_password`.
4. As super admin: `POST /api/v1/admin/users` with JSON `email`, `password`, `role`.

Register the public auth router in `app/api/main.py` without a global auth dependency; other routers use `Depends(get_current_user)`.

The `User` model stays in `app/models/user.py` (shared ORM).
