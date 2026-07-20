# MAP.md — LogCoreOS Navigation Index

This is the navigation index for all files in this repo. Keep it updated when files or folders are added.

---

## Repository Layout

```
LogCoreOS/
│
├── CLAUDE.md                     → thin pointer to docs/AGENTS.md
├── VERSION                       → current version string (read by launch.sh and update.sh)
├── README.md                     → user-facing quick start (do not move — it's for humans)
├── CHANGELOG.md                  → user-facing version history (Keep a Changelog format)
├── SECURITY.md                   → vulnerability disclosure policy
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
│   │   │   ├── assets.py         → assets module: templates (admin), asset tree CRUD, shares/hidden_from, pool convert, attachments, n8n automation API (X-Automation-Token)
│   │   │   ├── finance.py        → finance module: books/accounts/categories/transactions CRUD, monthly report, net worth (access via finance_service._resolve_book_access)
│   │   │   ├── finance_banking.py → SimpleFIN connections (member request + mapping; ADMIN claim/reveal/disconnect/sync), CSV import (preview/commit), payee rules
│   │   │   ├── finance_planning.py → budgets (+status), recurring bills (+upcoming), planned one-offs, balance projection endpoints
│   │   │   ├── finance_invoicing.py → clients CRUD + AR rollup, invoices CRUD, partial payments (w/ linked income tx)
│   │   │   ├── finance_sharing.py → book/account audience (shares + contributors + hidden_from), share handshake respond, leave, member/role pickers
│   │   │   ├── contacts.py        → Contacts (CRM): contacts/interactions/deals CRUD, pipeline, admin custom fields, sharing handshake, CSV import/export, contact money view, write-focused n8n automation API
│   │   │   ├── home.py           → Home Assistant module: entity control, scenes, automations, favourites, admin config
│   │   │   ├── help.py            → Help system: GET /help/content (authored guide), /help/whats-new (banner state), GET/PUT /help/onboarding (first-run checklist); auth required, NO module gate (like Settings)
│   │   │   └── update.py         → update status check + trigger (admin only); works with update.sh on host
│   │   ├── services/
│   │   │   ├── file_service.py        → atomic Brain file reads/writes — ALWAYS use this, never open(...,'w')
│   │   │   ├── auth_service.py        → user CRUD, JWT create/verify, bcrypt, JTI revocation
│   │   │   ├── ai_provider.py         → AI abstraction layer (Anthropic + OpenAI-compatible; sync/async bridge)
│   │   │   ├── agent_service.py       → multi-tool AI agent orchestration (plan/auto/research modes, tool registry)
│   │   │   ├── task_service.py        → task business logic (CRUD, pagination, type handling)
│   │   │   ├── events_service.py      → calendar event CRUD
│   │   │   ├── notes_service.py       → notes CRUD, folder management, move; + sharing (sidecar Notes/_shares.json, folder-cascade resolve_access, pool notes, handshake, list_visible_notes/find_note_store)
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
│   │   │   ├── assets_service.py      → assets core: templates, field validation, tree ops, per-node archive (+cascade), share/hidden resolution, pool conversion, history, attachments
│   │   │   ├── assets_index.py         → derived share-routing cache (_system/assets_share_index.json); rebuildable, warmed at startup; sharers_for()/reindex_owner()/rebuild_share_index()
│   │   │   │   # Phase 2: per-user templates in USERS/{name}/Assets/templates.json (global in _system/asset_templates.json); assets ref template_id; request-based sharing (accepted[]) + accept/decline notifications
│   │   │   ├── finance_service.py     → finance core: books/accounts/categories/transactions (per-book per-year shards), computed balances, _resolve_book_access (single access gate)
│   │   │   ├── finance_reports.py     → finance reports computed on read: monthly income/expense by category, net worth
│   │   │   ├── simplefin_service.py   → SimpleFIN bridge client: claim setup token → read-only access URL (per-user secret), account mapping, sync engine w/ dedup + error throttle
│   │   │   ├── finance_import_service.py → CSV statement import: preview + column-mapped commit, import_hash dedup, Decimal→cents parsing
│   │   │   ├── finance_planning_service.py → budgets+alerts, recurring bills (matching/advance/missed), planned items, projection, deviation checks, nightly sweep
│   │   │   ├── finance_invoice_service.py → clients (reserved contact_id for future CRM), invoices (derived totals/overdue, auto-numbering), payments, AR rollup
│   │   │   ├── finance_index.py       → derived share-routing cache (_system/finance_share_index.json); rebuildable, warmed at startup; sharers_for()/reindex_owner()
│   │   │   ├── contacts_service.py     → Contacts core: contacts/interactions/deals, custom fields, pipeline, asset-style sharing (resolve_access read/contribute/edit), find_match dedup, follow-up reminders
│   │   │   ├── contacts_index.py       → derived share-routing cache for Contacts (_system/contacts_share_index.json); warmed at startup
│   │   │   ├── notes_index.py          → derived share-routing cache for Notes (_system/notes_share_index.json); scans each store's Notes/_shares.json; warmed at startup
│   │   │   ├── automations_config.py  → instance automation API token (generate/rotate/verify) for n8n → LogCore writes
│   │   │   ├── automation_inbox_service.py → Automation Inbox: named inboxes (notify/reviewers/workflow routing), item dedup by (workflow_key, external_id), status lifecycle, trim, batched notifications
│   │   │   ├── n8n_service.py         → n8n REST API client; import/execute/delete/activate workflows; write docker/n8n.env; sync_business_workflows() for auto-sync
│   │   │   ├── ha_service.py          → Home Assistant REST API client; config CRUD, entity states, service calls, scenes, automations, user favourites
│   │   │   ├── help_service.py        → Help content single source (loads content/help.json): get_content, as_text (markdown for the AI, incl. /help#id anchors), capabilities_index (enabled-modules index for chat context), onboarding state get/set
│   │   │   ├── whats_new_service.py    → on version bump, notify every user once (announce_if_updated at boot) + drive the few-day What's-New banner (get_banner); state in _system/whats_new_state.json
│   │   │   └── update_service.py      → GitHub release check (cached 4h), pending_update flag trigger, update log reader
│   │   ├── content/
│   │   │   └── help.json         → authored Help content (sections + FAQ + support + whats_new); SINGLE source read by the Help page, the ⓘ buttons, and the AI's get_help tool
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
│           │   ├── Automations.jsx → automations: Workflows|Inbox views — n8n workflow cards (import/run/logs) + Automation Inbox (item review actions, named-inbox chips, settings modal, ?view=inbox deep link)
│           │   ├── Assets.jsx      → assets: template-driven object tree (expand/collapse, filters, archived toggle), both workspaces
│           │   ├── Finance.jsx     → finance: book chips, Overview (balances + monthly summary) | Transactions (filters, add/edit) views, both workspaces
│           │   ├── Contacts.jsx    → Contacts (CRM): list + search, detail (fields/interactions/deals/money), ContactModal, CSV import/export; both workspaces
│           │   ├── Help.jsx        → Help & Guide page: fetches /help/content; TOC chips, per-section cards (blurb/how-to/tips), search, "only my modules" filter, What's New, FAQ, Contact & Support (mailto); hash-scrolls to #section from ⓘ deep-links
│           │   ├── Home.jsx        → Smart Home: entity tiles by domain, scenes panel, HA automations, favourite stars
│           │   ├── Admin.jsx      → admin panel (users, feature roles, workspace access, AI settings, web search, hosting, Infisical, n8n, Smart Home)
│           │   ├── Settings.jsx   → user settings (appearance, timezone, session, notifications, background upload, shortcuts — server-side per-workspace via PATCH /auth/me)
│           │   ├── Login.jsx      → login + register form
│           │   └── Setup.jsx      → first-time setup wizard (Personal/Business profile, priorities, timezone)
│           └── components/
│               ├── Layout.jsx     → root shell: sidebar nav, user menu, theme toggle, module access guard
│               ├── TaskModal.jsx  → create/edit task form (title, category, type, recurrence, due date/time, assigned_to, linked asset)
│               ├── AssetModal.jsx → asset modal: opens an existing asset in read-first view (AssetView), Edit flips to the editor (dynamic template fields, attachments, share/hide selectors, history, 3-choice archive, delete/convert); auto-flips create→edit
│               ├── AssetView.jsx  → read-only asset overview: header, attachments, fields as label/value pairs, notes, child list (drill-in), linked tasks, sharing summary, history; ✎ Edit button (owner/editor only)
│               ├── assetDisplay.jsx → shared asset display helpers (no circular import): AttachmentThumb, FieldInput, CapsSelector (contribute caps checkbox panel), formatChanges(), fieldDisplay()
│               ├── TemplateManager.jsx → admin template editor: ordered typed fields (TagInput options), EmojiPicker icon, defaults, example insert
│               ├── TagInput.jsx    → GitHub-topics-style chip input (free-text or strict selector mode); inline capped suggestion box — template options, share/hide members
│               ├── EmojiPicker.jsx → curated self-contained emoji grid popover (right-aligned) for template icons
│               ├── AssetTreePicker.jsx → foldered expand/collapse asset picker; reused by Move + create-asset parent chooser
│               ├── finance/       → finance components: TransactionModal.jsx (+tax flags+receipts+ContactPicker payee), BookSettings.jsx (accounts/categories/tax buckets/CSV import), SimpleFinPanel.jsx (bank connect+mapping), BudgetsPanel.jsx, RecurringPanel.jsx (+planned one-offs+deductible), InvoicesPanel.jsx (invoices/payments via ContactPicker + AR + printable InvoicePrint), ReportsPanel.jsx (P&L + tax export), money.js (cents↔display helpers)
│               ├── contacts/      → ContactPicker.jsx (search-first contact autocomplete + quick-create; reused by transaction payee + invoice client)
│               ├── EventModal.jsx → create/edit calendar event form (title, dates, times, all_day, color, notes)
│               ├── CalendarGrid.jsx → month view: day cells with event/task indicators, click to open detail
│               ├── HelpButton.jsx  → small ⓘ affordance next to a page title; deep-links to /help#<section>
│               ├── WhatsNewBanner.jsx → dismissible bar shown for a few days after an update (reads /help/whats-new); per-version localStorage dismiss; links to /help#whats-new
│               ├── GettingStarted.jsx → first-run checklist card on the Dashboard (reads/writes /help/onboarding); hides when dismissed or all steps done
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
│   ├── backup.sh                  → Brain backup script (keeps 30 most recent)
│   └── update.sh                  → in-place update + auto-rollback; --watch daemon for flag-file trigger; --cron for crontab
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
    ├── TASKS.md                   → active product work queue + backlog
    ├── MEMORY.md                  → design decisions, security rules, known gotchas
    ├── MAP.md                     → THIS FILE — navigation index
    ├── API.md                     → REST API endpoint reference
    ├── TESTING.md                 → testing guide: brain fixture, patterns, coverage targets
    ├── Security-Audit-2026-07-19.md → full security audit + remediation log (passes 1–5)
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
