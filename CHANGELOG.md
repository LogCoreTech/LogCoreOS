# Changelog

All notable changes to LogCore OS are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Added

**Link your deals, assets, and money together**
- **Link assets to a deal** — every deal row in Contacts now has a 🔗 panel: attach the assets a job involves (the client's property, equipment used), see them at a glance, and get a running total of the linked assets' finance activity
- **Tag transactions with an asset** — the transaction form gets an optional "Linked asset" picker, and every asset's page now shows a **Finance activity** section with **income, expenses, and net** for that asset, across every book you can see
- **Create an invoice straight from a Won deal** — the 🧾 button now opens Finance with the invoice pre-filled (the deal's contact as the client, the deal value as a line item); you pick the book, review, and save — the invoice remembers which deal it bills
- **A deal can bill multiple invoices** — deposits, progress billing, final invoices all show under the deal, with a **Job P&L**: invoiced, collected, expenses from the linked assets, and net job profit
- **Change invoice status freely** — a status dropdown (draft/sent/paid/void) on the invoice and in the list replaces the one-way buttons; full payments still auto-mark paid
- **Finish payment transactions on the spot** — recording a payment that logs a ledger transaction now opens that transaction immediately so you can set category, asset, and notes without hunting for it
- **Everything links back** — invoices show the deal (and its assets) they came from; transactions show "from invoice / deal" chips; asset pages, deals, and invoices all click through to each other
- **Contacts on assets** — asset templates get a "contact" field type (pick a person/company from your CRM); the contact's page gains a **References** section showing every asset, invoice, and dollar tied to them, plus per-deal job profit

### Fixed

- **What's-New broadcast now fires after in-place updates** — `update.sh` stamps the installed version only after the restarted app passes its health check, so the boot-time announce saw the old version and stayed silent. The scheduler now re-checks 3 minutes after boot and during the daily update check
- **Release tags with a capital V are parsed correctly** (`V0.3.0` previously broke version comparison, hiding updates)
- **Updates card ↺ now really checks** — the refresh button hits a new cache-busting endpoint (`POST /update/check`) instead of re-reading the 4-hour cache, so a fresh release is visible immediately

## [0.3.1] — 2026-07-18

### Added

**Help section (with AI-readable guides)**
- New **Help** entry in the sidebar and mobile menu (below Settings) opening a full **Help & Guide** page: what every module does and how to use it, a searchable FAQ, and how to reach support
- Every module page gets an **ⓘ button** next to its title that jumps straight to that module's help section
- **The AI knows the help too** — ask "how do I use Finance?" in Chat and the assistant reads the same guide, answers, and links you to the right section; it also proactively points you to the right module for what you're trying to do
- **Search** the guide, filter to **only your modules**, or press **?** anywhere to open Help
- **Contact & support**: email support@logcoretech.com with pre-filled buttons for bug reports, feature requests, and feedback
- **First-run Getting Started checklist** on the Dashboard to help new users find their way (dismissible)
- **What's New broadcast**: after LogCore updates, every user gets a "what's new" note in their inbox and a dismissible banner for a few days, sourced from an authored release-highlights list

- **`launch.sh --tunnel-token <token>`** — pass your Cloudflare Tunnel token straight into the launch command, so a fresh VPS goes from empty to publicly reachable in two commands (`git clone` + `bash launch.sh --install-deps --tunnel-token <token>`). No UI access needed to bootstrap the tunnel; the Admin → Hosting panel still works for changing it later

### Changed

- **Setup wizard slimmed to a single page** — the Life Priorities step (and the summary page repeating it) is gone. New users just confirm profile type + timezone and launch; priorities start from the sensible default and are fine-tuned anytime on the Profile page (which the wizard now points out)

### Fixed

- **First-user setup now applies the Personal/Business choice instance-wide** — picking Personal (or Business) in the wizard disables the other workspace for the whole instance (`enabled_workspaces`), instead of leaving both visible in Admin. Admins can re-enable the other workspace anytime from Admin → Workspaces
- **Mobile: the app header no longer hides behind the phone notch/bezel** — the top bar now respects the device safe area (matching the bottom nav, which already did); the All Modules drawer also respects the bottom inset
- **launch.sh as root no longer crash-loops the app** — on a fresh VPS the repo is typically cloned by root, leaving `brain/` root-owned while the app container runs as uid 1000; startup died with `PermissionError` on `/data/brain`. `launch.sh` now fixes `brain/` ownership automatically when run as root (and prints the exact `chown` command when run as a non-root user with mismatched ownership)

## [0.3.0] — 2026-07-16

### Added

**Contacts (CRM) module**
- New **Contacts** module (personal & business) for people and organizations — clients, leads, vendors, friends. Rich records (type, multiple emails/phones, address, company link, tags, birthday, status, notes) plus **admin-defined custom fields**
- **Interactions timeline** (call/email/meeting/text/note) and a **deals pipeline** (customizable stages, kanban + list). Optional **follow-up dates** surface as reminders. Marking a deal *Won* links out to create an invoice in Finance
- **Contact-linked payees**: pick or quick-create a contact when logging a transaction; bank/CSV imports auto-suggest a matching contact. A contact's card shows what you've spent/received with them, scoped to the finance books you can actually see
- **Invoicing now uses contacts** — the old add-client form is replaced by a contact picker
- **Sharing** like the rest of the app: share a contact (read/contribute/edit) with a person, the household/team pool, or a role; contribute = log interactions & advance deals without editing the core record; hidden-from beats sharing; personal shares are accept/decline requests
- **AI + automations**: the AI can look up, create, and update contacts, log interactions, and add deals (writes behind the approval prompt, and it searches first to avoid duplicates); n8n workflows get a **write-focused** API (create/append/dedup-lookup, **no bulk export** — a leaked token can't dump your contact list)
- **CSV import/export** to onboard an existing contact list

**Goals**
- Completed goals **no longer disappear** — they stay in Done until you click **Clear completed** (which archives them). A **timeline filter** (Today / Week / Month / Quarter / Year) shows only goals due in that window, and the progress count follows it. Creating a goal now **requires a target date**, and the AI asks for one if you don't give it

**Automations (n8n)**
- The bundled n8n now **only runs when needed** — it starts on your first workflow, stops when idle, and stands aside entirely when you attach an external n8n instance (with an admin override to keep it on)

**Notes**
- **Share notes and folders** (read / edit-content / full) with people, the household/team pool, or a role — sharing a folder shares everything inside it. Household & team shared notes; accept/decline requests; leave anytime; read-only view for view-only shares
- **Drag a note into a folder** on desktop and mobile

**Finance**
- New books seed **workspace-aware** categories and tax buckets (personal vs business), plus more income options than just Salary. Recurring bills and one-off planned items can now carry a **deductible flag + tax bucket**
- **Archived books** are reachable again via a *Show archived* toggle (with Unarchive)
- Household/team books have a clear **＋ Account** affordance

**Setup & misc**
- The Setup **Life Priorities** step now has ↑/↓ reorder buttons (works on touch) and a **Skip** option — fixing a spot where a beta tester got stuck
- Default life priority renamed **God → Religion** (new setups only; existing users unchanged)
- Transaction payee field reads **"Paid to"** for expenses and **"Pay from"** for income
- AI chat: cleaner toolbar (icon memory buttons, fixed-width mode selector with a Plan icon) and a simpler greeting

**Finance module (Phase E — sharing & employee access)**
- **Share a book** with a person, the whole team/household, or a role — as read, edit, or **contribute**. Sharing is a request: each person gets an Accept/Decline notification and the book only appears for them once they accept (and they can Leave later)
- **Contribute access is the employee expense-submission mode**: you pick exactly what the person can do — add expenses and/or income, edit their own entries, see balances, see everyone's entries. Defaults are the tightest: submit expenses only, see only their own entries, **no balances**. All enforced server-side: capped viewers get balance-stripped responses and filtered transaction lists, not hidden UI
- **Per-account overrides**: share the whole book but restrict (or open up) a single account — an entry naming a person always beats a group entry, and an account row always beats the book row, so one member of an edit-shared group can be individually limited
- **Household/Team pool books** take **contributor grants** (no accept step — the pool is already visible to the workspace): let a member log entries in the family book without making them an admin
- **Hide from** specific people or whole roles (e.g. `role:crew`) — hiding beats sharing, and role hides cover future hires automatically
- AI chat gains `add_finance_transaction` and `categorize_transaction` (approval-gated, same caps enforced) — "log $40 gas in the family budget" now works end to end

**Finance module (Phase D — invoicing, clients & taxes)**
- **Invoices**: line items with quantities, optional tax %, due dates, auto-numbered (INV-2026-0001, prefix customizable per book). Lifecycle draft → sent → paid/void; **overdue is always computed** from the due date and open balance — nothing to forget to update
- **Partial payments**: record each payment as it arrives; the invoice flips to *paid* by itself at zero balance. A payment can log a **linked income transaction** straight into the ledger (client name as payee)
- **Clients & who's-behind**: a per-book client list with a rollup answering the owner question directly — invoiced / paid / outstanding / **overdue** per client, worst offender first, with the last payment date. Clients carry a reserved link for the future CRM module
- **Print / PDF invoices**: clean printable invoice view straight from the browser — no server dependencies
- **Tax season, handled**: flag transactions deductible and file them into your own tax buckets ("Schedule C: Supplies"); year-end summary per bucket plus a one-click **CSV export for the accountant**
- **Receipts on transactions**: attach photos/PDFs (10 MB, up to 10 per transaction) — stored with the book, deleted with the transaction
- **P&L / income statement**: income vs expenses with per-category breakdown for any year, quarter or month
- AI chat can draft invoices and record payments — every one behind the approval prompt

**Finance module (Phase C — budgets, bills, forecasting & fraud alerts)**
- **Budgets**: set a monthly limit per category; color bars show where you stand, and you get a bell/push warning at 80% (configurable per book) and again when you go over — each fires once, no nagging
- **Recurring bills & income**: track rent, subscriptions, paychecks with their cadence (weekly/monthly/yearly). Incoming transactions — typed, bank-synced or CSV — **auto-match** to the bill (small amount/date wiggle tolerated), mark it paid and roll the due date forward; a bill 3+ days late with no matching charge notifies you
- **Planned one-offs**: expected items like a tax refund or a car repair, with a check-off when they happen
- **Projected balance** — the "what should I have on day X" number: pick an account and a date, and LogCore adds every scheduled bill, paycheck and planned item to today's balance, with the itemized list of *why*
- **Balance deviation alerts**: set a threshold per account and LogCore compares the bank's reported balance against what your ledger says it should be — after every sync and nightly. A drift beyond the threshold pings you immediately: unrecorded spending or **someone in your account**. (Cash accounts work too — punch in the actual balance via the account API)
- AI chat can now answer "am I over budget?" and "what will checking look like on the 1st?" (new read-only budget + projection tools)

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
