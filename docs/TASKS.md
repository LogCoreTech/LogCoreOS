# TASKS.md — LogCoreOS Active Work Queue

Keep this up to date. Mark tasks done as they're completed. Add new tasks as they surface. This is the single source of truth for what's being worked on.

---

## Active Tasks

*Revenue target: first client within one month. Critical path goes through the land investor — he's a warm lead already waiting.*

- [ ] **Get Anthropic API key** — takes 5 minutes at console.anthropic.com; use Haiku model for demo cost control; without this the demo has no AI and the client pitch has no demo; do this first
- [ ] **Define pricing tiers with specific numbers** — need dollar amounts before closing the land investor or anyone else; decide: bare bones hosting (setup fee + monthly) vs. managed + custom APIs (higher both); can't say yes to a client without a price
- [ ] **Automation Inbox / results dashboard** — workflows write structured output to Brain JSON; users see results with per-item actions (Interested / Pass / Offer Made / Closed); workflow skips already-reviewed items; land investor needs this to see the value loop
- [ ] **Land lead search & qualify workflow** — n8n workflow pulling land listings (LandWatch, Land.com, county records) and AI-qualifying by investor's criteria (price, acreage, location, zoning); stub file in `automations_stubs/`; Brain JSON output schema; depends on Automation Inbox being live
- [ ] **Close land investor as first client** — once Automation Inbox + workflow are live, demo it to him directly and close; he already asked for this

---

## Backlog

### Launch Prep — do in order before going public

- [ ] **Commit pending change + push** — 1 uncommitted change has been sitting since the session 5 work; verify, commit, push to GitHub before deploying anywhere
- [ ] **Verify GitHub repo is public + README is solid** — Reddit and Discord will link straight to the repo; README needs to be good enough for a first impression
- [ ] **Provision Hetzner CX22 for demo instance** — separate VPS from personal; ~€4.50/mo
- [ ] **Create new Cloudflare Tunnel token for demo VPS** — current token is set to dev instance and stays there; new token gets set to `demo.logcoretech.com`; do before provisioning the VPS
- [ ] **Wire demo.logcoretech.com in Cloudflare** — subdomain → Cloudflare Tunnel token for the demo VPS
- [ ] **Deploy LogCore on demo VPS** — full stack (app + ntfy + n8n + tunnel), open registration on, `demo.logcoretech.com`
- [ ] **Privacy policy page on logcoretech.com** — required before demo goes public; users put personal data in the app, GDPR/CCPA compliance is not optional
- [ ] **Terms of service page on logcoretech.com** — needed for demo and managed hosting before anyone signs up
- [ ] **OG/social preview image for logcoretech.com** — when the link is shared on Reddit/Discord, a good preview card dramatically increases clicks; add `<meta og:image>` to index.html with a branded screenshot or graphic
- [ ] **Screenshots in README** — at least 2–3 static images of the actual app UI; people decide whether to try it based on screenshots alone
- [ ] **CONTRIBUTING.md** — expected by open source community before a Reddit post; basic "how to run locally and submit a PR" guide
- [ ] **GitHub issue templates** — bug report + feature request templates; structures incoming issues so they're useful instead of vague
- [ ] **GitHub Release tag** — tag the current version (v0.1 or v1.0); users and GitHub stars page both expect this; pairs with existing CHANGELOG.md
- [ ] **2FA on all critical accounts** — Cloudflare, Hetzner, GitHub, Stripe, domain registrar; one compromised account takes everything down
- [ ] **Cloudflare Analytics enabled** — already in Cloudflare dashboard, one toggle; free website traffic visibility with no tracking script on the site
- [ ] **Update website copy for business-first positioning** — current site likely leads with personal/family angle; target customer is businesses; update hero copy, features section, and pitch to lead with team, automations, and managed workflows
- [ ] **Add "Try the Demo" CTA to logcoretech.com** — button pointing at `demo.logcoretech.com`; users need a clear path from website to demo

### Business — Legal

- [ ] **File LLC** — Arkansas; file online at sos.arkansas.gov; $45 standard (~4–6 weeks) or $300 expedited (~3–5 days); pay expedited if you need the bank account open within the month
- [ ] **Get EIN from IRS** — free, ~5 minutes at irs.gov; required to open a business bank account
- [ ] **Open business bank account** — keep business money separate from personal from day one; do after LLC + EIN
- [ ] **Set up accounting** — Wave (free) is sufficient to start; track income and expenses from day one, not retroactively
- [ ] **Business credit card** — separate card for business expenses; do after bank account is open
- [ ] **Password manager for business credentials** — Bitwarden free tier; VPS, Cloudflare, GitHub, Stripe, domain registrar passwords all in one secure place; don't manage these in your head

### Business — Go-to-Market

- [ ] **Define managed hosting pricing** — decide the model (monthly flat fee per instance? per user?) before saying yes to any client; need a number to close deals
- [ ] **Set up Stripe** — payment processing ready before the first client; don't invoice manually
- [ ] **Set up branded email** — `hello@logcoretech.com` or `support@logcoretech.com` via Cloudflare Email Routing (free); `logcoretech@gmail.com` looks unprofessional to business clients
- [ ] **Managed hosting waitlist form** — before Stripe is ready, capture emails of interested people via Formspree (already used on contact form); don't lose leads because payment isn't wired up yet
- [ ] **Client onboarding process doc** — when someone says yes to managed hosting, what are the exact steps? Write it before you need it under pressure; VPS provisioning, DNS, tunnel token, first login handoff
- [ ] **LinkedIn company page** — B2B clients will search for it; basic page with logo, description, link to logcoretech.com

### Demo Instance — features to build

- [ ] **Daily demo reset script** — cron job that wipes all non-admin user Brain folders + auth entries nightly, resets to clean template state; keeps the demo box from filling with stale data
- [ ] **Demo banner in UI** — in-app notice explaining this is a demo and data resets daily; prevents confused support requests
- [ ] **AI cost protection for demo** — switch demo instance to `claude-haiku-4-5-20251001` (much cheaper) OR add a per-user daily message cap in the chat router; demo users will burn the Anthropic budget without this
- [ ] **UptimeRobot monitoring on demo URL** — free tier monitors uptime every 5 min and sends email/SMS alert when it goes down; know before users do; set up immediately after demo deploys

### Community

- [ ] **Reddit post** — post to r/selfhosted, r/productivity, r/homelab once demo is live
- [ ] **Discord server** — create and link from website + GitHub README
- [ ] **GitHub Discussions** — one toggle in repo settings; gives community a place to ask questions
- [ ] **Facebook page post** — announce to existing followers once demo is live
- [ ] **Demo video or GIF** — screen recording of the app in action; single biggest missing piece for Reddit posts and README; people decide whether to click through based on this alone

### Workflows — managed automation business

*(Automation Inbox and land lead workflow moved to Active Tasks — time-sensitive, first client depends on them)*

### Product Backlog

- [x] **Self-hoster update flow** — `docker/update.sh` handles in-place updates with auto-rollback; Admin → Updates card shows current vs latest version; `launch.sh --auto-update` installs cron for hands-free updates; daily scheduler job refreshes version cache (2026-07-05)
- [ ] **User-customizable Dashboard per workspace** — each user can choose which widgets appear on their personal and business dashboards and in what order; widget config stored per-workspace in `brain/USERS/{name}/Dashboard/personal.json` and `business.json`; available widgets: Top 3 Tasks, Streaks, Due Today, Smart Home (personal), Team Tasks (business) — more as modules are added
- [ ] **Projects module** — project tracking with tasks, milestones, and status (deferred to Phase 3+)
- [ ] **Multi-day calendar events** — calendar events currently support a single `date` field; true multi-day events (vacations, trips, blocks) need `start_date` / `end_date`, a backend schema update, and a calendar renderer that spans cells
- [x] **Household task assignment for non-admins** — resolved 2026-07-02: `GET /shared/members` + `GET /team/members` expose the member list to admins and users with the `pool_edit` grant, feeding the assign dropdown for granted non-admins
- [ ] **Personal calendar task completion toggle** — tasks shown in CalendarGrid day detail panel have no done/undo button; must navigate to Tasks page to un-mark done
- [ ] **Projects / chat system evolution** — evolve chat into a ChatGPT/Claude-style Projects feature: named projects with custom context, per-project chat archives, optional agent usage within each project

---

## Done

- [x] **Pool permissions + workspace visibility + calendar/admin fixes** — (1) Admin page mobile overflow fixed (`w-full` root, `flex-wrap`+`min-w-0`/`truncate` on UsersCard/RolesCard rows); (2) household/team tasks on the personal calendar now carry the 🏠/🧑‍🤝‍🧑 badge and hide/show with the pool toggle pill (matching events); (3) assigned pool tasks open TaskModal read-only (no Save/Delete, Cancel→"Close") — was 404'ing on save; (4) instance-wide **Workspaces** admin card hides a whole workspace for everyone incl. admins via `enabled_workspaces`; (5) per-user **pool_edit** grant (`household`/`team`) gives full pool-manager parity (add/edit/delete events + tasks + assign), default off, admins always; new `/shared/members` + `/team/members` feed the assign dropdown (2026-07-02)
- [x] **UI bug fixes — sign-out, Brain back button, pool priorities keyboard, horizontal scroll** — sign-out moved to sidebar (desktop) and mobile drawer footer; Brain file list view now has ← Settings back button; PriorityList extracted to module level (was defined inside PoolPrioritiesCard causing keyboard dismissal on every keystroke); overflow-y-scroll on Layout main fixes scrollbar-induced layout shift; Admin feature-role row gets flex-wrap; Calendar wrapper gets w-full; POOL_DEFAULT_TEAM updated with business-relevant defaults (2026-07-01)
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
