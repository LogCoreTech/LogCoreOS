# LogCoreOS — AI Agent Guide

This is the single source of truth for any AI coding agent (Claude Code, Copilot, Cursor, etc.) working on this codebase.

**Meta-rule:** When you make a change that affects architecture, conventions, file layout, security rules, or known gotchas — update this file in the same commit.

---

## Project Summary

LogCoreOS is a self-hosted, open-source, AI-native life operating system. It gives individuals and families a private Brain (Markdown + JSON files) that an AI layer can read and act on. There is no database — the filesystem IS the database.

**Stack:** Python 3.12 / FastAPI · React 18 / Vite / Tailwind CSS · Docker Compose · ntfy (push notifications)

---

## Repository Map

```
LogCoreOS/
│
├── CLAUDE.md                     → thin pointer to this file
├── README.md                     → user-facing quick start (do not move — it's for humans)
├── launch.sh                     → one-command startup: builds frontend, generates .env, starts Docker
├── requirements-dev.txt          → dev/test deps (pytest, etc.)
│
├── app/
│   ├── backend/
│   │   ├── main.py               → app factory, router registration, CORS middleware, static file serving
│   │   ├── config.py             → all env vars via Pydantic Settings (reads docker/.env)
│   │   ├── scheduler.py          → 4 APScheduler jobs (recurring, digest, overdue, weekly)
│   │   ├── routers/
│   │   │   ├── auth.py           → login, register, logout, /me, admin users, AI/search/hosting settings
│   │   │   ├── tasks.py          → task CRUD, top3, scored, history
│   │   │   ├── chat.py           → AI chat with full Brain context injection + tool use
│   │   │   ├── brain.py          → Brain file read/write (path-validated, admin-only writes)
│   │   │   ├── notes.py          → notes module (files + folders CRUD)
│   │   │   ├── journal.py        → journal module (daily entries by date)
│   │   │   ├── calendar.py       → calendar module (tasks view + events CRUD)
│   │   │   ├── priorities.py     → priority order + daily override
│   │   │   ├── setup.py          → first-time setup wizard
│   │   │   ├── health.py         → GET /health (no auth, used by Docker healthcheck)
│   │   │   ├── export.py         → brain zip download
│   │   │   ├── shared.py         → shared task/event public links (household pool)
│   │   │   ├── push.py           → ntfy push notification subscription
│   │   │   ├── suggestions.py    → proactive AI suggestion engine + notification inbox
│   │   │   └── profile.py        → user Profile.md read/write
│   │   ├── services/
│   │   │   ├── file_service.py   → atomic Brain file reads/writes — ALWAYS use this, never open(...,'w')
│   │   │   ├── auth_service.py   → user CRUD, JWT create/verify, bcrypt, JTI revocation
│   │   │   ├── ai_provider.py    → AI abstraction layer (Anthropic; swap via AI_PROVIDER env)
│   │   │   ├── task_service.py   → task business logic
│   │   │   ├── priority_service.py  → life priority scoring formula
│   │   │   ├── hosting_service.py   → runtime hosting config (reads brain/hosting.json at request time)
│   │   │   ├── rate_limiter.py   → IP-based rate limiting (respects trust_proxy_headers)
│   │   │   ├── recurring_service.py → recurring task date advancement + streak logic
│   │   │   ├── notification_service.py → ntfy push delivery
│   │   │   └── suggestion_service.py   → proactive suggestion generation
│   │   ├── migrations/
│   │   │   └── runner.py         → runs pending Brain schema migrations at startup
│   │   └── tests/                → pytest suite (see Testing section)
│   │
│   └── frontend/
│       └── src/
│           ├── lib/
│           │   ├── api.js         → ALL API calls go here — never fetch() directly in components
│           │   ├── auth.jsx       → useAuth() hook + AuthProvider
│           │   └── constants.js   → ALL_MODULES registry (must match backend require_module IDs)
│           ├── pages/
│           │   ├── Home.jsx       → dashboard (top3 tasks, priority override)
│           │   ├── Tasks.jsx      → task management
│           │   ├── Chat.jsx       → AI chat interface
│           │   ├── Admin.jsx      → admin panel (users, AI settings, web search, hosting)
│           │   ├── Settings.jsx   → user settings (timezone, session, notifications)
│           │   ├── Notes.jsx      → notes module
│           │   ├── Journal.jsx    → journal module
│           │   ├── Calendar.jsx   → calendar UI (backend complete; UI in progress)
│           │   ├── Login.jsx      → login + register
│           │   └── Setup.jsx      → first-time setup wizard
│           └── components/        → shared UI components
│
├── brain/                         → starter Brain (mounted at /data/brain in Docker)
│   ├── AGENTS.md                  → AI boot protocol (in-app AI session start order)
│   ├── SOUL.md                    → AI personality and communication principles
│   ├── USERS.md                   → user registry and selection logic
│   ├── MEMORY_MAP.md              → navigation index for all Brain files
│   ├── USERS/_template/           → copied for each new user at setup
│   ├── skills/life-priorities/    → task scoring + recurring task logic
│   ├── _system/auth.json          → user accounts, JTI blacklist (NEVER commit; volume-mounted)
│   └── hosting.json               → runtime hosting config written by Admin → Hosting panel
│
├── docker/
│   ├── docker-compose.yml         → service definitions (app + ntfy)
│   ├── .env.example               → env var template
│   ├── .env                       → live secrets (NEVER commit; generated by launch.sh)
│   └── backup.sh                  → Brain backup script (keeps 30 most recent)
│
├── agent/
│   └── skills/                    → reusable agent skills for in-app AI
│       ├── run-tests/             → run pytest + structured GREEN/RED report
│       ├── diagnose/              → full security/architecture audit
│       └── run-agent/             → (see folder)
│
└── docs/
    ├── AGENTS.md                  → THIS FILE
    ├── API.md                     → REST API endpoint reference
    ├── PROJECT_DOCS.md            → system architecture + development roadmap
    └── BACKLOG.md                 → deferred features and open bugs
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
- `brain/hosting.json` — runtime hosting config (written by Admin → Hosting; not in git)

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
All routes are under `/api/v1/`. The frontend base is `const BASE = '/api/v1'` in `lib/api.js`. Always use the v1 prefix.

### Dynamic CORS
`DynamicCORSMiddleware` in `main.py` reads the allowed origin from `brain/hosting.json` at request time (via `hosting_service.effective_domain_url()`). When no domain is configured it falls back to the `ALLOWED_ORIGINS` env var. It always reflects the request `Origin` header — never sends `"*"` — so credentials work correctly per the CORS spec.

### Runtime Hosting Config
`services/hosting_service.py` reads `brain/hosting.json` at every request to determine `cookie_secure`, `trust_proxy_headers`, and `domain_url`. This means the Admin → Hosting panel takes effect immediately without a container restart. The env vars are the default values; `hosting.json` overrides them at runtime.

---

## Development Setup

```bash
# Backend (from app/backend/)
pip install -r requirements.txt
pip install -r ../../requirements-dev.txt
uvicorn main:app --reload --port 8000

# Frontend (from app/frontend/)
npm install
npm run dev

# Run tests (from app/backend/)
pytest tests/ -v
```

Full Docker stack (canonical):
```bash
bash launch.sh               # first-time or normal restart
bash launch.sh --skip-build  # skip npm build if dist/ already exists
bash launch.sh --reconfigure # reset docker/.env
```

---

## Backend Conventions

### Routers
- One file per feature area in `routers/`
- Apply `require_module()` at the router level: `_require_tasks = require_module("tasks")`
- Apply rate limiting where appropriate: `_limit = rate_limit(n, window_seconds)`
- Use Pydantic models for all request bodies — validate at the boundary
- Raise `HTTPException` with appropriate status codes; never let unhandled exceptions surface

### Services
- Services contain all business logic; routers are thin HTTP wrappers
- Services never import from routers
- `auth_service` uses `_auth_lock` (threading.Lock) for all read-modify-write operations on `auth.json`

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

### API Calls
All API calls go through `lib/api.js`. The `request()` function handles 401 by clearing localStorage and redirecting to `/login`. Add new endpoints to the appropriate export object in `api.js`; never `fetch()` directly in components.

### Auth State
`useAuth()` returns `{ user, login, logout, updateUserField }`. `user` has `{ name, role, disabledModules, timezone }`. Use `updateUserField(key, value)` for immediate optimistic updates after a successful PATCH /me.

### Admin-Only Pages
The `/admin` route is wrapped in `<AdminOnly>` which redirects non-admins to `/`. Admin UI lives in `pages/Admin.jsx`. The admin section was intentionally removed from `pages/Settings.jsx`.

### Styling
Tailwind classes only. Custom classes (`btn-primary`, `btn-ghost`, `input`, `card`, `badge`) are defined in `src/index.css`. Design system:
- `charcoal-*` for neutral grays
- `orange-500` as the brand accent
- Dark mode via `dark:` prefix (class-based, not system preference)
- No inline `style={}` unless strictly necessary
- No `console.log` in committed code

### Code Style (Python)
- PEP 8. No line longer than 100 chars.
- Type annotations on all public functions.
- No bare `except:` — catch specific exceptions.
- All file writes go through `write_json()` / `write_markdown()`.

### Commit Messages
Imperative mood, present tense:
- `feat: add recurring task streak reset`
- `fix: resolve leap year bug in recurring scheduler`
- `docs: update AGENTS.md with hosting rules`

---

## Security Rules

1. **Never trust user input as file paths.** Always resolve through `user_path()`.
2. **Brain file content injected into AI prompts must be wrapped in `<brain_data>` XML tags** to prevent prompt injection. See `routers/chat.py:_safe()`.
3. **`trust_proxy_headers`** defaults to `False`. Only enable when there is a trusted reverse proxy in front of the app.
4. **`SECRET_KEY`** must be changed from the default before any network exposure. `launch.sh` generates one automatically.
5. **Passwords** are bcrypt-hashed. Never store or log plaintext passwords.
6. **`brain/_system/auth.json` and `docker/.env` must never be committed.** Both are in `.gitignore`.
7. **`cookie_secure`** should be `true` in any HTTPS deployment. The Admin → Hosting panel sets this at runtime.

---

## Testing

Tests live in `app/backend/tests/`. Run with `pytest tests/ -v` from `app/backend/`.

The `brain` fixture in `conftest.py` patches `settings.brain_path` to an isolated temp directory. All tests that touch the filesystem must use this fixture.

Coverage targets:
- `recurring_service._next_due` — exhaustive date arithmetic including leap years
- `priority_service.score_task` — scoring formula
- `auth_service` — user CRUD, token operations, revocation
- `task_service` — task CRUD, pagination

Run tests before committing any backend change.

---

## Scheduler

APScheduler runs 4 jobs (all times in `settings.scheduler_timezone`):

| Job | Schedule | What it does |
|-----|----------|--------------|
| Recurring processor | Nightly 00:01 | Advances due dates, resets broken streaks |
| Morning digest | Configurable (default 06:00) | Sends top-3 tasks via ntfy |
| Overdue check | Configurable (default 19:00) | Alerts on overdue tasks |
| Weekly review | Sunday 19:00 | Summary of completed tasks by category |

Timezone is set via `SCHEDULER_TIMEZONE` env var (IANA string, validated at startup).

---

## Adding a New Module

1. Add entry to `ALL_MODULES` in `app/frontend/src/lib/constants.js`
2. Create `app/frontend/src/pages/NewModule.jsx`
3. Add route in `app/frontend/src/App.jsx`
4. Create `app/backend/routers/new_module.py` with `_require_new = require_module("new_module_id")`
5. Register router in `app/backend/main.py` under `/api/v1/new_module`
6. Add API methods to `app/frontend/src/lib/api.js`
7. Update this file if the module introduces new conventions or file layout

---

## Agent Skills

Reusable agent tasks live in `agent/skills/`. Each skill gets its own folder:

```
agent/skills/<skill-name>/
├── <skill-name>.md   — AI instructions: what to do, how to interpret output, output format
└── <script>.sh       — shell scripts for the automatable parts (optional but preferred)
```

The `.md` file drives the AI; scripts handle anything a shell can verify faster than a model. Run the scripts first, then pass the output as context for the `.md` instructions.

| Skill | When to use |
|-------|-------------|
| `run-tests` | After any backend change, before committing |
| `diagnose` | Before a release or for a full health check |

To add a new skill: create the folder, add the `.md`, add any scripts, register it in `agent/README.md`.

---

## Known Gotchas

These are lessons learned from working on this project. Do not repeat these mistakes.

**Docker volume path for frontend dist:**
The backend resolves the frontend dist as `Path(__file__).parent.parent / "frontend" / "dist"`. Since `main.py` is at `/app/main.py` inside the container, `parent.parent` is `/`. The volume mount in `docker-compose.yml` must be:
```yaml
- ../app/frontend/dist:/frontend/dist   # correct
# NOT: ../app/frontend/dist:/app/frontend/dist  (this breaks static file serving)
```

**Health check URL:**
The correct health check path is `/api/v1/health`. The old path `/api/health` does not exist.

**Docker socket permissions:**
The app user must be in the `docker` group to run Docker commands. After adding:
```bash
sudo usermod -aG docker <username>
```
The user must log out and back in (or run `newgrp docker`) for the change to take effect.

**nvm and Node.js:**
nvm is a version manager — installing nvm does not install Node.js. You must run `nvm install <version>` separately. Node.js is loaded into PATH via `.bashrc`; open a new terminal or source `.bashrc` before running `launch.sh`.

**Runtime hosting config vs env vars:**
`cookie_secure` and `trust_proxy_headers` can be set in `docker/.env` (static defaults) or overridden at runtime by the Admin → Hosting panel (written to `brain/hosting.json`). The runtime value always wins. Use `hosting_service.effective_cookie_secure()` and `hosting_service.effective_trust_proxy_headers()` — never read `settings.*` directly in code that serves requests.

---

## Known Limitations / Future Work

See `docs/PROJECT_DOCS.md` for the full roadmap. Current known gaps:

- **Calendar UI** — backend and events CRUD are complete; the frontend UI is not yet built (tracked in `docs/BACKLOG.md`)
- **No database migration story** — Brain schema changes require manual file updates
- **Single-worker only** — file locks are in-process; multi-worker uvicorn would need distributed locking
- **No email verification** — user emails are trusted as-is
- **Brain files are not end-to-end encrypted** — the server can read all user data
- **AI provider abstraction** — `services/ai_provider.py` has the abstraction layer; only Anthropic is wired (Phase 6 adds more providers)
