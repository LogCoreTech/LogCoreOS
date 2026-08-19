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
│   │   │   ├── chat.py           → AI chat with plan/auto/research modes, Brain context injection, tool use, chat save/load; conversations are workspace-scoped sessions keyed by a required `chat_id` — `POST /chat` marks the session "running" before calling `run_agent`, resets to "idle" on an unhandled exception, and calls `notify_user()` on completion; `GET /chat/sessions` (list, for the Chats drawer) + `POST /chat/sessions/{chat_id}/read` (clear unread) read/write agent_service.py's session index
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
│   │   │   ├── infisical.py      → Infisical secrets manager integration (admin only; status, token set/clear)
│   │   │   ├── features.py       → feature flags + custom role management (admin only)
│   │   │   ├── automations.py    → automations module: import/run/logs n8n workflows (personal + business scopes)
│   │   │   ├── assets.py         → assets module: templates (admin), asset tree CRUD, shares/hidden_from, pool convert, attachments, n8n automation API (X-Automation-Token)
│   │   │   ├── finance.py        → finance module: books/accounts/categories/transactions CRUD, monthly report, net worth (access via finance_service._resolve_book_access); GET/PUT /finance/prefs — workspace-keyed last-opened-book pointer (finance_service.get_last_book_id/set_last_book_id, file_service.finance_prefs_path), consulted by Finance.jsx only when no `?book=` override is present
│   │   │   ├── finance_banking.py → SimpleFIN connections (member request + mapping; ADMIN claim/reveal/disconnect/sync), CSV import (preview/commit), payee rules
│   │   │   ├── finance_planning.py → budgets (+status), recurring bills (+upcoming), planned one-offs, balance projection endpoints
│   │   │   ├── finance_invoicing.py → clients CRUD + AR rollup, invoices CRUD, partial payments (w/ linked income tx)
│   │   │   ├── finance_sharing.py → book/account audience (shares + contributors + hidden_from), share handshake respond, leave, member/role pickers
│   │   │   ├── finance_transfers.py → cross-book/cross-workspace Transfer type: POST creates both linked legs (same-currency + edit-access-on-both required), PATCH/DELETE update or remove a pair together; imports _find_or_404/_require_edit from finance.py (same sibling-router pattern as the other finance_*.py files)
│   │   │   ├── contacts.py        → Contacts (CRM): contacts/interactions/deals CRUD, pipeline, admin custom fields, sharing handshake, CSV import/export, contact money view, write-focused n8n automation API, self-contact (GET/PATCH /contacts/me — login-gated only, not the contacts module), affiliation link/unlink
│   │   │   ├── home.py           → Home Assistant module: entity control, scenes, automations, favourites, admin config
│   │   │   ├── help.py            → Help system: GET /help/content (authored guide), /help/whats-new (banner state), GET/PUT /help/onboarding (first-run checklist); auth required, NO module gate (like Settings)
│   │   │   ├── update.py         → update status check + trigger (admin only); works with update.sh on host
│   │   │   ├── ai_usage.py       → AI usage metering + caps: GET /overview, /users, /defaults (admin), PATCH /defaults, /users/{id}/limits (admin), GET /me (any user, for the Chat toolbar indicator)
│   │   │   ├── dashboards.py     → Custom Dashboards: standalone dashboard CRUD/access/render, sharing handshake, catalog, cross-module reference lookup, members/roles (share picker support); also hosts Dashboard Templates CRUD (`/templates*`, declared before `/{dashboard_id}` — same route-ordering rule as assets.py) and `/{id}/subject` + `/{id}/detach-template` for templated-dashboard instances; `get_render`'s `_resolve_subject()` resolves a dashboard's `subject_type`/`subject_id` into a small `{type, id, name, icon?}` summary for the frontend hero header — never raises, just omits `subject` if the viewer's lost access
│   │   │   └── presence.py       → app-wide online/offline presence: `POST /presence/ping` records the caller's own last-seen (rate-limited); deliberately no lookup-by-username endpoint — presence is only ever meant to surface embedded in an already access-controlled contact read, never queried directly
│   │   ├── services/
│   │   │   ├── file_service.py        → atomic Brain file reads/writes — ALWAYS use this, never open(...,'w')
│   │   │   ├── auth_service.py        → user CRUD, JWT create/verify, bcrypt, JTI revocation
│   │   │   ├── ai_provider.py         → AI abstraction layer (Anthropic + OpenAI-compatible; sync/async bridge)
│   │   │   ├── agent_service.py       → multi-tool AI agent orchestration (plan/auto/research modes, tool registry); load_sessions/get_session/upsert_session/mark_session_read/delete_session_by_filename manage a capped (_SESSIONS_CAP=50), workspace-scoped chat_sessions.json index (status idle/running/awaiting_approval/awaiting_answer + unread + preview) — workspace-scoped (not user_path) because chat archives live under ws_path(...)/Chats/
│   │   │   ├── task_service.py        → task business logic (CRUD, pagination, type handling)
│   │   │   ├── events_service.py      → calendar event CRUD
│   │   │   ├── notes_service.py       → notes CRUD, folder management, move; + sharing (sidecar Notes/_shares.json, folder-cascade resolve_access, pool notes, handshake, list_visible_notes/find_note_store — find_note_store() takes an optional owner hint to disambiguate a path that could exist in more than one reachable store); meets(access, need) access-level helper, shared by routers/notes.py and agent_service.py's note tools
│   │   │   ├── journal_service.py     → daily journal entry CRUD
│   │   │   ├── profile_service.py     → pool (_household/_team) priority order only — real users' profile data lives on their self-contact (contacts_service.py) since the Profile/Contacts merge
│   │   │   ├── priority_service.py    → life priority scoring formula + top3 logic
│   │   │   ├── hosting_service.py     → runtime hosting config (reads brain/hosting.json at request time)
│   │   │   ├── rate_limiter.py        → IP-based rate limiting (respects trust_proxy_headers)
│   │   │   ├── recurring_service.py   → recurring task date advancement + streak logic
│   │   │   ├── notification_service.py → ntfy push notification delivery
│   │   │   ├── push_service.py        → web push subscription management + VAPID send; `_build_vapid_jwt` only prepends `mailto:` to `VAPID_SUBJECT` if it isn't already a `mailto:`/`https:` URI (some push services reject a `sub` claim that isn't a real URI)
│   │   │   ├── suggestions_service.py → proactive suggestion generation + custom schedule management
│   │   │   ├── web_search_service.py  → Tavily API web search (for chat research mode)
│   │   │   ├── infisical_loader.py    → Infisical secrets pull on startup; token validation + file storage
│   │   │   ├── features_service.py    → feature flags + role resolution (get_effective_disabled)
│   │   │   ├── assets_service.py      → assets core: templates, field validation, tree ops, per-node archive (+cascade), share/hidden resolution, pool conversion, history, attachments; `asset_links_contact(asset, template, contact_id)` — "does this asset reference this contact in any contact-type field" — shared by `list_assets_for_contact` and the dashboard Collection block resolver, one implementation not two
│   │   │   ├── assets_index.py         → derived share-routing cache (_system/assets_share_index.json); rebuildable, warmed at startup; sharers_for()/reindex_owner()/rebuild_share_index()
│   │   │   │   # Phase 2: per-user templates in USERS/{name}/Assets/templates.json (global in _system/asset_templates.json); assets ref template_id; request-based sharing (accepted[]) + accept/decline notifications
│   │   │   ├── finance_service.py     → finance core: books/accounts/categories/transactions (per-book per-year shards), computed balances, _resolve_book_access (single access gate); transactions carry an optional transfer_pair_id + denormalized transfer_peer_* fields (book/account/workspace) for Transfer legs; get_transaction_by_transfer_pair() looks up a leg's counterpart
│   │   │   ├── finance_reports.py     → finance reports computed on read: monthly income/expense by category, net worth
│   │   │   ├── simplefin_service.py   → SimpleFIN bridge client: claim setup token → read-only access URL (per-user secret), account mapping, sync engine w/ dedup + error throttle
│   │   │   ├── finance_import_service.py → CSV statement import: preview + column-mapped commit, import_hash dedup, Decimal→cents parsing
│   │   │   ├── finance_planning_service.py → budgets+alerts, recurring bills (matching/advance/missed), planned items, projection, deviation checks, nightly sweep
│   │   │   ├── finance_invoice_service.py → clients (reserved contact_id for future CRM), invoices (derived totals/overdue, auto-numbering), payments, AR rollup
│   │   │   ├── finance_index.py       → derived share-routing cache (_system/finance_share_index.json); rebuildable, warmed at startup; sharers_for()/reindex_owner()
│   │   │   ├── contacts_service.py     → Contacts core: contacts/interactions/deals, custom fields, pipeline, asset-style sharing (resolve_access read/contribute/edit), find_match dedup, follow-up reminders, self-contact (self_of marker, get/create_self_contact, cross-workspace resolution; type is guarded to stay "person" — a self-contact can't become a company), affiliated_contact_ids link/unlink, private-field stripping (_strip_private), format_profile_text() (AI chat context); company-type-only structured fields locations (capped list) + hours (always 7 entries, Mon–Sun) via _validate_locations()/_validate_hours(); custom field definitions carry `applies_to: ['person','company']` (_validate_applies_to, default both), fields_for_type(contact_type) filters a definition list by it — ContactModal.jsx/ContactDetail.jsx call this to only render matching-type fields
│   │   │   ├── contacts_index.py       → derived share-routing cache for Contacts (_system/contacts_share_index.json); warmed at startup
│   │   │   ├── notes_index.py          → derived share-routing cache for Notes (_system/notes_share_index.json); scans each store's Notes/_shares.json; warmed at startup
│   │   │   ├── automations_config.py  → instance automation API token (generate/rotate/verify) for n8n → LogCore writes
│   │   │   ├── automation_inbox_service.py → Automation Inbox: named inboxes (notify/reviewers/workflow routing), item dedup by (workflow_key, external_id), status lifecycle, trim, batched notifications
│   │   │   ├── n8n_service.py         → n8n REST API client; import/execute/delete/activate workflows; write docker/n8n.env; sync_business_workflows() for auto-sync
│   │   │   ├── ha_service.py          → Home Assistant REST API client; config CRUD, entity states, service calls, scenes, automations, user favourites
│   │   │   ├── help_service.py        → Help content single source (loads content/help.json): get_content, as_text (markdown for the AI, incl. /help#id anchors), capabilities_index (enabled-modules index for chat context), onboarding state get/set
│   │   │   ├── whats_new_service.py    → on version bump, notify every user once (announce_if_updated at boot) + drive the few-day What's-New banner (get_banner); state in _system/whats_new_state.json
│   │   │   ├── update_service.py      → GitHub release check (cached 4h), pending_update flag trigger, update log reader
│   │   │   ├── ai_usage_service.py     → AI usage metering + caps: daily-bucketed usage in _system/ai_usage.json, derived daily/weekly/monthly totals, per-user hard/soft cap enforcement + warn/over notifications; the single place chat_completion/agent_completion record usage
│   │   │   ├── dashboards_service.py   → Custom Dashboards core: CRUD, resolve_access() (mirrors finance_service._resolve_book_access), floor-of-one delete protection, share_underlying_data owner-only setter, self-healing default resolution; also the Dashboard Templates instance side — `_sync_blocks_from_template`/`_sync_templated_dashboard` (self-healing sync-on-read, same shape as the default-resolution above: reconcile a templated dashboard's `blocks` against its template's current blocks, keeping each existing slot's own layout untouched — the entire "block set stays synced, layout stays independent" mechanism in one pure function), `_apply_layout_only` (server-enforced layout-only PATCH for templated dashboards), `set_subject`/`detach_template`, `_attach_template_labels` (denormalizes `_template_label`/`_template_icon` onto every listed dashboard for the grouped-navigation UI)
│   │   │   ├── dashboard_templates_service.py → Dashboard Templates CRUD, near-verbatim mirror of assets_service.py's template section (two-tier global/personal stores, `visible_templates`, personal-template sharing handshake, `template_reference_count`/delete guard). A template is `{label, icon, subject_type: contact|asset|null, blocks: [{id, type, config}]}` — no stored layout (a newly-synced instance slot gets an auto-stacked layout instead, computed in dashboards_service.py); `config` may use the literal sentinel `"$subject"` on a contact_id/asset_id field, substituted per-instance at render time (see dashboard_blocks/render.py)
│   │   │   ├── dashboard_index.py      → derived share-routing + reverse "referenced by" cache for Dashboards (_system/dashboard_index.json); mirrors assets_index.py, keyed off each block type's declared record_ref_fields (no per-block-type hardcoding)
│   │   │   ├── dashboard_blocks/       → block-type registry + resolver package: registry.py (BlockSpec/REGISTRY), render.py (the security-critical two-pass render_block — read-through-never-a-bypass + the one share_underlying_data exception; also `_resolve_subject_config` — the one central place a templated dashboard's `"$subject"` config sentinel gets substituted with that instance's own `subject_id` before any resolver runs, so no resolver below needs to know the sentinel exists), _tasks.py/_home.py/_pool.py/_calendar.py/_finance.py/_contacts.py/_assets.py/_notes.py/_journal.py/_automations.py/_ai_usage.py/_freeform.py/_actions.py/_collections.py (one resolver module per source module family; _actions.py is display-only — nav_button/status_button/generic block actions' actual writes go through each target module's own existing endpoint directly from the frontend, never through here; also exposes a small reusable per-module label/lookup helper, shared by the standalone Action blocks and by any opted-in block's generic `actions[]` resolution; _contacts.py additionally registers `contacts_list` — a plain list-shaped block, the first general "list of contacts" block type; _collections.py's `resolve_collection` is the generic one — source (asset template + optional contact-link filter) / view (list/kanban/count) / action (a status field write, same `assetsApi.update` call status_button already makes) instead of a new hand-coded resolver per use case), agent_schemas.py (`AGENT_CONFIG_SCHEMAS` — maintained Python mirror of `blockRegistry.js`'s `CONFIG_FIELD_SCHEMAS` for the chat agent's `get_dashboard_block_catalog` tool, flattening the one frontend-only composite picker kind into flat config keys)
│   │   │   ├── user_deletion_service.py → admin user-deletion orchestration: preview (owned+shared items across Assets/Finance/Contacts/Notes + read-only blast radius), completeness validation, execute (transfer/delete decisions → reference cleanup in every other store → index rebuild → batched new-owner notifications → account+Brain-folder delete, in that order)
│   │   │   └── presence_service.py → app-wide online/offline tracking, generalized from agent_service.py's chat-only `record_chat_presence`/`is_chat_present`; one small per-user file (`presence.json`, not a shared multi-writer file), `record_presence()`/`is_online()` (90s staleness — a bit looser than chat's 45s, one ping interval not tied to a specific view)
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
│           │   ├── api.js         → ALL API calls go here — never fetch() directly in components; injects X-Workspace header on every request; chat.send/chat.resume take `chatId` as their first param, chat.sessions()/chat.markSessionRead() back the Chats drawer
│           │   ├── auth.jsx       → useAuth() hook + AuthProvider; polls /me every 30s; preferences server-only (not in localStorage)
│           │   ├── constants.js   → ALL_MODULES registry (must match backend require_module IDs), CATEGORY_COLORS, DEFAULT_SHORTCUTS, getShortcutsForUser(user, workspace), scoreTask(task, categoryOrder, todayStr) — JS port of priority_service.py's score_task(), used by Tasks.jsx's Priority sort mode
│           │   ├── workspace.jsx  → WorkspaceProvider context + useWorkspace() hook; persists active workspace to localStorage
│           │   ├── theme.js       → CSS variable theme engine (accent color, dark mode, background, density, corners)
│           │   └── deepLinks.js   → MODULE_ROUTES + deepLinkUrl(module, recordId) — single source of truth for "module → route" and its record-deep-link query param, used by Layout.jsx's notification navTarget() and the dashboard's nav_button block so URL construction is never hand-maintained in two places; RECORD_PARAM's `chat: 'chat_id'` + Layout.jsx's `open_chat` navTarget case route a chat notification straight into that conversation
│           ├── pages/
│           │   ├── Dashboard.jsx  → Custom Dashboards: single-dashboard viewer/editor (?id= deep link, falls back to the resolved default), view/edit mode, delegates rendering to components/dashboard/; a templated dashboard (`current.template_id`) hides "+ Add Block" and passes `blocksLocked` through to DashboardGrid/BlockRenderer since its block set is template-controlled — only layout stays freely editable; "+ New Dashboard"/empty-state both open CreateDashboardModal.jsx instead of creating blank directly; renders DashboardHero.jsx above the grid whenever `current.subject` is present
│           │   ├── Tasks.jsx      → personal task management (flat list, no category headers — sorted by a "Sort by" control: Priority score via lib/constants.js's scoreTask(), Date/Time, or Alphabetical, remembered in localStorage; filter tabs, edit modal, household assigned tasks); `?task=` deep link opens that task's edit modal (mirrors Assets.jsx's `?asset=` pattern)
│           │   ├── Goals.jsx      → standalone Goals page at /goals (gated by tasks module): filters tasks where type='goal', progress bar, category grouping
│           │   ├── Chat.jsx       → AI chat: plan/auto/research modes, proposal cards, step trace, memory save; multi-conversation — state keyed by `chat_id`, the "Chats" drawer (fed by `chat.sessions()`) opens a conversation directly on click (no preview step) with active/unread indicators per row, cleared on open; `newChat()` starts a fresh `chat_id`; switching conversations doesn't block on one still running
│           │   ├── Calendar.jsx   → personal calendar (month grid, events + dated tasks overlay, EventModal); `?event=` deep link opens that event's edit modal
│           │   ├── Household.jsx  → household hub (personal workspace): shared task pool (all read/write), shared events (admin write)
│           │   ├── Team.jsx        → business team hub (business workspace): shared task pool, shared events — mirrors Household but on _team pool
│           │   ├── Notes.jsx      → markdown notes with folder tree, auto-save, create/delete/move; `?path=` deep link opens that note
│           │   ├── Journal.jsx    → daily journal (date picker, markdown editor per day, entry list)
│           │   ├── Brain.jsx      → browse + edit user's Brain markdown files directly
│           │   ├── Profile.jsx    → thin self-view: fetches the user's self-contact via /contacts/me, renders components/contacts/ContactDetail.jsx (read) / ContactModal.jsx (edit) with a local view/edit mode switch
│           │   ├── Automations.jsx → automations: Workflows|Inbox views — n8n workflow cards (import/run/logs) + Automation Inbox (item review actions, named-inbox chips, settings modal, ?view=inbox deep link)
│           │   ├── Assets.jsx      → assets: template-driven object tree (expand/collapse, filters, archived toggle), both workspaces
│           │   ├── Finance.jsx     → finance: book chips, Overview (balances + monthly summary) | Transactions (filters, add/edit, Transfer kind + TransferEditModal for linked-pair rows) views, both workspaces
│           │   ├── Contacts.jsx    → Contacts (CRM): list + search, alphabetical with A-Z jump strip, detail (fields/interactions/deals/money — company vs. person fields differ, see ContactModal.jsx), ContactModal, CSV import/export; both workspaces
│           │   ├── Help.jsx        → Help & Guide page: fetches /help/content; TOC chips, per-section cards (blurb/how-to/tips), search, "only my modules" filter, What's New, FAQ, Contact & Support (mailto); hash-scrolls to #section from ⓘ deep-links
│           │   ├── Home.jsx        → Smart Home: entity tiles by domain, scenes panel, HA automations, favourite stars
│           │   ├── Settings.jsx   → Settings drill-down menu (icon+label rows, no inline cards): Profile/Appearance/Notifications/Shortcuts(mobile)/Account rows + admin-only "Admin Settings" row
│           │   ├── settings/      → Settings sub-pages, one route per row (each with its own "← Back" header via components/settings/SettingsPageHeader.jsx):
│           │   │   ├── Appearance.jsx    → dark mode, accent color, background presets/upload, density, corners
│           │   │   ├── Notifications.jsx → ntfy channel+rotate, Web Push, Proactive Suggestions (merged from 3 former cards)
│           │   │   ├── Shortcuts.jsx     → shortcuts editor — drives both mobile's bottom bar AND (2026-08-18) desktop's sidebar "Pinned" section from the same per-workspace list; no longer mobile-only, row shown on every screen size in Settings.jsx
│           │   │   ├── Account.jsx       → timezone, "Your Brain" link (→ /brain), export Brain zip
│           │   │   ├── AdminMenu.jsx     → Admin Settings drill-down menu (admin-only): Users & Roles/AI/General/Team/Household/Hosting/Contact Fields rows
│           │   │   └── admin/            → one page per Admin Settings row (relocated from the old Admin.jsx + AiUsage.jsx, not rewritten):
│           │   │       ├── Users.jsx           → user list; "+ Add User" and "Role Definitions →" rows
│           │   │       ├── NewUser.jsx         → create-user form as its own page
│           │   │       ├── UserDetail.jsx      → per-user page: role, feature role, workspace access, pool-edit grants, module overrides, bank connection (claim/reveal/sync/disconnect), delete (routes to UserDeletionReview when the user owns shared items)
│           │   │       ├── UserDeletionReview.jsx → delete-review page: per-item transfer-to-user / transfer-to-pool / delete decisions (bulk-default + per-item override) for everything the user owns that's already shared, plus a read-only "will also lose access to" section
│           │   │       ├── RoleDefinitions.jsx → custom feature-role editor (create/edit/delete + module toggles)
│           │   │       ├── Ai.jsx              → AI Provider + Web Search + AI Usage & Limits (month picker, stat cards, defaults, per-user limits) — 3 sections, one page
│           │   │       ├── General.jsx         → Registration, Workspace visibility, Session Length (single global admin-set value, no per-user override), Updates
│           │   │       ├── Team.jsx            → Team pool priorities + PoolBankConnections (pool="team")
│           │   │       ├── Household.jsx       → Household pool priorities + Smart Home (Home Assistant config) + PoolBankConnections (pool="household")
│           │   │       ├── Hosting.jsx         → Hosting (domain/proxy/tunnel) + Managed Hosting (Infisical, self-hides when unconfigured) + n8n Automation + automation token reveal/rotate
│           │   │       └── ContactFields.jsx   → Contacts custom-field admin authoring screen (mirrors TemplateManager.jsx's add/edit/reorder/delete pattern) — key/label/type/select-options + a Person/Company `applies_to` checkbox pair, guards against unchecking the last remaining value; the only frontend caller of `PUT /contacts/fields` (none existed before this)
│           │   ├── Login.jsx      → login + register form
│           │   └── Setup.jsx      → first-time setup wizard (Personal/Business profile, priorities, timezone)
│           └── components/
│               ├── Layout.jsx     → root shell: sidebar nav, user menu, theme toggle, module access guard; notification navTarget() has an `open_chat` case (deepLinks.js's `chat` route) so a chat-completion/approval notification opens straight into that conversation
│               ├── settings/      → shared Settings/Admin building blocks: MenuRow.jsx (icon+label+subtitle+chevron row), SettingsPageHeader.jsx ("← Back" + title), PriorityList.jsx (shared by admin/Team.jsx + admin/Household.jsx), PoolBankConnections.jsx (per-pool SimpleFIN: read-only summary of members' accounts mapped in, plus a real connect/reveal/sync/disconnect + mapping UI for a bank account owned by the pool itself — independent instance per pool)
│               ├── TaskModal.jsx  → create/edit task form (title, category, type, recurrence, due date/time, assigned_to, linked asset)
│               ├── AssetModal.jsx → asset modal: opens an existing asset in read-first view (AssetView), Edit flips to the editor (dynamic template fields, attachments, share/hide selectors, history, 3-choice archive, delete/convert); auto-flips create→edit; a blank asset's `CustomFieldsEditor` now authors typed field defs (same 6 types Templates use, key auto-slugified from the label) + their values together, one row at a time, plus a "Save as template" action (`SaveAsTemplateModal`) that creates a real Template from those defs and attaches it back (2026-08-18)
│               ├── AssetView.jsx  → read-only asset overview: header, attachments, fields as label/value pairs, notes, child list (drill-in), linked tasks, sharing summary, history; ✎ Edit button (owner/editor only)
│               ├── assetDisplay.jsx → shared asset display helpers (no circular import): AttachmentThumb (image attachments open in a new in-app `ImageLightbox` — `.modal-overlay`-based, closes on ✕/backdrop/Escape — instead of a new browser tab, using the blob URL already held for the thumbnail; non-image files keep the existing new-tab open; the single shared component behind both AssetView.jsx's own attachment section and the dashboard Documents block), ImageLightbox, FieldInput, CapsSelector (contribute caps checkbox panel), formatChanges(), fieldDisplay()
│               ├── dashboard/     → Custom Dashboards UI: DashboardGrid.jsx (react-grid-layout wrapper — 36 cols/24px rows on desktop, 12 cols on mobile (MOBILE_COLS export), both breakpoints independently drag/resize-editable (`layout.lg`/`layout.sm` are genuinely separate saved layouts) with `compactType={null}` + `preventCollision={true}` so a block stays exactly where it's dropped/resized including snug side-by-side, instead of auto-shuffling neighbors; touch dragging is hand-rolled (press-and-hold ~550ms arms a block via a delegated capture-phase `touchstart` interceptor, since react-draggable itself has no start-delay concept — a plain swipe scrolls the page normally instead of grabbing a block; resize is untouched, still instant on the small corner handle) — real on-device iOS PWA verification of the *feel* is still the open item, mouse dragging is unaffected; `blocksLocked` prop, threaded straight through to BlockRenderer.jsx, doesn't touch any of this — a templated dashboard's layout stays exactly as draggable/resizable as a freeform one), BlockRenderer.jsx (dispatch by type + locked placeholder + "✎" edit-config button gated on `isConfigurable()`; threads an `onAction` callback to every block, a no-op for passive types; passes `actions={block.config?.actions}` through on both render paths so any `recordKind`-opted block can render its own configured buttons; the icon+label header — and blocks flagged `chromeless: true` get a small ✎/✕ corner overlay instead — are both edit-mode-only, zero reserved space in view mode, "makes it look cleaner" per 2026-08-06 owner request; a `locked` prop additionally suppresses just the ✎/✕ buttons, for a templated dashboard whose block set isn't locally editable; a `shape` lookup off blockRegistry.js — `'list'` drops the padded/bordered `.card` wrapper entirely for genuinely list-shaped blocks, default `'detail'` keeps today's card look — content-aware styling instead of every block getting identical box chrome regardless of what's inside it), DashboardHero.jsx (identity banner for a subject-bound dashboard — avatar/icon + name + the dashboard's own template label, reading the `subject`/`template_label` fields `GET /dashboards/{id}/render` now returns; renders nothing for a freeform or subject-less dashboard), blockRegistry.js (frontend render-component map mirroring the backend registry, plus `CONFIG_FIELD_SCHEMAS` — the per-block-type config field list keyed by picker `kind`, with an optional `showIf: {key, equals}` for fields that only apply to one branch of another field's value; several record-linked labels spell out their actual data source, e.g. "Contact's Deals", "Asset's Linked Contact"; `recordKind` (task/asset/contact/event/note, from `actionKinds.js`) opts a block into the generic action-button system — set on every `shape:'list'`/`shape:'detail'` block whose rows resolve through that module's own standard API by plain id; deliberately unset on `pool_tasks` since its rows route through `sharedApi`/`teamApi` by `_source`, not `tasksApi`; new `contacts_list` entry, the first general contacts-list block; re-exports `ACTION_MODULE_BY_KIND`/`ACTION_PRESETS_BY_KIND` from `actionKinds.js`), actionKinds.js (small shared constants — action-kind→module map + per-recordKind preset action lists — pulled out of blockRegistry.js/blocks.jsx into its own file specifically so both can import it without a circular import, since blockRegistry.js already imports render components from blocks.jsx), blocks.jsx (30+ block presentational components, including `StatusButtonBlock` — the first write-capable block; it calls each target module's own existing endpoint directly, e.g. `tasksApi.update`/`contactsApi.update`(contact fields)/`assetsApi.archive`, never a dashboard-specific write path; it and `NavButtonBlock` render as a bare `.btn-pill` — no surrounding text — so several fit in a small space, and both correctly show a config'd custom `label` now (2026-08-06 fix: the backend resolvers never forwarded it); `runStatusAction`/`ActionButton`/`BlockActionButtons` are the generic action-button trio reused by every `recordKind`-opted block — `BlockActionButtons` renders once per row for list-shaped blocks and once for the whole block for detail-shaped ones, reusing `nav_button`/`status_button`'s exact click logic rather than a new write path; new `ContactsListBlock`), BlockPicker.jsx ("+ Add Block" catalog + config form; dual add/edit mode via an optional `editingBlock` prop; renders a real search/tree/select picker per field `kind` — never a raw id/path text box; filters fields by `showIf` before rendering; a search input filters the type-grid step client-side by label, so 30+ tiles across 4 categories stay findable; `templateMode`/`subjectType` props — set only when DashboardTemplateManager.jsx reuses this same component to edit a *template's* block — add a "$subject" checkbox on any contact/asset-kind field matching the template's own subject type, storing the literal sentinel instead of a picked id; new `ActionsEditor` repeater — modeled on `LocationsEditor`'s add/remove/edit shape — appears whenever the selected block type has a `recordKind`, letting the user author/reorder the block's own `actions[]` config), ModuleAndRecordPicker.jsx (nav_button's target picker: pick a module page — or Settings, a hand-added extra option since it isn't a real module — then optionally narrow to one specific section/sub-page (`MODULE_SECTIONS` in `lib/deepLinks.js`, e.g. Finance's Budgets tab or a specific Settings page) or one specific record, mutually exclusive; `dashboard` is a record-linkable module too via `DashboardPicker.jsx`, so a nav button can jump to one particular dashboard by id rather than only ever landing on your current default), DashboardPicker.jsx (nav_button's dashboard-record picker — a `<select>` over `dashboardsApi.list()`, same base shape as `finance/FinanceBookPicker.jsx`, only ever offers dashboards the viewer can already see; options are grouped into native `<optgroup>`s by each dashboard's `_template_label`, mirroring DashboardSwitcher.jsx's own grouping off the same server-denormalized field), CreateDashboardModal.jsx (new-dashboard flow: blank or from-a-template; picking a template with a `subject_type` shows the matching ContactPicker/AssetPickerField before creating — replaces the old direct blank-create calls in Dashboard.jsx's empty state and DashboardSwitcher.jsx's "+ New Dashboard"), DashboardTemplateManager.jsx (Dashboard Templates CRUD UI, structurally mirrors TemplateManager.jsx — list/edit/share views, own/global/shared sections, admin gating for global — but the per-template form manages a *block list* via BlockPicker.jsx in `templateMode` instead of field definitions; no grid/layout editing here by design, see dashboards_service.py's sync mechanism for why), TemplatePicker.jsx (the Collection block's "show records from" field — plain `<select>` over `assetsApi.listTemplates()`, picks a whole template/kind-of-record, not one asset instance), TemplateFieldsPicker.jsx (the Collection block's "fields to show" — checkbox multi-select over a chosen template's own field keys), AssetSelectFieldPicker.jsx (pick one of a source's own select-type template fields, then one of that field's own options — both picked, never typed; source is either one specific asset via `assetId` (status_button's "set an asset field" action, reads the asset's embedded `_template`) or a whole template directly via `templateId` (the Collection block's "status field" config, which has no single asset instance to read from) — exactly one of the two props is passed by any given caller), ContactFieldPicker.jsx (status_button's "update contact data" picker: same two-stage pick-field-then-pick-value shape, but a hardcoded field list — `gender`/`marital_status` — since Contacts have no per-instance template to read options from, and most other seemingly-pickable Contact fields are either free text or private), DashboardAccessModal.jsx (sharing + share_underlying_data toggle; target picker is a real `<select>` of members/household/team/roles via `GET /dashboards/members`+`/roles`, not free text), DashboardSettingsModal.jsx (per-dashboard options: rename, change icon via EmojiPicker, Share/Set as default/Delete — replaces what used to be a loose row of buttons in the edit toolbar, both to give dashboards an actual settings surface and because that wider row was overflowing awkwardly on mobile; for a templated dashboard, also shows its template's label, a "Change subject" inline Contact/AssetPickerField, and "Detach from template" — the escape hatch that freezes current blocks/layout in place as an ordinary freeform dashboard), DashboardSwitcher.jsx (searchable dashboard picker; groups by `_template_label` into collapsible sections with an "Other" bucket for ungrouped dashboards whenever there's no active search query — a live query flattens back to a plain filtered list; "+ New Dashboard" opens CreateDashboardModal.jsx, a "Templates" button opens DashboardTemplateManager.jsx), LockedBlockPlaceholder.jsx
│               ├── TemplateManager.jsx → admin template editor: ordered typed fields (TagInput options), EmojiPicker icon, defaults, example insert
│               ├── TagInput.jsx    → GitHub-topics-style chip input (free-text or strict selector mode); inline capped suggestion box — template options, share/hide members
│               ├── EmojiPicker.jsx → curated self-contained emoji grid popover (right-aligned) for template icons
│               ├── AssetTreePicker.jsx → foldered expand/collapse asset picker; reused by Move + create-asset parent chooser
│               ├── AssetPickerField.jsx → compact single-asset field (current selection + "Change ▾" toggles an inline AssetTreePicker) — same idiom as AssetModal's own parent picker; used by dashboard record-linked block config
│               ├── TaskPicker.jsx, EventPicker.jsx, NotePicker.jsx, WorkflowPicker.jsx → ContactPicker-pattern search-autocomplete pickers (single id/path value, graceful fallback to plain text if the list fetch fails) over the user's own tasks/calendar events/notes/n8n workflows; used by dashboard record-linked block config so no block ever needs a raw id typed in
│               ├── finance/       → finance components: TransactionModal.jsx (+tax flags+receipts+ContactPicker payee; Transfer kind swaps category/payee for a cross-book/cross-workspace To Book+To Account picker with client-side currency-match validation), TransferEditModal.jsx (edit/delete a linked transfer pair together — amount/date/notes, both legs), BookSettings.jsx (accounts/categories/tax buckets/CSV import), SimpleFinPanel.jsx (bank connect+mapping), BudgetsPanel.jsx, RecurringPanel.jsx (+planned one-offs+deductible), InvoicesPanel.jsx (invoices/payments via ContactPicker + AR + printable InvoicePrint), ReportsPanel.jsx (P&L + tax export), FinanceBookPicker.jsx (plain-select book picker; used by dashboard record-linked block config), money.js (cents↔display helpers)
│               ├── contacts/      → ContactDetail.jsx (read-first `<dl>`-grid card, shared by Contacts.jsx and Profile.jsx — self-contact "(ME)" badge, affiliated-contacts chips, career history, profile-merge field sections, `fullPage` mode, owner-only "hidden from others" badges next to a hidden section's heading), ContactModal.jsx (edit form — same profile-merge fields, private-only-when-self, affiliation picker, career history resume editor with direct past-role add/edit, photo upload, priorities reorder editor, `fullPage` mode, convert-to-pool button, per-section hide toggles via SectionHeader.jsx), ContactAvatar.jsx (shared photo-or-fallback-icon avatar + `useContactPhotoUrl()` hook — fetches the photo as an authenticated blob since a plain `<img src>` can't carry the `X-Workspace` header; used by the Contacts list, ContactDetail's header, and ContactModal's photo uploader preview; also renders the online/offline presence dot overlay and the click-to-open last-seen popover, anchored off the avatar's left edge; fires an optional `onPopoverToggle` callback so ContactRow (Contacts.jsx) can raise its own row's stacking context above sibling rows while open, 2026-08-18), ContactPicker.jsx (search-first contact autocomplete + quick-create; reused by transaction payee + invoice client + affiliation/employer pickers), BulkConvertContactsModal.jsx (checklist, defaults to everything selected — converts many of the caller's own personal contacts into the workspace pool at once, 2026-08-17), SectionHeader.jsx (section heading + optional self-contact-owner-only "Hide from others" toggle, 2026-08-18), phone.js (shared `formatPhone(p)` display formatter — used by ContactDetail.jsx and Contacts.jsx's list-row preview; the list row previously showed the raw undashed digits, a separate bug from ContactDetail's own formatting, 2026-08-15), presence.js (`formatLastSeen()` — minutes for the first hour, hours up to a day, days uncapped after that, 2026-08-17)
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
│   ├── _system/automations_index.json → business workflow metadata (n8n IDs + tags)
│   └── _system/ai_usage.json      → AI usage metering + caps: per-user daily buckets (messages/tokens, personal+business), defaults, mode/period/limits, alert dedup — operational metadata, never in a user's portable Brain folder
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
