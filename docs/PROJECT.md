# LogCoreOS — Project Documents

*Combined reference: System Architecture + Development Roadmap.*

---

# Part 1 — System Architecture

## Vision

LogCoreOS is a self-hosted, open-source, AI-native life operating system that acts as the central intelligence and data layer for an individual or family.

The core principles:

- Data ownership first
- Human-readable files first
- Vendor agnostic
- Local-first with cloud convenience options
- AI as an interface, not the product
- Extensible and modular

---

## Two Products

**LogCore Brain** (`brain/`) — Free and open source. Markdown and JSON files. Works with any AI — Claude Code, GPT, Ollama, anything. Take your Brain folder anywhere and your AI context comes with you.

**LogCore App** (`app/`) — The software layer. Python FastAPI backend + React frontend, installable as a PWA on phones and desktops. Dashboards, task management, integrated AI chat, background scheduling, push notifications. This is what you run (or pay to have hosted).

---

## High-Level Architecture

```
User Interface (React PWA)
      ↓
Application Layer (FastAPI)
      ↓
AI Agent Layer (ai_provider abstraction → current: Anthropic)
      ↓
The Brain (Source of Truth — Markdown + JSON files)
      ↓
Automation Layer (Built-in Scheduler + future: LogCore Workflows)
      ↓
External Services & Devices
```

---

## 1. The Brain

The Brain is the heart of LogCoreOS.

All user data exists as organized Markdown and JSON files inside `brain/`. The Brain is fully portable — it works with any AI out of the box. If the AI provider changes, the Brain comes with you.

Structure:

```
brain/
├── AGENTS.md              ← AI boot protocol (session start order, memory rules)
├── SOUL.md                ← AI personality and communication principles
├── USERS.md               ← User registry and selection logic
├── MEMORY_MAP.md          ← Navigation index for all memory files, skills, plugins
├── Memory/
│   ├── Long_Term_Memory.md    ← System-wide stable knowledge
│   └── Daily Notes/           ← One file per session day (YYYY-MM-DD.md)
├── USERS/
│   ├── _template/             ← Copied for each new user at setup
│   │   ├── Profile.md
│   │   ├── Long_Term_Memory.md
│   │   ├── Short_Term_Memory.md
│   │   └── Tasks/
│   │       ├── tasks.json
│   │       ├── tasks_history.json
│   │       ├── tasks_view.md
│   │       └── daily_override.json
│   └── {User Name}/           ← Created by the setup wizard on first login
└── skills/
    ├── life-priorities/       ← Task scoring + recurring task logic
    └── skill-creator/         ← Template and process for building new skills
```

The Brain files are the permanent source of truth. Databases exist only as generated indexes for search, caching, or performance.

---

## 2. AI Agent System

The AI agent is the operating interface for LogCoreOS.

At the start of every session, the AI reads the Brain in this order:

1. `SOUL.md` — personality and principles
2. `USERS.md` — who is being helped
3. `Memory/Long_Term_Memory.md` — system-wide stable knowledge
4. `USERS/{name}/Long_Term_Memory.md` — personal stable knowledge
5. `USERS/{name}/Short_Term_Memory.md` — recent active context
6. `USERS/{name}/Tasks/tasks.json` — active tasks
7. `MEMORY_MAP.md` — navigation index

After loading, the agent scores the user's tasks and surfaces the **top 3 most pressing tasks** using the Life Priorities skill.

**AI Provider:** The App routes all AI calls through `services/ai_provider.py` — a thin abstraction layer so swapping providers requires changing one file, not refactoring the whole codebase. Currently wired to Anthropic. Multi-provider support (local models, OpenAI, Ollama) is Phase 6. The `AI_PROVIDER` and `AI_MODEL` env vars control the active model.

---

## 3. Life Priority Scoring

The Life Priorities skill is a core built-in feature.

Each user defines their priority order in `Profile.md` (e.g., God → Family → Job → Personal Growth → Hobbies). Tasks are scored by category weight, urgency, and priority to surface what matters most right now.

**Scoring formula:**

```
category_weight = total_categories - position_index
priority_weight: High=3, Medium=2, Low=1
urgency_bonus:  overdue=10, due_today=5, due_this_week=2, no_due_date=0

final_score = (category_weight × priority_weight) + urgency_bonus
```

Implemented in both the AI layer (`skills/life-priorities/`) and the App backend (`priority_service.py`). The dashboard displays top 3 automatically via `/api/tasks/top3`.

---

## 4. Application Modules

The App currently provides:

**Phase 1 (complete):**

- User authentication (JWT, bcrypt, role-based: admin / member / guest)
- Task management (create, complete, skip, recurring, streaks, history)
- Life priority scoring and top-3 dashboard
- AI chat interface (full Brain context injected into every message)
- Push notifications via ntfy (self-hosted)
- Setup wizard (creates user Brain folder from template on first login)
- Background scheduler (nightly recurring processor, morning digest, overdue alerts, weekly review)
- React PWA (installable on phone and desktop)
- Docker Compose deployment
- Notes module (markdown notes editor, stored in Brain/Notes/)
- Journal module (daily entries stored in Brain/Journal/YYYY-MM-DD.md, with agent tools)
- Calendar module — full stack: events CRUD, personal calendar UI (CalendarGrid with multi-day event bars, holiday engine, task pills, day detail panel), household calendar tab
- Household module — tab-based hub: Calendar tab (shared events + tasks on grid) + Tasks tab (all shared tasks with filter by status, created_by attribution); **task assignment** (admin assigns tasks to a named member; assigned member sees the task in personal Tasks + calendar with 🏠 badge); **shared events** visible on every member's personal calendar with toggle; **"Add to Household"** in personal EventModal moves event to household pool; any member can create events, admin-only edit/delete; done tasks filtered from calendar grids
- Per-user appearance theming: accent color (8 presets + any hex), dark/light/system mode, background (7 gradient presets + custom image upload), density (comfortable/compact), corner radius (rounded/sharp) — all persisted in `auth.json` and applied via CSS variables with FOUC prevention
- Collapsible sidebar (desktop) with collapse state persisted to `localStorage`
- Frosted card blur, left-border active nav highlight, CSS variable-driven corner radii

**Phase 2 (complete):**

- Long-term memory writes from chat (append_memory / rewrite_memory tools)
- Planning mode with propose-before-execute AI behaviour
- Proactive suggestions engine with notification inbox
- File modification from chat (read/write/list Brain files via agent tools)
- Research mode with Tavily web search integration

**Phase 3 (partial — shipped early):**

- n8n Automations integration — personal and business workflow cards, import/run/logs via n8n REST API; business workflows auto-synced from `automations_stubs/` on startup
- Smart Home (Home Assistant) — entity tiles, scene control, HA automation management, per-user starred favourites on dashboard widget; admin config panel
- Team module — business-workspace shared task + event pool (`_team`), structurally separate from Household (`_household`); no data can cross between the two
- Assets module — template-driven nestable object tracking (subdivisions → parcels, vehicles, equipment): admin-curated typed field templates, subtree sharing + per-user hide, pool conversion (survives account deletion), archive-first lifecycle, change history, attachments, task linking, AI tools, and a token-authenticated n8n automation API
- Finance module — books/accounts/transactions, SimpleFIN bank sync + CSV, budgets/recurring/projection/deviation alerts, invoicing/AR/tax/receipts, asset-style sharing with caps (both workspaces)
- Contacts (CRM) module — rich contacts + admin custom fields, interaction timeline, customizable deals pipeline (kanban+list), follow-up reminders, asset-style sharing, Contact-linked payees + invoice clients, write-focused n8n automation API + agent tools (both workspaces)

**Phase 4 (partial — shipped early):**

- Workspace switching — personal / business dual-workspace support; per-workspace data paths, module visibility, and feature role defaults; workspace toggle pill in sidebar for dual-access users; admin UI for granting and per-workspace module control

**Planned (future phases):**

- Projects (deferred from Phase 1; roadmapped for Phase 3+)
- Health tracking
- External integrations (Google Calendar, Apple Health, etc.)

---

## 5. Multi-User Architecture

Multi-user is foundational from Phase 0, not a later addition.

One installation supports a single person, couple, family, or household.

Each user receives:

- Their own `USERS/{name}/` Brain folder
- Private memory and tasks
- Individual AI preferences (defined in their Profile)
- Individual life priority hierarchy

**Registration model:** The first user to register automatically becomes admin. After that, registration is closed by default — admins add new users directly from the admin panel (Settings → User Access → Add User) or by toggling Open Registration temporarily. This prevents kids or unauthorized users from creating accounts to bypass restrictions.

**Admin module control:** Admins can disable specific modules per user (e.g., restrict a child to Tasks only). Restrictions propagate to active sessions within 30 seconds via polling — no re-login required.

**User contact & notification preferences (future):**

Currently each user record stores an email (login identifier) and an ntfy channel UUID (push notifications). Email is used for login only — not for sending messages. ntfy handles all current notification delivery without requiring a phone number or email address.

When notification automation expands (email digests, SMS alerts, etc.), user records should be extended with a structured `notifications` block rather than adding flat fields:

```json
"notifications": {
  "ntfy": "lc-abc123",
  "email": "user@example.com",
  "phone": "+15551234567"
}
```

Each field is optional — the notification service checks which ones are populated before sending. This avoids breaking changes when new channels are added. Phone number (SMS via Twilio or similar) should only be added when a concrete SMS feature is being built — not speculatively.

Shared spaces and family-level features (shared calendar, chores, family dashboard) were originally planned for Phase 5; core household functionality (shared tasks, events, task assignment, personal calendar integration) shipped in Phase 1.

---

## 6. Automation System

**Built-in scheduler (system automation) — active now:**

The `scheduler.py` background service handles all internal automation:

| Job | Schedule | What it does |
|-----|----------|--------------|
| Recurring processor | Nightly 00:01 | Archives done non-recurring tasks to history; advances recurring due dates; resets broken streaks |
| Morning digest | Configurable (default 06:00) | Runs `daily_digest` suggestion for each user |
| Overdue check | Configurable (default 19:00) | Alerts on overdue tasks |
| Weekly review | Sunday 19:00 | Summary of completed tasks by category |
| Goal drift | Daily 19:30 | Checks progress against goals; surfaces goal drift suggestions |
| JTI cleanup | Nightly 03:00 | Removes expired revoked JWT token IDs from `auth.json` |
| Custom jobs | User-configured (daily/weekly/interval) | Per-user custom suggestion schedules registered dynamically |

Scheduler timezone is configurable via `SCHEDULER_TIMEZONE` in `.env`.

**LogCore Workflows (user-defined automation) — Phase 3:**

Users will define automations through the app or via AI command. Workflows run natively inside the scheduler engine. For users who want n8n, workflows can be exported in n8n-compatible format and imported there — but n8n is never a required dependency. This keeps the system vendor-agnostic and self-contained by default.

---

## 7. Integration Layer

Planned connectors:

- Calendars (Google, Apple)
- Email
- Cloud storage
- Health devices (Apple Health, Garmin)
- Smart home systems (Home Assistant)
- Messaging platforms
- Financial services
- External APIs

---

## 8. Deployment

**Tech stack:**

- Backend: Python FastAPI
- Frontend: React + Vite + Tailwind CSS (served as PWA)
- Notifications: ntfy (self-hosted)
- Containers: Docker Compose

**Docker services:**

```
logcore-app    → FastAPI backend + React frontend (port 8000)
logcore-ntfy   → ntfy push notification server (port 5680)
logcore-n8n    → n8n workflow automation engine (internal; exposed via app proxy)
```

The `brain/` folder and `auth.json` are mounted as volumes — all data persists outside the container.

**Key environment variables (see `docker/.env.example`):**

| Variable | Default | Purpose |
|----------|---------|---------|
| `SECRET_KEY` | *(required)* | JWT signing key |
| `AI_PROVIDER` | `anthropic` | Active AI provider |
| `ANTHROPIC_API_KEY` | *(required for chat)* | Anthropic API key |
| `AI_MODEL` | `claude-sonnet-4-6` | Model to use |
| `ALLOWED_ORIGINS` | `*` | CORS origins (lock down in production) |
| `COOKIE_SECURE` | `true` | Require HTTPS for auth cookies (set false for local HTTP) |
| `TRUST_PROXY_HEADERS` | `false` | Trust X-Forwarded-For header (enable behind a reverse proxy) |
| `SCHEDULER_TIMEZONE` | `America/Chicago` | IANA timezone for all scheduled jobs |
| `ALLOW_OPEN_REGISTRATION` | `false` | Allow self-registration after first user |

`COOKIE_SECURE` and `TRUST_PROXY_HEADERS` can be overridden at runtime without a restart via **Admin → Hosting**. The panel writes to `brain/hosting.json`; the app reads that file on every request and the runtime value always wins over the env var.

**Backups:**

The Brain is the source of truth. Back it up.

```bash
# Manual backup (saves to ./backups/)
bash docker/backup.sh

# Custom backup destination
bash docker/backup.sh /path/to/backup/folder
```

Keeps the 30 most recent backups automatically. For automated backups, add to cron on the host:

```
0 3 * * * /path/to/logcoreos/docker/backup.sh >> /var/log/logcore-backup.log 2>&1
```

**PWA on mobile:** The app installs as a PWA on Android and desktop. iOS (Safari) supports PWA installation but has historically limited background push notification support — ntfy's native app handles notifications on iOS reliably regardless of PWA limits.

**Deployment models:**

- **Community:** Self-hosted via Docker Compose. Free, full data ownership.
- **Managed:** LogCore hosted. Automatic backups, easy updates, remote access. *(planned)*
- **Appliance:** Dedicated hardware with LogCoreOS pre-installed. *(planned)*

---

# Part 2 — Development Roadmap

## Phase 0: Foundation ✅ Complete

Create the Brain standard.

Done:

- Brain folder structure (`AGENTS.md`, `SOUL.md`, `USERS.md`, `MEMORY_MAP.md`, `Memory/`, `USERS/_template/`)
- Per-user memory system (Profile, Long-Term Memory, Short-Term Memory)
- Life Priorities skill (`skills/life-priorities/`) with scoring formula, task schema, recurring logic
- Skill-creator system for building new skills
- AI boot protocol and end-of-turn memory rules

---

## Phase 1: Core MVP ✅ Complete

**Goal:** A usable personal life operating system.

Done:

- User authentication (JWT, bcrypt, roles)
- Admin-only registration (first user = admin; admin adds subsequent users)
- Setup wizard (creates user Brain folder from template)
- Task management (CRUD, recurring, streaks, history)
- Life priority scoring (top 3 dashboard)
- AI chat interface with full Brain context injection
- AI provider abstraction layer (swap providers by changing one env var)
- Push notifications (ntfy)
- Background scheduler (recurring processor, morning digest, overdue alerts, weekly review)
- Configurable CORS, timezone, and registration settings
- Backup script (`docker/backup.sh`)
- React PWA (installable on phone and desktop)
- Docker Compose deployment
- Notes module (markdown notes editor, stored in Brain/Notes/)
- Journal module (daily entries stored in Brain/Journal/YYYY-MM-DD.md, with agent tools)
- Calendar module — full stack: personal calendar UI with multi-day event bars, client-side holiday engine (17 US holidays), task pills, day detail panel; household calendar tab with shared events
- Household module — tab-based hub (Calendar + Tasks); shared tasks visible to all members, shared events admin-only; undated tasks visible in Tasks tab
- Per-user appearance theming (accent color, dark/light/system mode, background gradients + custom image, density, corner style)
- Collapsible desktop sidebar, frosted card blur, left-border active nav, CSS variable-driven design tokens
- Admin hosting panel (cookie_secure, trust_proxy_headers, domain URL, Cloudflare Tunnel token + apply)
- launch.sh one-command startup script

Deferred:

- Projects (backlogged; roadmapped for Phase 3+)

---

## Phase 2: AI Operating Layer ✅ Complete

Shipped:

- Long-term memory writes from the App (`append_memory` / `rewrite_memory` agent tools)
- Planning mode — agent proposes a plan and awaits confirmation before executing
- Proactive suggestions engine — AI monitors context and surfaces suggestions; notification inbox in the UI
- File modification from chat — agent can read, list, and write Brain files via tool use
- Research mode — Tavily web search integration; agent can search the web during chat sessions

Natural language command interface active. Examples that work now:

- "Plan my week."
- "Summarize my progress this month."
- "Organize my tasks by project."
- "Create a goal and break it into tasks."

---

## Phase 3: LogCore Workflows (Automation)

**Shipped early:**
- ✅ n8n integration — personal and business workflow management with auto-sync for business stubs

**Remaining:**

Build a native workflow engine inside the scheduler.

- Workflow definition format (JSON-based, human-readable)
- Trigger types: time-based, event-based (task completed, Brain file changed, etc.)
- Actions: send notification, update Brain file, call external API, run a skill
- AI-generated workflows ("create an automation that reminds me every Sunday to review my goals")
- Native workflow editor in the App UI

The built-in scheduler handles all system jobs. LogCore Workflows handles everything the user defines.

---

## Phase 4: Integrations and Migration

**Shipped early:**
- ✅ Home Assistant smart home integration (entity control, scenes, HA automations, per-user favourites)
- ✅ Workspace switching — personal / business dual-workspace with isolated data paths, per-workspace modules, and admin-controlled access

**Remaining:**

Develop connectors:

- Existing note applications (Notion, Obsidian, Apple Notes)
- Calendar systems (Google, Apple)
- Task managers (Todoist, Things)
- Health platforms (Apple Health, Garmin)

Build AI-assisted migration:

- "Import my digital life."

The AI organizes everything into the Brain.

---

## Phase 5: Family / Business Operating System

Build on the existing multi-user and workspace foundation. Foundation already shipped:

- ✅ Shared calendar (household events visible to all members, admin-only write)
- ✅ Shared tasks (household task pool, any member can create/complete, created_by attribution)
- ✅ Household module tab architecture (Calendar + Tasks tabs; extensible for future tabs)
- ✅ Team module (business team task + event pool, structurally isolated from Household)
- ✅ Per-workspace module visibility control (admin sets which modules are active per workspace per user)

Remaining:

- Permission controls (what each user can see / is allowed to edit)
- Family dashboard
- Shared shopping lists
- Chore management with assignments
- Business-specific features (project tracking, ~~client management~~ → shipped as the Finance invoicing + **Contacts (CRM)** modules, etc.)
- Household/Team automation via LogCore Workflows

---

## Phase 6: AI Provider Expansion

Deliver on the vendor-agnostic promise. The abstraction layer (`ai_provider.py`) is already in place — this phase wires up additional providers.

- Local models via Ollama and LM Studio
- OpenAI and Gemini
- Any provider with an OpenAI-compatible API
- Provider selection per-user (one household member uses local, another uses cloud)

The Brain context layer works identically regardless of provider.

---

## Phase 7: Ecosystem

Create:

- Plugin system
- Public Brain specification
- Developer API
- Community marketplace

---

## Phase 8: Commercial Platform

Launch:

- Managed hosting
- Enterprise-grade infrastructure
- Premium AI services
- Hardware appliance

---

## Development Philosophy

Do not begin by building every feature.

The first goal is to create the foundation:

```
Brain → AI Agent → Core Applications → Automations → Ecosystem
```

If the foundation is correct, every future feature becomes easier to build.

All logic, skills, and plugins live in the Brain. Provider-specific configs are thin wrappers. If the AI provider changes tomorrow, the Brain — and everything the user has built — comes with them.
