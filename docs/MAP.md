# MAP.md — LogCoreOS Navigation Index

This is the navigation index for all files in this repo. Keep it updated when files or folders are added.

---

## Repository Layout

```
LogCoreOS/
│
├── CLAUDE.md                     → thin pointer to docs/AGENTS.md
├── README.md                     → user-facing quick start (do not move — it's for humans)
├── CHANGELOG.md                  → user-facing version history (Keep a Changelog format)
├── SECURITY.md                   → vulnerability disclosure policy
├── OWNER_SETUP.md                → LogCoreTech managed-service setup checklist (ops, not for AI agents)
├── LICENSE                       → project license
├── launch.sh                     → one-command startup: builds frontend, generates .env, starts Docker
├── requirements-dev.txt          → dev/test deps (pytest, etc.)
│
├── app/
│   ├── backend/
│   │   ├── main.py               → app factory, router registration, CORS + security headers middleware, static file serving
│   │   ├── config.py             → all env vars via Pydantic Settings (reads docker/.env)
│   │   ├── scheduler.py          → 7 APScheduler jobs (recurring, digest, overdue, weekly, goal drift, JTI cleanup, custom)
│   │   ├── routers/
│   │   │   ├── _task_models.py   → shared Pydantic models for tasks (CreateTaskRequest, UpdateTaskRequest)
│   │   │   ├── _event_models.py  → shared Pydantic models for calendar events
│   │   │   ├── auth.py           → login, register, logout, /me, admin user management, AI/search/hosting settings, infisical + feature flags
│   │   │   ├── tasks.py          → task CRUD, top3, scored, history
│   │   │   ├── chat.py           → AI chat with plan/auto/research modes, Brain context injection, tool use, chat save/load
│   │   │   ├── brain.py          → Brain file read/write (path-validated, admin-only writes)
│   │   │   ├── notes.py          → notes module (files + folders CRUD, move)
│   │   │   ├── journal.py        → journal module (daily entries by date)
│   │   │   ├── calendar.py       → calendar module (tasks view + events CRUD)
│   │   │   ├── priorities.py     → priority order + daily override
│   │   │   ├── setup.py          → first-time setup wizard
│   │   │   ├── health.py         → GET /health (no auth, used by Docker healthcheck)
│   │   │   ├── export.py         → brain zip download (mounted at /api/v1/user)
│   │   │   ├── shared.py         → household pool: tasks at /shared/tasks, events at /shared/events (admin write)
│   │   │   ├── team.py           → business team pool: tasks at /team/tasks, events at /team/events; own _team pseudo-user; separate from household
│   │   │   ├── push.py           → web push subscriptions (VAPID), subscribe/unsubscribe/test
│   │   │   ├── suggestions.py    → proactive AI suggestion engine + per-user custom schedules + notification inbox
│   │   │   ├── profile.py        → user Profile.md read/write
│   │   │   ├── infisical.py      → Infisical secrets manager integration (admin only; status, token set/clear)
│   │   │   ├── features.py       → feature flags + custom role management (admin only)
│   │   │   ├── automations.py    → automations module: import/run/logs n8n workflows (personal + business scopes)
│   │   │   └── home.py           → Home Assistant module: entity control, scenes, automations, favourites, admin config
│   │   ├── services/
│   │   │   ├── file_service.py        → atomic Brain file reads/writes — ALWAYS use this, never open(...,'w')
│   │   │   ├── auth_service.py        → user CRUD, JWT create/verify, bcrypt, JTI revocation
│   │   │   ├── ai_provider.py         → AI abstraction layer (Anthropic + OpenAI-compatible; sync/async bridge)
│   │   │   ├── agent_service.py       → multi-tool AI agent orchestration (plan/auto/research modes, tool registry)
│   │   │   ├── task_service.py        → task business logic (CRUD, pagination, type handling)
│   │   │   ├── events_service.py      → calendar event CRUD
│   │   │   ├── notes_service.py       → notes CRUD, folder management, move operations
│   │   │   ├── journal_service.py     → daily journal entry CRUD
│   │   │   ├── profile_service.py     → user Profile.md + profile.json read/write
│   │   │   ├── priority_service.py    → life priority scoring formula + top3 logic
│   │   │   ├── hosting_service.py     → runtime hosting config (reads brain/hosting.json at request time)
│   │   │   ├── rate_limiter.py        → IP-based rate limiting (respects trust_proxy_headers)
│   │   │   ├── recurring_service.py   → recurring task date advancement + streak logic
│   │   │   ├── notification_service.py → ntfy push notification delivery
│   │   │   ├── push_service.py        → web push subscription management + VAPID send
│   │   │   ├── suggestions_service.py → proactive suggestion generation + custom schedule management
│   │   │   ├── web_search_service.py  → Tavily API web search (for chat research mode)
│   │   │   ├── infisical_loader.py    → Infisical secrets pull on startup; token validation + file storage
│   │   │   ├── features_service.py    → feature flags + role resolution (get_effective_disabled)
│   │   │   ├── n8n_service.py         → n8n REST API client; import/execute/delete/activate workflows; write docker/n8n.env; sync_business_workflows() for auto-sync
│   │   │   └── ha_service.py          → Home Assistant REST API client; config CRUD, entity states, service calls, scenes, automations, user favourites
│   │   ├── automations_stubs/    → committed stub files (*.stub.json) that drive business workflow auto-sync; each has name/key/tags only — no workflow logic ever committed here
│   │   ├── migrations/
│   │   │   └── runner.py         → runs pending Brain schema migrations at startup
│   │   └── tests/                → pytest suite (see Testing section in AGENTS.md)
│   │
│   └── frontend/
│       └── src/
│           ├── lib/
│           │   ├── api.js         → ALL API calls go here — never fetch() directly in components; injects X-Workspace header on every request
│           │   ├── auth.jsx       → useAuth() hook + AuthProvider; polls /me every 30s; preferences server-only (not in localStorage)
│           │   ├── constants.js   → ALL_MODULES registry (must match backend require_module IDs), CATEGORY_COLORS, DEFAULT_SHORTCUTS, getShortcutsForUser(user, workspace)
│           │   ├── workspace.jsx  → WorkspaceProvider context + useWorkspace() hook; persists active workspace to localStorage
│           │   └── theme.js       → CSS variable theme engine (accent color, dark mode, background, density, corners)
│           ├── pages/
│           │   ├── Dashboard.jsx  → dashboard: top 3 scored tasks, today's tasks, streaks, Smart Home favourites widget
│           │   ├── Tasks.jsx      → personal task management (list, filter, priority reorder, edit modal, household assigned tasks)
│           │   ├── Goals.jsx      → standalone Goals page at /goals (gated by tasks module): filters tasks where type='goal', progress bar, category grouping
│           │   ├── Chat.jsx       → AI chat: plan/auto/research modes, proposal cards, step trace, memory save, chat save/load
│           │   ├── Calendar.jsx   → personal calendar (month grid, events + dated tasks overlay, EventModal)
│           │   ├── Household.jsx  → household hub (personal workspace): shared task pool (all read/write), shared events (admin write)
│           │   ├── Team.jsx        → business team hub (business workspace): shared task pool, shared events — mirrors Household but on _team pool
│           │   ├── Notes.jsx      → markdown notes with folder tree, auto-save, create/delete/move
│           │   ├── Journal.jsx    → daily journal (date picker, markdown editor per day, entry list)
│           │   ├── Brain.jsx      → browse + edit user's Brain markdown files directly
│           │   ├── Profile.jsx    → edit Profile.md and profile.json fields (priorities, occupation, etc.)
│           │   ├── Automations.jsx → automations: personal/business n8n workflow cards, import modal, run + logs
│           │   ├── Home.jsx        → Smart Home: entity tiles by domain, scenes panel, HA automations, favourite stars
│           │   ├── Admin.jsx      → admin panel (users, feature roles, workspace access, AI settings, web search, hosting, Infisical, n8n, Smart Home)
│           │   ├── Settings.jsx   → user settings (appearance, timezone, session, notifications, background upload, shortcuts — server-side per-workspace via PATCH /auth/me)
│           │   ├── Login.jsx      → login + register form
│           │   └── Setup.jsx      → first-time setup wizard (Personal/Business profile, priorities, timezone)
│           └── components/
│               ├── Layout.jsx     → root shell: sidebar nav, user menu, theme toggle, module access guard
│               ├── TaskModal.jsx  → create/edit task form (title, category, type, recurrence, due date/time, assigned_to)
│               ├── EventModal.jsx → create/edit calendar event form (title, dates, times, all_day, color, notes)
│               ├── CalendarGrid.jsx → month view: day cells with event/task indicators, click to open detail
│               └── ErrorBoundary.jsx → catch React render errors, display fallback UI
│
├── brain/                         → starter Brain (mounted at /data/brain in Docker)
│   ├── AGENTS.md                  → AI boot protocol (in-app AI session start order)
│   ├── SOUL.md                    → AI personality and communication principles
│   ├── USERS.md                   → user registry and selection logic
│   ├── MEMORY_MAP.md              → navigation index for all Brain files
│   ├── Memory/
│   │   └── Long_Term_Memory.md    → system-wide stable facts (shared AI context)
│   ├── USERS/_template/           → copied for each new user at setup
│   │   └── Business/              → placeholder — provisioned as empty business workspace for new users
│   ├── skills/life-priorities/    → task scoring + recurring task logic
│   ├── _system/auth.json          → user accounts, JTI blacklist (NEVER commit; volume-mounted)
│   ├── _system/features.json      → feature flags + custom role definitions (created at first setup)
│   ├── _system/migrations.json    → migration tracking (which schema migrations have run)
│   ├── _system/vapid_keys.json    → VAPID keypair for web push notifications (auto-generated)
│   ├── _system/n8n_config.json    → n8n URL + API key (written by Admin → n8n card)
│   ├── _system/ha_config.json     → Home Assistant URL + long-lived token (written by Admin → Smart Home card)
│   └── _system/automations_index.json → business workflow metadata (n8n IDs + tags)
│   ├── ai_settings.json           → AI provider, model, API keys (written by Admin UI; not in git)
│   └── hosting.json               → runtime hosting config written by Admin → Hosting panel
│
├── docker/
│   ├── docker-compose.yml         → service definitions (app + ntfy + n8n)
│   ├── .env.example               → env var template
│   ├── .env                       → live secrets (NEVER commit; generated by launch.sh)
│   └── backup.sh                  → Brain backup script (keeps 30 most recent)
│
├── agent/
│   ├── README.md                  → in-app AI agent architecture: modes, tool registry, brain skills
│   └── skills/                    → pointer files for brain skills (source lives in brain/skills/)
│       └── life-priorities/       → pointer → brain/skills/life-priorities/ (task scoring + top 3)
│
└── docs/
    ├── README.md                  → docs folder overview and file table
    ├── AGENTS.md                  → AI boot protocol + dev conventions
    ├── SOUL.md                    → AI personality and principles
    ├── PROJECT.md                 → system architecture + development roadmap
    ├── TASKS.md                   → active work queue + backlog
    ├── MEMORY.md                  → design decisions, security rules, known gotchas
    ├── MAP.md                     → THIS FILE — navigation index
    ├── API.md                     → REST API endpoint reference
    ├── TESTING.md                 → testing guide: brain fixture, patterns, coverage targets
    ├── Daily Notes/               → per-session work logs (YYYY-MM-DD.md)
    ├── skills/                    → dev tools for Claude Code sessions
    │   ├── README.md              → skill index and usage
    │   ├── diagnose/              → full security/architecture audit with severity levels
    │   ├── run-tests/             → run pytest + structured GREEN/RED report
    │   └── run-agent/             → CLI wrapper: send goals to the in-app AI, see tool trace
    └── hooks/
        ├── docs_loader.sh         → UserPromptSubmit hook: injects key docs at session start
        ├── docs_reminder.sh       → Stop hook: prompts doc updates at end of each turn
        ├── commit_reminder.sh     → Stop hook: reminds to commit every 30 min if changes exist
        └── safety_check.sh        → PreToolUse hook: blocks destructive Bash commands
```

---

## Key Reference Points

| What you need | Where to look |
|---|---|
| What this project is | `docs/README.md`, `docs/PROJECT.md` |
| Current priorities / tasks | `docs/TASKS.md` |
| Design decisions & hard rules | `docs/MEMORY.md` |
| Architecture & roadmap | `docs/PROJECT.md` |
| What was worked on recently | `docs/Daily Notes/YYYY-MM-DD.md` |
| Full API reference | `docs/API.md` |
| How to work on this codebase | `docs/AGENTS.md` |
| AI behavior rules | `docs/SOUL.md` |

---

## Update Rule

Any time a new file or folder is added to this repo, add it here with a one-line description before the session ends.
