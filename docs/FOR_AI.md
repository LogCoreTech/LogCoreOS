# LogCoreOS — Comprehensive AI Agent Guide

This document is the authoritative reference for any AI coding agent (Claude Code, Copilot, Cursor, etc.) working on this codebase.

---

## Project Summary

LogCoreOS is a self-hosted, open-source, AI-native **life operating system**. It gives individuals and families a private Brain (Markdown + JSON files) that an AI layer can read and act on. There is no database — the filesystem IS the database.

**Stack:** Python 3.11 / FastAPI backend · React 18 / Vite / Tailwind frontend · Docker Compose

---

## Repository Layout

```
/
├── app/
│   ├── backend/          # FastAPI application
│   │   ├── main.py       # App factory, router registration, startup checks
│   │   ├── config.py     # Pydantic settings (reads from docker/.env)
│   │   ├── routers/      # One file per feature area
│   │   ├── services/     # Business logic (no HTTP here)
│   │   ├── scheduler.py  # APScheduler jobs (recurring, digests, etc.)
│   │   └── tests/        # pytest test suite
│   └── frontend/         # Vite + React SPA
│       └── src/
│           ├── pages/    # One component per route
│           ├── components/
│           └── lib/      # api.js, auth.jsx, constants.js
├── brain/                # Starter Brain template (mounted at /data/brain in Docker)
├── docker/               # docker-compose.yml, .env.example, nginx config
└── docs/                 # Architecture, API reference, AI guide (this file)
```

---

## Core Concepts

### The Brain
All user data lives in `brain/USERS/{UserName}/` as Markdown and JSON files. There is no database. This makes data portable, human-readable, and AI-friendly.

Key files per user:
- `Profile.md` — life priorities, goals, values
- `Long_Term_Memory.md` / `Short_Term_Memory.md` — AI context
- `Tasks/tasks.json` — active tasks
- `Tasks/tasks_history.json` — completed tasks
- `Tasks/daily_override.json` — today's category priority override

System files (not user-specific):
- `brain/_system/auth.json` — user accounts, JWT revocations, runtime settings
- `brain/AGENTS.md`, `brain/SOUL.md`, `brain/USERS.md` — AI system-level context

### Atomic Writes
**Always** use `write_json()` and `write_markdown()` from `services/file_service.py`. These use `tempfile.mkstemp` + `os.replace()` for atomic POSIX writes. Never use `open(..., 'w')` directly for Brain files.

### JWT Auth
- Tokens carry `sub` (user ID), `jti` (unique token ID), `exp`, `name`, `role`
- Logout revokes the JTI in memory (`_revoked_jtis` set) and persists to `auth.json`
- On startup, `_bootstrap_revoked_jtis()` reloads the JTI blacklist from disk
- `get_current_user()` dependency attaches `_jti` and `_exp` to the user dict for logout

### Module System
The module registry lives in `app/frontend/src/lib/constants.js` (`ALL_MODULES`). Each module has an `id` that matches the string used in `require_module(module_id)` on the backend. When you add a new module, update both.

Backend enforcement: `require_module("module_id")` is a FastAPI dependency factory that returns 403 if the module is in `user["disabled_modules"]`.

### API Versioning
All routes are under `/api/v1/`. The frontend base is `const BASE = '/api/v1'` in `lib/api.js`. When adding new routes, always use the v1 prefix.

---

## Development Setup

```bash
# Backend (from app/backend/)
pip install -r requirements.txt
pip install -r ../../requirements-dev.txt  # dev deps (pytest etc.)
uvicorn main:app --reload --port 8000

# Frontend (from app/frontend/)
npm install
npm run dev

# Run tests (from app/backend/)
pytest tests/ -v
```

For full Docker stack:
```bash
cp docker/.env.example docker/.env
# Edit docker/.env — set SECRET_KEY at minimum
docker compose -f docker/docker-compose.yml up --build
```

---

## Backend Conventions

### Routers
- One file per feature area in `routers/`
- Apply `require_module()` at the router level: `_require_tasks = require_module("tasks")`
- Apply rate limiting where appropriate: `_limit = rate_limit(n, window_seconds)`
- Use Pydantic models for all request bodies — validate at the boundary

### Services
- Services contain all business logic; routers are thin HTTP wrappers
- Services never import from routers
- `auth_service` uses `_auth_lock` (threading.Lock) for all read-modify-write operations on auth.json

### Path Safety
- User names are validated against `_NAME_RE` at creation time to prevent path traversal
- The brain router has additional `_resolve()` path validation
- Never construct paths from user input without going through `user_path(name)` from `file_service.py`

### Error Handling
- Raise `HTTPException` with appropriate status codes in routers
- Raise `ValueError` in services; routers catch and convert to 400
- Log errors at `logger.error()` or `logger.warning()` — never swallow silently

---

## Frontend Conventions

### API calls
All API calls go through `lib/api.js`. The `request()` function handles 401 by clearing localStorage and redirecting to `/login`. Add new endpoints to the appropriate export object; never `fetch()` directly in components.

### Auth state
`useAuth()` returns `{ user, login, logout, updateUserField }`. `user` has `{ name, role, disabledModules, timezone }`. Use `updateUserField(key, value)` for immediate optimistic updates after a PATCH /me succeeds.

### Admin-only pages
The `/admin` route is wrapped in `<AdminOnly>` which redirects non-admins to `/`. Admin UI lives in `pages/Admin.jsx`; the admin section was intentionally removed from `pages/Settings.jsx`.

### Styling
Tailwind classes only. Custom classes (`btn-primary`, `btn-ghost`, `input`, `card`, `badge`) are defined in `src/index.css`. The design system uses:
- `charcoal-*` for neutral grays
- `orange-500` as the brand accent
- Dark mode via `dark:` prefix (class-based, not system preference)

---

## Security Rules

1. **Never trust user input as file paths.** Always resolve through `user_path()`.
2. **Never build SQL queries with string concat.** (There's no SQL, but the principle applies to any query language.)
3. **Brain file content injected into AI prompts must be wrapped in `<brain_data>` XML tags** to prevent prompt injection. See `routers/chat.py:_safe()`.
4. **`trust_proxy_headers`** defaults to `False`. Only enable if you trust the upstream proxy.
5. **`SECRET_KEY`** must be changed from the default before any network exposure.
6. **Passwords** are bcrypt-hashed. Never store or log plaintext passwords.

---

## Testing

Tests live in `app/backend/tests/`. Run with `pytest tests/ -v` from `app/backend/`.

The `brain` fixture in `conftest.py` patches `settings.brain_path` to an isolated temp directory. All tests that touch the filesystem should use this fixture.

Coverage targets:
- `recurring_service._next_due` — exhaustive date arithmetic including leap years
- `priority_service.score_task` — scoring formula
- `auth_service` — user CRUD, token operations, revocation
- `task_service` — task CRUD, pagination

---

## Scheduler

APScheduler runs 4 jobs:
1. `00:01` — Process recurring tasks (advance due dates, manage streaks)
2. Morning digest — Push ntfy notification with top tasks
3. `19:00` — Overdue task check and reminder
4. Weekly review (Sunday) — Summary digest

All times are in `settings.scheduler_timezone` (IANA string, validated at startup).

---

## Adding a New Module

1. Add entry to `ALL_MODULES` in `app/frontend/src/lib/constants.js`
2. Create `app/frontend/src/pages/NewModule.jsx`
3. Add route in `app/frontend/src/App.jsx`
4. Create `app/backend/routers/new_module.py` with `_require_new = require_module("new_module_id")`
5. Register router in `app/backend/main.py` under `/api/v1/new_module`
6. Add API methods to `app/frontend/src/lib/api.js`

---

## Agent Skills

Reusable agent tasks live in `agent/skills/`. Each skill gets its own folder:

```
agent/skills/<skill-name>/
├── <skill-name>.md   — AI instructions: what to do, how to interpret output, output format
└── <script>.sh       — shell scripts for the automatable parts (optional but preferred)
```

**Rule:** one folder per skill. The `.md` file drives the AI; scripts handle anything a shell can verify faster than a model. An agent runs the scripts first, then uses the output as context for the `.md` instructions.

To add a new skill: create the folder, add the `.md`, add any scripts, register it in `agent/README.md`.

---

## Known Limitations / Future Work

See `docs/PROJECT_DOCS.md` for the full roadmap. Current known gaps:

- **No database migration story** — schema changes require manual file updates (tracked in PROJECT_DOCS.md)
- **Single-worker only** — file locks are in-process; multi-worker uvicorn would need distributed locking
- **No email verification** — user emails are trusted as-is
- **Brain files are not end-to-end encrypted** — the server can read all user data
- **AI model is hard-coded to Anthropic** — `services/ai_provider.py` has the abstraction but only one provider is wired
