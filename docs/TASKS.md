# TASKS.md — LogCoreOS Active Work Queue

Keep this up to date. Mark tasks done as they're completed. Add new tasks as they surface. This is the single source of truth for what's being worked on.

---

## Active Tasks

*(nothing in flight)*

---

## Backlog

- [ ] **User-customizable Dashboard per workspace** — each user can choose which widgets appear on their personal and business dashboards and in what order; widget config stored per-workspace in `brain/USERS/{name}/Dashboard/personal.json` and `business.json`; available widgets: Top 3 Tasks, Streaks, Due Today, Smart Home (personal), Team Tasks (business) — more as modules are added
- [ ] **Projects module** — project tracking with tasks, milestones, and status (deferred to Phase 3+)
- [ ] **Multi-day calendar events** — calendar events currently support a single `date` field; true multi-day events (vacations, trips, blocks) need `start_date` / `end_date`, a backend schema update, and a calendar renderer that spans cells
- [ ] **Household task assignment for non-admins** — only admins can currently assign tasks because `GET /auth/users` is admin-gated; a `/shared/members` endpoint could expose the member list to all household members, enabling peer assignment
- [ ] **Personal calendar task completion toggle** — tasks shown in CalendarGrid day detail panel have no done/undo button; must navigate to Tasks page to un-mark done
- [ ] **Projects / chat system evolution** — evolve chat into a ChatGPT/Claude-style Projects feature: named projects with custom context, per-project chat archives, optional agent usage within each project

---

## Done

- [x] **Workspace-aware priorities + pool category lists + assigned task bleed-through** — `profile_service` and `priority_service` are now workspace-aware (business tasks scored by `Business/profile.json` priorities); `GET/PUT /priorities/pool` admin endpoints let admins set category order for `_household` and `_team` pools; `GET /tasks/assigned` returns pool tasks assigned to current user; Tasks.jsx shows assigned pool tasks with 🏠/🧑‍🤝‍🧑 badges and routes completions to the right pool; Profile.jsx reloads on workspace switch and re-labels priorities section; Admin page has new Pool Priorities card (2026-07-01)
- [x] **Workspace-aware Dashboard** — personal workspace shows SmartHome widget; business workspace shows TeamWidget (pending team tasks + link to /team); `key={workspace}` on root div forces full remount on switch; HomeWidget gated to personal-only (2026-07-01)
- [x] **Workspace mode switching fixes + chat workspace awareness** — Calendar/Tasks/Notes auto-refresh on switch; workspace-restricted modules (Journal, Household, Team) auto-redirect to dashboard; Calendar pools switch Household↔Teams with workspace; Chat saves/reads/searches workspace-specific Brain files; optional cross-workspace AI search toggle for dual-workspace users (2026-07-01)
- [x] **Per-workspace shortcuts settings** — Settings page now shows separate Personal and Business shortcut panels; picker filters by disabled modules and workspace; `cleanShortcuts()` strips invalid IDs at init so slots are genuinely empty; both workspaces saved in one PATCH call (2026-06-30)
- [x] **Shortcuts disabled-module leak fix** — shortcuts picker previously showed all modules regardless of `disabledModules` or workspace constraint; now correctly filtered (2026-06-30)
- [x] **Automations module (n8n)** — personal/business workflow tabs, import/run/logs, Admin n8n card, Infisical secret sync to n8n.env, bundled n8n Docker service (2026-06-29)
- [x] **Automations granular tab access control** — `automations` and `automations_business` as separate module IDs; `nav: false` pattern for sub-feature modules; Personal/Business tabs render dynamically based on user.disabledModules (2026-06-29)
- [x] **Business workflow auto-sync** — stub files in `app/backend/automations_stubs/` drive what workflows should exist; app fetches actual JSONs from private GitHub repo via `WORKFLOWS_BASE_URL` + `WORKFLOWS_TOKEN` (Infisical secrets); reconciles n8n on startup + every 6 hours; self-hosters skip silently (2026-06-29)
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
