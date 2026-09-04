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

**AI Provider:** The App routes all AI calls through `services/ai_provider.py` — a thin abstraction layer that dispatches by provider `kind` (`anthropic`, `openai_compatible`, `azure_openai`, `custom`). Admin -> AI Settings offers a picker covering ~25 named providers (Anthropic, OpenAI, Azure OpenAI, Groq, Gemini, Mistral, DeepSeek, xAI, local runners like Ollama/LM Studio/vLLM, and more via a "Custom" escape hatch) plus an opt-in live model-list fetch, backed by `services/ai_provider_catalog.py`. The `AI_PROVIDER`/`AI_MODEL`/`ANTHROPIC_API_KEY` env vars only seed the fallback default before an admin first saves settings there.

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
- Help system — an in-app Help & Guide page (per-module how-to, FAQ, search, "only my modules" filter, `?` shortcut), an ⓘ button on every module page, a first-run Getting Started checklist, and a What's-New broadcast (inbox note + banner) after each update. All authored in one source (`content/help.json`) that the AI also reads via a `get_help` tool + a capability index injected into chat, so the assistant can explain any feature and point users to the right module
- Goals module (2026-08-28, reworked 2026-08-29 per the owner's own try-it-out pass — "Round 2," same still-uncommitted changeset) — converted from a fake feature (Task records with `type=="goal"`, riding on Tasks' own permission gate) into a real, independent module: unbounded-depth subgoals (including linking an EXISTING goal as a subgoal, i.e. re-parenting, added Round 2), tasks linked directly to a goal, a generic metric-provider mechanism (a built-in subgoal/task completion rollup, a user-logged manual metric with history, or a live percentage pulled from another module — a Finance budget's spent-vs-limit, a number-type Contacts custom field, or the caller's own Contacts weight, added Round 2 — with a shared `direction`/`start_value` config so a decrease-type goal like weight loss reads correctly), a recurring linked task's own 30-day completion rate feeding its parent goal's rollup (Round 2, replacing a binary done/not-done contribution), on-pace tracking against a due date, a completion celebration and a progress-drift/deadline-urgency suggestion pair, a shared tag vocabulary with Tasks (Round 2), and an ME/pool tab split BY OWNERSHIP (Round 2 — "ME" is all of the caller's own goals at any depth, a second tab shows the household's/team's pool goals; the original Round 1 split was by DEPTH instead, root-level-only vs. everything, replaced once the owner reported not being able to find pool goals in the merged list); household/team pool goals via the same personal+pool pattern Finance/Contacts/Assets/Notes already use

**Phase 2 (complete):**

- Long-term memory writes from chat (append_memory / rewrite_memory tools)
- Planning mode with propose-before-execute AI behaviour
- Proactive suggestions engine with notification inbox
- File modification from chat (read/write/list Brain files via agent tools)
- Research mode with Tavily web search integration

**Phase 3 (partial — shipped early):**

- n8n Automation integration (renamed from "Automations," 2026-08-25) — personal and business workflow cards, import/run/logs via n8n REST API; business workflows auto-synced from `automations_stubs/` on startup
- Home Assistant — entity tiles, scene control, HA automation management, per-user starred favourites on dashboard widget; admin config panel (renamed from "Smart Home," 2026-08-24)
- Team module — business-workspace shared task + event pool (`_team`), structurally separate from Household (`_household`); no data can cross between the two
- Assets module — template-driven nestable object tracking (subdivisions → parcels, vehicles, equipment): admin-curated typed field templates, subtree sharing + per-user hide, pool conversion (survives account deletion), archive-first lifecycle, change history, attachments, task linking, AI tools, and a token-authenticated n8n automation API
- Finance module — books/accounts/transactions, SimpleFIN bank sync + CSV, budgets/recurring/projection/deviation alerts, invoicing/AR/tax/receipts, asset-style sharing with caps (both workspaces)
- Contacts (CRM) module — rich contacts + admin custom fields, interaction timeline, customizable deals pipeline (kanban+list), follow-up reminders, asset-style sharing, Contact-linked payees + invoice clients, write-focused n8n automation API + agent tools (both workspaces)

**Phase 4 (partial — shipped early):**

- Workspace switching — personal / business dual-workspace support; per-workspace data paths, module visibility, and feature role defaults; workspace toggle pill in sidebar for dual-access users; admin UI for granting and per-workspace module control

**Complete — Mod Store / universal module system (2026-08-24 through 2026-08-28):**

A real architectural shift, not just a feature: every module has now converted, one at a time,
into a self-contained `module_packages/<id>/` format with its own manifest/version — including
foundational ones (Tasks, Chat, Dashboards-the-feature), which just carry `uninstallable: true`
rather than being excluded from the system. End state reached: `main.py` has zero hardcoded
per-module router registrations. The registry mechanism itself (discovery, install/uninstall state,
all enforcement-gap fixes, the admin Mod Store UI) is done and fully tested, and — as of Finance's
own conversion below, the 13th and final one — every module the rollout plan ever targeted has
converted. What remains is real-world verification on the live instance of the more recently
converted modules, not further conversions (see `docs/TASKS.md`'s Mod Store tracking item for the
exact confirmed-live vs. built-but-unverified split). Thirteen modules converted in total: journal
(increment 1) and Home Assistant (increment 2, 2026-08-24, full internal id rename
too) are both confirmed working end-to-end on the owner's live instance. Automations/n8n Automation
(2026-08-25, taken out of the original planned order at the owner's request — display name only,
id/routes/internal names deliberately left unchanged), Calendar (2026-08-25, increment 4, no
rename at all this time — the owner's explicit "keep as calendar" — plus a new feature riding along:
the personal calendar's household/team pool-events toggle now hides itself entirely when that pool
module isn't installed/active for the viewer, instead of offering a button that would silently
no-op), Tasks (2026-08-25, increment 5, no rename either — the first LOCKED, `uninstallable:
true` module conversion, proving that mechanism end-to-end for real for the first time; task_service.py/
priority_service.py/recurring_service.py all stay core since Household/Team import them directly),
and Household+Team (2026-08-25, increment 6, converted together in one sitting since neither owns
its own service file — both ride Tasks'/Calendar's now-core locations; no rename for either) are all
built and fully tested but not yet verified on the live instance. This last increment surfaced two
real, generic gaps in the module system itself, both fixed generically rather than as one-offs: a
shared dashboard block (the old `pool_tasks`, serving both pools) had to split into
`household_tasks`/`team_tasks` since `BlockSpec.module` can only gate to one real module; and
`ModuleManifest` gained a new `admin_agent_tools` field (mirroring `read_only_agent_tools`) once
Household became the first module to own an admin-only AI tool. Chat (2026-08-26, increment 7, the
second LOCKED module after Tasks) is also built and fully tested but not yet verified on the live
instance; unlike Tasks, `agent_service.py`'s own session/orchestration engine needed zero changes
(confirmed permanent core infrastructure — `module_registry.py`'s own docstring had already named
Chat alongside Tasks/Dashboards before this conversion existed), so this increment's router-move
was comparatively small. It surfaced two real, pre-existing enforcement gaps rather than new
module-system mechanism gaps: `GET /chat/runs` and `GET /chat/runs/{run_id}` were ungated (a user
with chat disabled could still read past agent run history), and chat's own archive folder had no
`owned_brain_paths` entry at all, leaving a disabled user's past conversations fully readable via
the Brain browser and the AI's own file-reading tools regardless of module state — both fixed as
part of the conversion. Notes (2026-08-26, increment 8) is also built and fully tested but not yet
verified on the live instance — the first conversion to genuinely test the sidecar-share-index
sharing pattern (`Notes/_shares.json` + `notes_index.py`), the direct precedent Assets/Contacts/
Finance will need for their own future conversions; `notes_service.py`/`notes_index.py` both stay
core since `user_deletion_service.py` imports both directly. It surfaced the same shape of gap Chat's
own conversion found — real pre-existing enforcement holes, not new mechanism gaps: all 7 note AI
tools lived unfiltered in the static tool list, `note_embed`'s dashboard block had no module gate at
all (the exact `pool_tasks`-before-Household/Team situation), and the Notes folder had no
`owned_brain_paths` entry — all three closed the same way prior conversions closed their own. It also
surfaced a genuine, previously-latent gap in the module-tool-dispatch mechanism itself: the generic
dispatch never threaded the caller's active workspace through to a module's own AI tools, harmless
for every prior module (all workspace-blind by construction or already documented as such) but a real
regression risk for notes, whose tools are genuinely workspace-aware — fixed by widening the dispatch
signature, with every other module picking up the unused parameter for signature parity. Dashboards
(2026-08-27, increment 9, the third LOCKED module after Tasks and Chat) is also built and fully
tested but not yet verified on the live instance — structurally the most-depended-upon module
converted so far, since every other module's own dashboard blocks read/write through it.
`dashboards_service.py`/`dashboard_templates_service.py`/`dashboard_index.py` all stay core, the
strongest "stays core" case yet: `migrations/runner.py`'s own core migrations call `dashboards_service`
directly, and migrations run before module registration exists at all in boot order, not just
"another router imports it." Owns zero block types (it's the container, never a `REGISTRY` entry).
Surfaced the same enforcement-gap shape as Chat's/Notes' own conversions — all 10 dashboard AI tools
lived unfiltered in the static tool list, closed by making them module-owned; no brain-path gap
existed here since Dashboards data is JSON not markdown, the same structural category as Tasks
(`"Dashboards"` added to the unconditional structural skip set alongside `"Tasks"`, not the
conditional per-user one). One genuinely new problem no prior conversion needed to solve: `App.jsx`'s
root route (`to: '/'`) had to stay hardcoded and `ModuleRoute`-unwrapped, since a user with
`dashboard` disabled would otherwise hit a self-targeting redirect loop at the app's own home page —
solved by filtering the generic route-generation loop to skip any package claiming `/`. Assets
(2026-08-27, increment 10) is also built and fully tested but not yet verified on the live instance —
the 11th converted module, first of the three largest/most structurally complex remaining (Assets,
Contacts, Finance, deliberately last), and the first NORMAL optional-module conversion since Notes
(not `uninstallable`, unlike Tasks/Chat/Dashboards in between). `services/assets_service.py`/
`assets_index.py` both stay core, the strongest "stays core" case yet: `module_packages/dashboard/
backend/router.py`, an already-converted SIBLING module package rather than just another core router,
imports `assets_service` directly for its own Dashboard Hero subject resolver. The Collection dashboard
block (`dashboard_blocks/_collections.py`, previously filed separately since its own docstring
anticipated future generalization to non-Assets record types) folded into the same
`dashboard_block.py` as Assets' other 4 blocks and was deleted outright — it was 100%
Assets-data-dependent today and, unlike every other block type, had no `module=` gate at all, the
exact `pool_tasks`-before-Household/Team situation. The real, previously undocumented enforcement gap
this conversion found and closed: all 10 asset AI tools lived in `agent_service.py`'s unfiltered
static tool lists exactly like Chat's/Notes'/Dashboards' own tools had before their conversions — a
user with Assets disabled/uninstalled could still use every one of them via chat, closed the same way
by making them module-owned. The one genuinely new problem: two endpoints (`GET`/
`POST /assets/automation/token[/rotate]`) were gated only by `require_admin`, not `require_module`,
inside this optional module's own router — uninstalling Assets would have silently taken away the
admin's only way to view/rotate a token Contacts' own automation API still depends on
(`automations_config.py` itself stays core, unowned by either module) — relocated to
`routers/auth.py`'s admin section instead. Contacts (2026-08-28, increment 11, converted the same day
as Assets) is also built and fully tested but not yet verified on the live instance — the 12th
converted module, second of the three largest/most structurally complex remaining. `routers/
contacts.py` moved to `module_packages/contacts/backend/router.py`; unlike Assets, no endpoints moved
out this time — Contacts' own automation endpoints were already correctly gated only by the shared
n8n token, the same accepted pattern Assets' own automation endpoints use.
`services/contacts_service.py`/`contacts_index.py` both stay core — the most-depended-on "stays core"
service of any conversion yet, with a SECOND already-converted sibling module package
(`module_packages/chat/backend/router.py`'s AI system-prompt profile context) joining
`module_packages/dashboard/backend/router.py`'s Dashboard Hero resolver as direct importers, on top of
`agent_service.py`'s own core `get_profile`/`update_profile` tools, deliberately left core rather than
moved into Contacts' own `agent_tools.py` since Profile is a generic concept independent of Contacts'
module state. The real, structurally new problem this conversion had to solve, the mirror of Assets'
own Collection-block decision: `dashboard_blocks/_contacts.py`'s `custom_fields` block reads from
EITHER Contacts or Assets data depending on config, spanning both modules and owned by neither — it
was extracted into a new core file (`_custom_fields.py`) rather than folded into either module package,
while the other 3 blocks moved and gained a `module="contacts"` gate for the first time. The frontend
mirrors this exactly: `ContactPicker.jsx` stays core (7 external importers, including an
already-converted sibling module's own component), the only file left in `components/contacts/`.
Two admin-gated-but-not-module-gated endpoints were found and judged independently rather than fixed
uniformly: `PUT /contacts/fields` was missing `require_module("contacts")` — fixed; `GET
/contacts/available-for-linking` was deliberately left ungated, matching `/contacts/me`'s own
always-available precedent for account-creation infrastructure. Finance (2026-08-28, converted the
same day as Assets and Contacts) is the 13th and FINAL module in the entire rollout plan — the
largest and most structurally complex module in the app, and the only one split across SIX separate
router files (2,196 lines / 78 endpoints) rather than one, composed into a single router at the
manifest level via nested `include_router()` calls since `ModuleManifest.get_router()` only supports
returning one. `finance_service.py`/`finance_invoice_service.py`/`finance_index.py` all stay
core — the strongest "stays core" case yet, since Contacts' own `GET /contacts/{id}/finance`
endpoint makes deep, multi-function calls into both. `finance_planning_service.py`/
`simplefin_service.py` ALSO stay core, for a genuinely new reason: both are imported directly by
`scheduler.py`'s own boot/cron job functions, a scheduler dependency treated exactly like a
sibling-module dependency for the "stays core" test, mirroring `n8n_service.py`'s own precedent from
Automations. 13 admin-lifecycle SimpleFIN endpoints were found gated by `require_admin` alone, never
`require_module("finance")` — fixed, the same narrow-inconsistency shape as Contacts' own `PUT
/contacts/fields` finding. Full backend suite: 1030 passed (up from 996), `eslint`/`vite build`
clean. See `docs/MEMORY.md`'s 2026-08-28 entry (Finance) for the full writeup.

**The Mod Store migration is now complete.** All 13 modules the rollout plan ever targeted —
journal, home_assistant, automations, calendar, tasks, household, team, chat, notes, dashboard,
assets, contacts, finance — have converted into `module_packages/`. The only things that remain
permanently core/unconverted are the plan's own explicitly-designated cross-cutting infrastructure
that was never meant to convert: `dashboard_blocks/` (registry.py, render.py, every block resolver),
`agent_service.py`'s tool-orchestration/session engine, and `module_registry.py` itself. No further
module conversions are planned. What's left is real-world verification on the live instance of the
modules built since journal/Home Assistant/Automations were last confirmed working there — see
`docs/TASKS.md`'s Mod Store tracking item for exactly which modules are confirmed-live vs. still
pending.
Full design in `docs/MEMORY.md`'s 2026-08-24/25/26/27/28 entries and
`/home/logcore/.claude/plans/i-want-you-to-composed-scone.md`; rollout order tracked in
`docs/TASKS.md`.

**Goals used this same infrastructure, the same day, but was NOT one of the 13 rollout modules
above.** Immediately after this rollout's own migration-verification pass, `goals` — until then not
a real backend module at all, just Task records with `type=="goal"` riding on Tasks' own permission
gate — was scoped through its own interview and built as a genuinely new, independent
`module_packages/goals/` entry: unbounded subgoal hierarchy, linked tasks, the new generic
metric-provider mechanism (`module_registry.py`'s `MetricProviderSpec`/`owned_metric_providers`/
`metric_providers()`), and household/team pool goals. It's the mechanical *result* of everything this
rollout built (manifest/migration/agent-tool/dashboard-block infrastructure, the personal+pool
single-router pattern Finance/Contacts/Assets/Notes established), not a 14th increment of the
rollout itself — there was no `routers/goals.py`/`services/goals_service.py` to move, so "conversion"
isn't even the right word for it. Its own `m031` migration is what finally emptied
`features_service.py`'s `_CORE_MODULE_IDS` (and the frontend's `CORE_MODULES`) down to `[]` — `goals`
was the very last hardcoded-core id in the app, and it's now a real, independent, uninstallable
module like any other. See `docs/MEMORY.md`'s 2026-08-28 entry (Goals) for the full design writeup.

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

Deliver on the vendor-agnostic promise. Shipped: Admin -> AI Settings now offers a picker across ~25 named providers (Anthropic, OpenAI, Azure OpenAI, Groq, Gemini, Mistral, DeepSeek, xAI, Cerebras, Together, Fireworks, OpenRouter, local runners — Ollama, LM Studio, vLLM, llama.cpp, text-generation-webui, KoboldCpp, Jan.ai — and more via a "Custom" OpenAI-compatible escape hatch), an opt-in live model-list fetch per provider, and Azure's distinct resource-endpoint/deployment/API-version shape. Every field but the API key is a picker with a "type manually" fallback.

- ~~Local models via Ollama and LM Studio~~ shipped
- ~~OpenAI and Gemini~~ shipped
- ~~Any provider with an OpenAI-compatible API~~ shipped (the "Custom" entry)
- Provider selection per-user (one household member uses local, another uses cloud) — explicitly deferred; the setting is per-instance only for now

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
