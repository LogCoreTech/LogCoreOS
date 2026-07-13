# Changelog

All notable changes to LogCore OS are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Added

**Finance module (Phase B — bank sync + CSV import)**
- **Bank-linked spending data via SimpleFIN** — a read-only bridge: your bank password is never typed into LogCore and never stored anywhere; the connection can only READ balances and transactions, it can never move money, and it's revocable from SimpleFIN's side at any time
- Connections are **admin-managed**: a member taps "Request bank connection" in Finance → 🏦 Bank (admins get a notification with a jump button), the admin pastes the member's SimpleFIN setup token in the new **Admin → Bank Connections** card (connect / replace / sync now / reveal / disconnect per user)
- Members then map each connected bank account onto an account in their own books; only admins can point a bank feed at a shared Household/Team book
- Auto-sync every 12 hours (+ shortly after startup); imported transactions land as **Uncategorized** for you to file — and LogCore **learns your categorization**: categorize "KROGER #123" as Groceries once and every future Kroger charge files itself
- Re-syncs never duplicate: every bank transaction is tracked by its bank ID; sync failures notify you and the admins at most once a day
- **CSV import** for banks without SimpleFIN (or fully third-party-free tracking): upload a statement export in Book Settings, map the columns once, import — re-importing the same file skips everything it already has

**Finance module (Phase A — ledger core)**
- New **Finance** page: create money **books** (e.g. "Family budget", "LLC books") — each with its own accounts (checking/savings/credit/cash), fully customizable expense & income categories, and running balances computed from the ledger
- Works in both workspaces: personal books are **private to you (not even admins can see them)**; business books live in your business workspace; admins can create shared **Household/Team books** every member can view
- Log income and expenses with payee, category, notes; filter/search transactions; balances, monthly income-vs-expense summary and top spending categories on the book's Overview
- Dashboard **Finance widget** shows each visible book's balance and your net worth per workspace
- AI chat can read your finance data — "what did I spend this month?" works out of the box (read-only; finance write tools come later phases)
- All amounts stored as exact integer cents (no floating-point money), one year of transactions per file so books stay fast for decades
- The **guest** role has Finance disabled by default — money visibility is opt-in per user
- Coming in the next phases (already designed): SimpleFIN bank sync (admin-managed, read-only tokens), CSV import, budgets with overspend alerts, recurring bills, projected balances with deviation alerts, invoices/clients/tax, and asset-style book sharing with per-person caps

## [0.2.0] — 2026-07-13

### Added

**Automation Inbox**
- Workflows (n8n) can now post structured, reviewable results into LogCore — land leads, alerts, anything — reviewed from a new **Inbox** view on the Automations page with one-tap actions: Interested / Pass / Offer Made / Closed (every action records who took it)
- **Named inboxes**: create as many as you need ("Land Leads", "Price Alerts"), route each workflow's output to the right one, and pick per inbox **who gets notified** on new items and **who may act** on them (admins always can). Unrouted results land in an auto-created General inbox
- New items send ONE batched notification (bell + push) with a **View →** button that jumps straight to the right inbox — switching you to the business workspace if needed
- Duplicate protection: re-running a workflow never re-adds items it already submitted, and workflows can ask LogCore what it has already seen before spending AI credits qualifying old listings
- Works in both workspaces: business inboxes are shared with the team (and survive account changes); personal inboxes are yours

**Assets module**
- **Contribute access for employees/crew**: share an asset with a new middle access level where you pick exactly what the person can do — which fields they may change (e.g. just Status) and what they may add (comments, photos/PDFs, items inside). They work from the clean asset view (quick status dropdown, only their granted fields editable, comment box) and never see the full editor
- **Contributors on Team/Household assets**: give a member (or the whole team) the same picked-capability access on pool assets — without handing them full team management rights
- **Comments on assets**: an attributed, append-only note log per asset ("gate fixed, invoice sent") that can't overwrite anyone else's text. Everyone with edit access gets notified when someone comments — the bell notification has a **View →** button (and the push notification a link) that jumps straight to that asset
- Comments are an audit-style log: **only an admin can delete one**. Anyone can **collapse the comments section for themselves** (it reappears next time the asset is opened), and edit-level users can **turn comments off for everyone** on an asset from the edit page (data kept, posting blocked, switch back anytime)
- **🔔 per-asset notification mute**: a bell button in the asset view opens a popup to opt out (or back in) of comment notifications for that asset **and everything inside it** — personal preference, doesn't affect anyone else; muting a parent covers all its children, and the popup tells you when a mute comes from a parent
- **Hide from whole roles**: the Hide-from picker now accepts roles (e.g. `role:crew`) — hides the asset from everyone holding that role, including people assigned to it later
- Workflow (n8n) API can now post asset comments too (attributed "automation", triggers the same notifications); asset edits from workflows were already supported — both are documented in the API reference
- New default **📁 Folder** template out of the box — just a name and notes, for organizing assets into groups without building a template first
- Clicking an asset now opens a clean, read-first overview — fields laid out to read at a glance, attachments, the items inside it, and linked tasks — with an **Edit** button to switch into the editor (shown only if you can edit). Cancelling an edit returns you to the overview
- Anyone can now create their own templates (not just admins); share them with specific people or whole roles. Admins keep global templates and can restrict them to chosen roles
- Sharing is now a request: when you share an asset or template, each person gets an Accept/Decline notification and it only appears for them once they accept — and they can leave a share later
- Track anything ownable — land parcels, vehicles, equipment — as a nestable object tree (subdivision → parcels → …)
- Admin-curated Templates define each object type's premade fields (text/number/date/boolean/select, optional defaults); starts empty with a one-click editable example. Icons via a built-in emoji picker; select options via tag chips
- Search bar and filter (owned / shared / pool / by type), all shown as the real foldered tree; move an asset with a foldered tree-picker (also used when choosing a parent on create)
- Sharing defaults to "everything inside" with a "this one only" option; a new asset created inside a shared one automatically joins the same audience, so you can grow a shared group
- Share an asset (and everything inside it) to Team, Household, or a specific person as read-only or edit; hide specific objects from selected users — all via member pickers
- Admins can convert an asset tree into a shared Team/Household object that survives user account deletion
- Archive a single asset or its whole subtree (you're asked which); delete your own personal assets. Per-asset change history, photo/PDF attachments
- Link tasks to assets from either side (task form asset picker; "＋ Task for this asset" in the asset editor)
- AI chat can list, create, update, and archive assets (writes still require your approval), and admins can manage templates by chat
- n8n automation API: token-authenticated endpoints to list/create/update assets from workflows; token managed in Admin → n8n

**Approve-edits chat mode (new default)**
- The AI now pauses before any data change and shows an approval card; reads run freely
- Plan / Auto / Research modes unchanged and still selectable

### Changed

- Goal-type tasks now live on the Goals page only — removed from the Tasks page, the dashboard's Top 3 and Due Today, and the morning digest (they still show on the calendar when dated; goal-drift check-ins are unchanged)

### Fixed

- **Per-person asset permissions now beat group permissions.** When an asset was shared with the whole household/team AND a specific person had their own contribute grant, the grants were blended — so tightening one member's permissions appeared not to take effect. A by-name entry now fully overrides any group entry (shares and pool contributors alike), so restricting a single member of a group actually works
- **A per-person contributor entry now also restricts a user who holds the "Can manage" (pool) grant.** Previously the blanket household/team management grant gave full edit on every pool asset, silently ignoring contributor permissions — so restricting such a user was impossible. A by-name contributor entry now downgrades them to exactly the picked capabilities on that asset (admins are never restricted; whole-team entries never downgrade managers)
- Saving a just-created Team/Household asset no longer fails with "Pool assets are workspace-visible — use hidden_from instead of shares" — the editor now knows a fresh asset is a pool asset (the share selector is hidden, as it already was when reopening one)
- The login page banner now fades in smoothly instead of painting top-to-bottom, and is preloaded/cached so it appears instantly on return and sign-out
- Fixed a crash ("Something went wrong") that could appear on any page when the notifications list came back in an unexpected shape
- Sign-out now fully resets the theme — the login page always shows the brand orange (the sign-in button no longer takes on the last user's accent color), and your background no longer lingers until a reload
- No longer randomly logged out: a single transient/background 401 (or a blip during the 30-second session refresh) used to clear the session and bounce you to login — the app now re-verifies the session first
- The asset editor no longer crashes to a blank "Something went wrong" page on unusual history data; the error screen gained a Reload button
- Mobile: the asset and template editors no longer extend under the phone status bar (safe-area-aware modals)
- Saved chat archives no longer lose multi-line AI responses (parser kept only the first line; continuing a chat then overwrote the archive with the truncated copy)
- Long AI responses (over 5,000 chars) now auto-save correctly
- Proactive notifications injected into chat no longer break sending messages (422) or create junk chat archives
- AI agent now resolves household member names on task assignment (first-name matching; asks when ambiguous) instead of writing raw strings

## [0.1.0] — 2026-07-06

First tagged release.

### Added

**Branding on login page**
- Login page now shows the LogCoreTech banner as a full-bleed background
- LC logo icon replaces the plain text "LogCore" on Login and Setup pages
- Accent color and background are no longer applied on `/login` and `/setup` — brand orange is always shown on auth pages regardless of user theme settings

### Fixed

- Notifications dropdown now opens to the left on mobile (was opening off-screen to the right when the bell is in the top-right corner)
- Admin user delete now removes the user's Brain folder (`brain/USERS/{name}/`) in addition to the auth record — previously the Brain data was orphaned on disk
- Setup wizard name placeholder changed from a developer's name to "First and Last Name"
- Setup wizard no longer asks for role/occupation (timezone only in step 1)
- Setup wizard skips the life priorities step for business-only instances; business instances get distinct default priorities (Revenue, Team, Clients, Operations, Growth)
- Fixed crash on startup caused by wrong import in `update.py` (`get_current_user` lives in `routers/auth`, not `services/auth_service`)



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

**Goals standalone page**
- `/goals` route added and gated by the `tasks` module (goals are task-type tasks)
- 🎯 Goals nav entry added to `ALL_MODULES` — appears in sidebar and shortcuts picker
- Dashboard and Goals pages re-fetch data immediately on workspace switch

**Scheduler workspace notifications**
- Morning digest, overdue alerts, weekly review, and goal drift notifications now run per workspace — a business-workspace user receives notifications about their business tasks separately from personal tasks
- Business workspace notifications include a `[business]` label in the notification title

**Server-side shortcuts**
- Sidebar shortcuts are now persisted in `auth.json` as `{"personal": [...], "business": [...]}` rather than `localStorage`, so they sync across devices and are per-workspace
- `PATCH /auth/me` accepts a `shortcuts` dict; `GET /auth/me` returns it
- Switching workspaces immediately updates the sidebar shortcuts to the saved set for that workspace
- Fixed bug: `workspaces` field was not included in the user object mapped from `/auth/me`, so the workspace toggle pill never appeared for dual-access users — now fixed

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
