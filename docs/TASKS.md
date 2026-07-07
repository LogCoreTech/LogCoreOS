# TASKS.md — LogCoreOS Active Work Queue

Keep this up to date. Mark tasks done as they're completed. Add new tasks as they surface. This is the single source of truth for product work.

**Structure:** active build work → launch surface → features that unblock scale → backlog. Work top-down.

---

## Now — active build work

- [ ] **Automation Inbox** — workflows write structured output to Brain JSON; users see results with per-item actions (Interested / Pass / Offer Made / Closed); workflow skips already-reviewed items
- [ ] **Land lead search & qualify workflow** — n8n pulling land listings (multiple sources with a fallback from day one) and AI-qualifying against configurable criteria; stub file in `automations_stubs/`; Brain JSON output schema; depends on Automation Inbox

## Launch surface (do in order)

- [ ] **Privacy policy page on logcoretech.com** — blocker before demo goes public (GDPR/CCPA)
- [ ] **Terms of service page on logcoretech.com** — needed for demo and managed hosting
- [ ] **New Cloudflare Tunnel token for demo VPS** — set to `demo.logcoretech.com`; do before provisioning
- [ ] **Provision Hetzner CX22 for demo instance** — ~€4.50/mo, separate from personal
- [ ] **Deploy LogCore on demo VPS** — full stack (app + ntfy + n8n + tunnel), open registration on
- [ ] **AI cost protection for demo** — Haiku model AND a per-user daily message cap in the chat router; the cap is non-negotiable before any launch post
- [ ] **Daily demo reset script** — cron wipe of non-admin Brain folders + auth entries nightly
- [ ] **Demo banner in UI** — "this is a demo, data resets nightly"
- [ ] **UptimeRobot monitoring on demo URL** — free tier, set up immediately after deploy
- [ ] **Off-site backups for demo VPS** — Hetzner snapshots or object storage; on-box backup.sh alone is not a backup
- [ ] **Screenshots in README** — 3+ images + a 30-second GIF of the AI using its memory
- [ ] **CONTRIBUTING.md** — how to run locally and submit a PR
- [ ] **GitHub issue templates** — bug report + feature request
- [ ] **Website: copy refresh + Try the Demo CTA** — CTA → demo.logcoretech.com; add comparison table (LogCoreOS vs Khoj / Notion AI / Open WebUI)
- [ ] **OG/social preview image for logcoretech.com** — `<meta og:image>` with branded screenshot
- [ ] **Waitlist form** — Formspree, capture interest before self-serve signup exists
- [ ] **Cloudflare Analytics enabled** — one toggle, free
- [ ] **LinkedIn company page** — BLOCKED: LinkedIn requires a registered company (LLC) to create a page; revisit after LLC formation (business-side, tracked in private Business repo) (2026-07-06)

## Features that unblock scale (build when demanded)

- [ ] **Assets module — REQUIRED BEFORE PILOT CLIENT** — owner flagged as important (2026-07-06); scope not yet defined (asset tracking for household/business — equipment, property, inventory?). Needs a definition session before build: data shape under the Brain (`Assets/assets.json`?), workspace scoping, module ID `assets` in constants.js + backend router

- [ ] **Ollama / local LLM support** — pulled forward from roadmap Phase 6; #1 r/selfhosted credibility feature; ship before/with the Reddit launch
- [ ] **RAG over the Brain (v0.2)** — embeddings + semantic search over notes/journal/files, auto-fed into chat context. Design rule (locked): vector index is a disposable derived cache — embedded file-backed store (e.g. Chroma), rebuildable from Brain files anytime, never source of truth, no new stateful service. Local-embeddings option pairs with Ollama. Target with the public demo
- [ ] **AI-built n8n automations (v0.4)** — natural language → generated workflow + preview/approve before activation; the flagship demo
- [ ] **Automation Inbox generalization** — from land-leads-specific to any workflow writing reviewable results
- [ ] **Instance provisioning script** — one command: VPS → tunnel → Infisical → configured instance
- [ ] **Importers: Todoist / Notion / Obsidian → Brain** — "import my digital life"
- [ ] **Stripe billing portal** — self-serve paid signup for hosted plans
- [ ] **Monthly value report** — auto-generated from Automation Inbox data (leads found, actions taken, hours saved)
- [ ] **Email digests + richer proactive digest (v0.3)** — calendar/journal-aware "what matters today"; email delivery (ntfy is a barrier for non-technical users; notifications block already designed in PROJECT.md)

---

## Product Backlog (pull in when demand appears)

- [ ] **User-customizable Dashboard per workspace** — widget config per-workspace in `brain/USERS/{name}/Dashboard/personal.json` and `business.json`; widgets: Top 3 Tasks, Streaks, Due Today, Smart Home (personal), Team Tasks (business)
- [ ] **Projects module** — project tracking with tasks, milestones, and status
- [ ] **Multi-day calendar events** — `start_date` / `end_date` schema + calendar renderer that spans cells
- [ ] **Personal calendar task completion toggle** — tasks in CalendarGrid day detail panel need a done/undo button
- [ ] **Projects / chat system evolution** — ChatGPT/Claude-style Projects: named projects with custom context, per-project chat archives, optional agent usage
- [ ] **Shared notes with per-user permissions** — Google-Docs-style: creator picks edit/read-only per user at note creation; shared notes readable/writable by both users and the AI, with the AI bound by the same per-user permission when acting on someone's behalf (requested 2026-07-06)
- [ ] **Quick capture** — email-to-inbox (forward email → task/note), PWA share_target, quick-add hotkey; capture must take <2 s (backlogged 2026-07-06 — pull on demand)
- [ ] **Recurring-task upgrades** — rrule-based patterns ("every 2nd Tuesday") + natural-language date parsing (v0.3; basic recurrence + streaks already exist)
- [ ] **Journal → insight loops** — weekly AI pattern detection (mood vs sleep etc.) beyond the existing weekly review (backlogged 2026-07-06)
- [ ] **Offline-first PWA sync** — local-first data + background sync + conflict resolution; structural advantage of file-based storage, but a big lift (backlogged 2026-07-06)
- [ ] **v1.0 trust stack — gates the Show HN post** — app-level 2FA, automated backups + one-click restore, audit logging, <10-min onboarding, real docs, test-coverage push; plugin API if feasible

---

## Done

- [x] **Chat "approve edits" mode — new default** — reads run freely, every write tool call pauses (`awaiting_approval` + `pending_write` steps) and the UI shows an ApprovalCard (Approve → one-turn auto re-send; Deny → conversational decline); `_READ_TOOLS` allowlist means future tools are write-gated by default; default mode switched to `approve` in backend + frontend; 5 tests (2026-07-06)
- [x] **BUG: proactive notification injection breaks chat + writes junk archives** — proactive messages are now display-only: `toApiHistory()` strips them and trims history to the validator's shape (start user / end assistant, also heals older junk archives on continue); auto-save skips proactive messages and proactive-only threads (2026-07-06)
- [x] **GitHub Discussions** — was already enabled on the repo (confirmed 2026-07-06)
- [x] **BUG: AI responses lost from saved chat history** — root cause was the archive parse, not the save: `parseSavedChat()` kept only lines starting with `**You**:`/`**AI**:`, dropping every continuation line of multi-line responses; continuing a chat then auto-saved the truncated parse back over the same file. Parser now accumulates continuation lines; saved-chat viewer renders full multi-line bubbles; history content cap raised 5000→30000 (long agent responses were silently 422ing the auto-save) (2026-07-06)
- [x] **BUG: agent member-name resolution on shared task assignment** — `add_shared_task`/`update_shared_task` now resolve `assigned_to` against real members via `_resolve_member_name()` (exact → first-name → prefix, case-insensitive); ambiguous/unknown names return an error listing candidates so the agent asks instead of guessing; new `list_household_members` agent tool; 16 tests added (2026-07-06)
- [x] **GitHub Release v0.1.0 published** — CHANGELOG stamped, release live, built-in updater now has a target (2026-07-06)
- [x] **CI green + badge** — first green run after 92 failures: black formatting applied, 4 stale lifecycle tests rewritten to nightly-archive behavior, badge live in README (2026-07-06)
- [x] **GitHub repo description + topics** — About section filled with description + ~16 topics (2026-07-06)
- [x] **Self-hoster update flow** — `docker/update.sh` handles in-place updates with auto-rollback; Admin → Updates card shows current vs latest version; `launch.sh --auto-update` installs cron for hands-free updates; daily scheduler job refreshes version cache (2026-07-05)
- [x] **Household task assignment for non-admins** — resolved 2026-07-02: `GET /shared/members` + `GET /team/members` expose the member list to admins and users with the `pool_edit` grant, feeding the assign dropdown for granted non-admins
- [x] **Pool permissions + workspace visibility + calendar/admin fixes** — (1) Admin page mobile overflow fixed (`w-full` root, `flex-wrap`+`min-w-0`/`truncate` on UsersCard/RolesCard rows); (2) household/team tasks on the personal calendar now carry the 🏠/🧑‍🤝‍🧑 badge and hide/show with the pool toggle pill (matching events); (3) assigned pool tasks open TaskModal read-only (no Save/Delete, Cancel→"Close") — was 404'ing on save; (4) instance-wide **Workspaces** admin card hides a whole workspace for everyone incl. admins via `enabled_workspaces`; (5) per-user **pool_edit** grant (`household`/`team`) gives full pool-manager parity (add/edit/delete events + tasks + assign), default off, admins always; new `/shared/members` + `/team/members` feed the assign dropdown (2026-07-02)
- [x] **UI bug fixes — sign-out, Brain back button, pool priorities keyboard, horizontal scroll** — sign-out moved to sidebar (desktop) and mobile drawer footer; Brain file list view now has ← Settings back button; PriorityList extracted to module level (was defined inside PoolPrioritiesCard causing keyboard dismissal on every keystroke); overflow-y-scroll on Layout main fixes scrollbar-induced layout shift; Admin feature-role row gets flex-wrap; Calendar wrapper gets w-full; POOL_DEFAULT_TEAM updated with business-relevant defaults (2026-07-01)
- [x] **Workspace-aware priorities + pool category lists + assigned task bleed-through** — `profile_service` and `priority_service` are now workspace-aware (business tasks scored by `Business/profile.json` priorities); `GET/PUT /priorities/pool` admin endpoints let admins set category order for `_household` and `_team` pools; `GET /tasks/assigned` returns pool tasks assigned to current user; Tasks.jsx shows assigned pool tasks with 🏠/🧑‍🤝‍🧑 badges and routes completions to the right pool; Profile.jsx reloads on workspace switch and re-labels priorities section; Admin page has new Pool Priorities card (2026-07-01)
- [x] **Workspace-aware Dashboard** — personal workspace shows SmartHome widget; business workspace shows TeamWidget (pending team tasks + link to /team); `key={workspace}` on root div forces full remount on switch; HomeWidget gated to personal-only (2026-07-01)
- [x] **Workspace mode switching fixes + chat workspace awareness** — Calendar/Tasks/Notes auto-refresh on switch; workspace-restricted modules (Journal, Household, Team) auto-redirect to dashboard; Calendar pools switch Household↔Teams with workspace; Chat saves/reads/searches workspace-specific Brain files; optional cross-workspace AI search toggle for dual-workspace users (2026-07-01)
- [x] **Per-workspace shortcuts settings** — Settings page now shows separate Personal and Business shortcut panels; picker filters by disabled modules and workspace; `cleanShortcuts()` strips invalid IDs at init so slots are genuinely empty; both workspaces saved in one PATCH call (2026-06-30)
- [x] **Shortcuts disabled-module leak fix** — shortcuts picker previously showed all modules regardless of `disabledModules` or workspace constraint; now correctly filtered (2026-06-30)
- [x] **Automations module (n8n)** — personal/business workflow tabs, import/run/logs, Admin n8n card, Infisical secret sync to n8n.env, bundled n8n Docker service (2026-06-29)
- [x] **Automations granular tab access control** — `automations` and `automations_business` as separate module IDs; `nav: false` pattern for sub-feature modules; Personal/Business tabs render dynamically based on user.disabledModules (2026-06-29)
- [x] **Business workflow auto-sync** — stub files in `app/backend/automations_stubs/` drive what workflows should exist; app fetches actual JSONs via `WORKFLOWS_BASE_URL` + `WORKFLOWS_TOKEN` (Infisical secrets); reconciles n8n on startup + every 6 hours; self-hosters skip silently (2026-06-29)
- [x] **Home Assistant integration** — `home` module: Smart Home page with entity tiles (light/switch/sensor/climate/cover/lock), scenes panel, automations panel, favourite star pinning, Dashboard widget for favourites; Admin → Smart Home card (URL + token + test); 4 AI chat tools; config at `brain/_system/ha_config.json` (2026-06-29)
- [x] **Admin UX fixes** — feature role dropdown always-visible in Users card; RolesCard description truncation fix (2026-06-29)
- [x] **Setup wizard** — profile type (Personal/Business) now only shown for first user setup (2026-06-29)
- [x] **Rate limiting** — added missing write-endpoint rate limits to shared.py (2026-06-29)
- [x] **Error handling** — Dashboard and Chat silent swallows replaced with surfaced error states (2026-06-29)

*(tracking starts from here — see git log for earlier history)*

---

## Format

```
- [ ] Task name — short description of what done looks like
- [x] Completed task — what was done (YYYY-MM-DD)
```
