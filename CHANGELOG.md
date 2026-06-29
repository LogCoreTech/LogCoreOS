# Changelog

All notable changes to LogCore OS are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Added

**Workspace switching (personal / business)**
- Users can be granted access to one or both workspaces (`personal`, `business`) by an admin
- Active workspace persists in `localStorage` and is sent on every API call as `X-Workspace` header
- Tasks, Calendar, Notes, and Journal are fully workspace-scoped — personal data in `brain/USERS/{name}/`, business data in `brain/USERS/{name}/Business/`
- Sidebar workspace toggle pill appears automatically when a user has access to both workspaces
- Per-workspace module control — admins can enable/disable modules independently per workspace in the Admin panel
- `disabled_modules` in auth.json is now a workspace-keyed dict (`{"personal": [...], "business": [...]}`) with backward compat for the flat-list format

**Team module (business workspace)**
- New `Team` page: shared task and event pool for business teams — mirrors Household but backed by `_team` pseudo-user pool, completely isolated from household data
- `team` module defaults enabled for business feature role, disabled for personal
- Team events (admin-only write) and tasks (any team member) follow the same CRUD shape as Household

**Smart Home (Home Assistant) integration**
- New `Home` page: entity tiles by domain, scene control, HA automation on/off, per-user starred favourites
- Starred entities appear as a widget on the Dashboard
- Admin config panel (HA URL + long-lived token) in Admin → Smart Home

**n8n Automations integration**
- New `Automations` page: personal and business workflow cards with run + logs
- Business workflows auto-synced on startup from `automations_stubs/` committed stubs
- Admin config panel (n8n URL + API key) in Admin → n8n

**Admin panel improvements**
- Per-workspace module toggle UI (Personal / Business tabs) per user
- Workspace access checkboxes (personal / business) per user
- n8n and Smart Home configuration cards

---

## [0.1.0] — 2026-06-27

### Added

**Core platform**
- FastAPI backend with JWT authentication, bcrypt passwords, and JTI revocation
- React 18 / Vite / Tailwind CSS frontend, installable as a PWA
- Docker Compose stack with automated health checks
- `launch.sh` one-command startup script with `--install-deps` flag for automatic prerequisite installation on Linux

**AI**
- AI chat with full Brain context injection (priorities, tasks, memory, profile)
- Tool use support within chat
- Automatic chat archiving to Brain files
- Anthropic API integration via pluggable `ai_provider` abstraction

**Modules**
- Tasks — personal task management with life-priority scoring, recurring tasks, streak tracking, and history archival
- Notes — folder-based note editor with auto-save
- Journal — daily entries by date
- Calendar — personal events and dated task view
- Household — shared tasks and events across all household members with admin controls

**Scheduler**
- Nightly recurring task processor and history archival
- Configurable morning digest and overdue notifications via ntfy
- Weekly review summary

**Admin**
- User management
- AI provider settings
- Web search toggle
- Runtime hosting configuration (domain, HTTPS, proxy headers) — no restart required

**User settings**
- Accent colour, dark mode, background image, density, corner style
- Timezone
- Push notification subscription
- Session management

**Data portability**
- All user data stored as Markdown and JSON files in `brain/`
- Brain export as zip download
- No database — the filesystem is the database
