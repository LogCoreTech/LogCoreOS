# LogCoreOS — AI Agent Guide

This file is the single source of truth for any AI agent working in this codebase.
All provider-specific files (CLAUDE.md, etc.) are thin redirects here.

**Meta-rule:** When you make a change that affects architecture, conventions, file layout, or known gotchas — update the appropriate docs file in the same commit.

---

## 1. Session Start — Read These First

Before doing anything else, read in this order:

1. `docs/SOUL.md` — who you are and what you protect
2. `docs/MEMORY.md` — stable project knowledge, design rules, and known gotchas
3. `docs/TASKS.md` — current work queue and active tasks
4. `docs/MAP.md` — navigation index for all files in this repo
5. `docs/PROJECT.md` — architecture, tech stack, and roadmap

Don't ask permission. Just do it.

**For Claude Code:** `docs/hooks/docs_loader.sh` handles steps 1–3 + this file automatically via a UserPromptSubmit hook.
**For other AI providers:** Read the files above manually in order.

---

## 2. Memory — How to Keep It Updated

**The rule: write it down. Files survive session restarts. Memory doesn't.**

| When this happens | Do this |
|---|---|
| A design decision is made | Update `docs/MEMORY.md` |
| New stable knowledge about the stack | Update `docs/MEMORY.md` |
| A task is added, completed, or reprioritized | Update `docs/TASKS.md` |
| Real work is done in a session | Update `docs/Daily Notes/YYYY-MM-DD.md` (create if missing) |
| Architecture or roadmap changes | Update `docs/PROJECT.md` |
| A new file or folder is added to the repo | Update `docs/MAP.md` |
| A mistake or gotcha is discovered | Add it to `docs/MEMORY.md` under Known Gotchas |

---

## 3. Daily Notes

Location: `docs/Daily Notes/YYYY-MM-DD.md`

- Create one per session day.
- Log what was worked on, decisions made, and follow-up items. Structured summary — not a transcript.
- At the start of each new session, read the previous daily note. Pull anything still relevant into `docs/MEMORY.md` or `docs/TASKS.md`, then leave the note as-is for the record.

---

## 4. End-of-Turn Memory Check

After every turn where real work was done, check each item:

1. `docs/TASKS.md` — mark completed tasks done; add new tasks surfaced this turn
2. `docs/MEMORY.md` — update if design decisions or stable facts changed
3. `docs/Daily Notes/YYYY-MM-DD.md` — update if real work was done; create if missing

Skip only if the turn was purely Q&A — no files changed, no decisions made. After updating (or skipping), respond with one line: what you updated or `Q&A only, skipped.`

**For Claude Code:** `docs/hooks/docs_reminder.sh` prompts this automatically via a Stop hook.

---

## 5. Git Workflow

```bash
GIT_SSH_COMMAND="ssh -i /home/logcore/.ssh/logcore_github" git push origin master
```

Commit message prefixes (imperative mood, present tense):
- `feat:` new feature or capability
- `fix:` bug fix
- `docs:` documentation only
- `chore:` tooling, config, scripts

---

## 6. Safety

- Never run destructive commands without confirming first
- Never commit `docker/.env`, `brain/_system/auth.json`, or any secrets
- `docs/hooks/safety_check.sh` blocks the most dangerous commands automatically via a PreToolUse hook

---

## Project Summary

LogCoreOS is a self-hosted, open-source, AI-native life operating system. It gives individuals and families a private Brain (Markdown + JSON files) that an AI layer can read and act on. There is no database — the filesystem IS the database.

**Stack:** Python 3.12 / FastAPI · React 18 / Vite / Tailwind CSS · Docker Compose · ntfy (push notifications)

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
- `Chats/YYYY-MM-DD_HH-MM-SS.md` — auto-saved chat archives

System files (not user-specific):
- `brain/_system/auth.json` — user accounts, JWT revocations, runtime settings
- `brain/_system/features.json` — feature flags + custom role definitions
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

Valid module IDs: `dashboard`, `tasks`, `calendar`, `household`, `notes`, `journal`, `chat`

### Feature Roles
Feature roles (custom, e.g. `cleaner`, `nanny`) control which modules are visible per user. Separate from auth roles (`admin`, `member`, `guest`). Stored in `brain/_system/features.json`. `guest` is the default for new users. `member` is the internal fallback. Both are protected built-in roles.

`get_effective_disabled(feature_role, user_disabled_modules)` in `services/features_service.py` resolves the union of role-level disables and per-user disables.

### Web Push
Push notifications use the Web Push API with VAPID keypair stored in `brain/_system/vapid_keys.json` (auto-generated on first startup). Subscriptions are stored per-user in the Brain. The internal ntfy service (`http://ntfy:80`) is used for server-initiated push. `push_service.py` handles subscription management and delivery.

### Export
Brain zip download is at `GET /api/v1/user/export` (note: router is mounted at `/api/v1/user`, not `/api/v1/export`). Returns a zip of the user's entire Brain folder.

### Suggestions
`suggestions_service.py` manages proactive AI suggestions: `daily_digest`, `overdue_alert`, `weekly_review`, `goal_drift`, and any user-defined custom suggestions. Each suggestion type generates an AI-crafted notification. Custom suggestions have configurable schedules (daily/weekly/interval) and are registered as live APScheduler jobs.

### API Versioning
All routes are under `/api/v1/`. The frontend base is `const BASE = '/api/v1'` in `lib/api.js`. Always use the v1 prefix.

### Dynamic CORS
`DynamicCORSMiddleware` in `main.py` reads the allowed origin from `brain/hosting.json` at request time (via `hosting_service.effective_domain_url()`). When no domain is configured it falls back to the `ALLOWED_ORIGINS` env var. It always reflects the request `Origin` header — never sends `"*"` — so credentials work correctly per the CORS spec.

### Runtime Hosting Config
`services/hosting_service.py` reads `brain/hosting.json` at every request to determine `cookie_secure`, `trust_proxy_headers`, and `domain_url`. This means the Admin → Hosting panel takes effect immediately without a container restart. The env vars are the default values; `hosting.json` overrides them at runtime.

### Chat System

The AI chat feature (`routers/chat.py` + `services/agent_service.py`) supports three modes:

- **Plan mode** — AI proposes a structured plan before executing. User approves or redirects.
- **Auto mode** — AI executes directly using available tools (read Brain files, write tasks, search notes, etc.).
- **Research mode** — AI uses web search via Tavily (`web_search_service.py`) in addition to Brain context.

The agent in `agent_service.py` runs a tool registry with safety guardrails. Tools include: read/write Brain files, task management, notes management, profile access, journal access, web search. Thoughts and tool calls are streamed back as a step trace visible in the UI.

**Chat archive storage:** `brain/USERS/{name}/Chats/YYYY-MM-DD_HH-MM-SS.md`

**Auto-save behavior (frontend):**
- Every chat is automatically saved 1.5 s after the AI responds (debounced `useEffect` on `messages` + `loading`).
- The first user message (truncated to 60 chars) becomes the auto-generated title.
- `continuedFromFile` state `{ filename, title }` tracks the current archive file so continued edits overwrite the same file instead of creating duplicates.

**API endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/chat` | Send a message; returns streamed response with step trace |
| `POST` | `/api/v1/chat/save` | Create or overwrite a chat archive. Body: `{ history, name?, filename? }`. Returns `{ filename, title }`. |
| `GET` | `/api/v1/chat/saved` | List all `.md` files in the user's Chats folder, newest first. |
| `DELETE` | `/api/v1/chat/saved/{filename}` | Delete a saved chat. |
| `POST` | `/api/v1/chat/save-memory` | Extract and save memory from a conversation |

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
bash launch.sh                  # first-time or normal restart
bash launch.sh --install-deps   # auto-install prerequisites (Linux only), then launch
bash launch.sh --skip-build     # skip npm build if dist/ already exists
bash launch.sh --reconfigure    # reset docker/.env
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
`useAuth()` returns `{ user, login, logout, updateUserField }`. `user` has `{ name, role, disabledModules, timezone, accentColor, darkMode, background, density, cornerStyle }`. Use `updateUserField(key, value)` for immediate optimistic updates after a successful PATCH /me.

### Pages
14 pages in `pages/`: `Dashboard.jsx`, `Tasks.jsx`, `Goals.jsx`, `Chat.jsx`, `Calendar.jsx`, `Household.jsx`, `Notes.jsx`, `Journal.jsx`, `Brain.jsx`, `Profile.jsx`, `Admin.jsx`, `Settings.jsx`, `Login.jsx`, `Setup.jsx`.

### Admin-Only Pages
The `/admin` route is wrapped in `<AdminOnly>` which redirects non-admins to `/`. Admin UI lives in `pages/Admin.jsx`. Render order: UsersCard → RegistrationCard → RolesCard → AiProviderCard → WebSearchCard → HostingCard → InfisicalCard.

### Styling
Tailwind classes only. Custom classes (`btn-primary`, `btn-ghost`, `input`, `card`, `badge`) are defined in `src/index.css`. Design system:
- `charcoal-*` for neutral grays
- `orange-500` / `orange-400` / `orange-600` as the brand accent — CSS variable-backed, not hardcoded. Tailwind's orange shades are remapped in `tailwind.config.js` to `rgb(var(--accent-500) / <alpha-value>)`.
- Dark mode via `dark:` prefix (class-based). The `dark` class is applied to `<html>` by `applyDarkMode()` in `lib/theme.js`. Supports `system`, `light`, `dark` modes.
- No inline `style={}` unless strictly necessary.
- No `console.log` in committed code.

### Theme System (`lib/theme.js`)
All runtime theming is handled by `applyAccentColor()`, `applyDarkMode()`, `applyBackground()`, `applyDensity()`, and `applyCornerStyle()`. These write CSS variables to `:root` / `<html>`.

**FOUC prevention:** `main.jsx` runs a synchronous IIFE before `ReactDOM.createRoot` that reads `localStorage.lc_user` and applies all CSS variables so the correct theme is set before React renders.

### Code Style (Python)
- PEP 8. No line longer than 100 chars.
- Type annotations on all public functions.
- No bare `except:` — catch specific exceptions.
- All file writes go through `write_json()` / `write_markdown()`.

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

APScheduler runs 7 fixed jobs plus dynamic per-user custom jobs (all times in `settings.scheduler_timezone`):

| Job | Schedule | What it does |
|-----|----------|--------------|
| Recurring processor | Nightly 00:01 | Archives yesterday's done non-recurring tasks → `tasks_history.json`; advances recurring task due dates; resets broken streaks |
| Morning digest | Configurable (default 06:00) | Runs `daily_digest` suggestion for each user |
| Overdue check | Configurable (default 19:00) | Runs `overdue_alert` suggestion for each user |
| Weekly review | Sunday 19:00 | Runs `weekly_review` suggestion for each user |
| Goal drift | Daily 19:30 | Runs `goal_drift` suggestion for each user |
| JTI cleanup | Nightly 03:00 | Removes expired revoked JWT token IDs from `auth.json` |
| Custom jobs | User-configured (daily/weekly/interval) | Per-user custom suggestion schedules registered dynamically via `add_custom_job()` |

Custom jobs are registered at startup via `_load_custom_jobs()` (reads all enabled custom suggestions across all users) and dynamically via `add_custom_job(user_name, suggestion)` / `remove_custom_job(user_name, suggestion_id)` when the user adds or deletes a custom suggestion.

### Task Lifecycle (done tasks)

Non-recurring tasks marked **done** stay in `tasks.json` until the 00:01 nightly job runs. At that point any task with `status == "done"`, `type != "recurring"`, and `completed_at` date earlier than today is moved to `tasks_history.json`.

Recurring tasks are **never** archived — they stay in `tasks.json` and have their `due_date` / `last_completed_date` advanced by the nightly job.

---

## Adding a New Module

1. Add entry to `ALL_MODULES` in `app/frontend/src/lib/constants.js`
2. Create `app/frontend/src/pages/NewModule.jsx`
3. Add route in `app/frontend/src/App.jsx`
4. Create `app/backend/routers/new_module.py` with `_require_new = require_module("new_module_id")`
5. Register router in `app/backend/main.py` under `/api/v1/new_module`
6. Add API methods to `app/frontend/src/lib/api.js`
7. Update `docs/MAP.md` with the new file

## Household Module

The Household module (`pages/Household.jsx`) is tab-based. All data lives in `brain/USERS/_household/`. Shared events: any member can create; only admins can edit/delete. Task assignment: admin creates with optional `assigned_to` field; assigned users see task with a 🏠 badge. Household record is the single source of truth.

**To add a new household section:** add to the `TABS` array in `Household.jsx`, add a conditional content block, add backend endpoints to `routers/shared.py` and `lib/api.js`.

## Notes Module

- Auto-save: 1.5 s debounce after user stops typing. No explicit Save button.
- Getting Started note: created automatically if user has no notes.
- Folder deselection: clicking a selected folder deselects it (notes created at root).

---

## Agent Skills

Reusable agent tasks live in `agent/skills/`. Each skill gets its own folder with a `.md` instruction file and optional shell scripts.

| Skill | When to use |
|-------|-------------|
| `run-tests` | After any backend change, before committing — runs pytest and reports GREEN/RED |
| `diagnose` | Before a release or full health check — security/architecture audit with severity levels |
| `run-agent` | CLI wrapper to send goals to the LogCore in-app AI agent and get results + tool trace |

To add a new skill: create the folder, add the `.md`, add any scripts, register it in `agent/README.md`.
