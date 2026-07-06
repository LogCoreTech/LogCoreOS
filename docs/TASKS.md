# TASKS.md — LogCoreOS Active Work Queue

Keep this up to date. Mark tasks done as they're completed. Add new tasks as they surface. This is the single source of truth for what's being worked on.

**Structure:** phases ordered by dependency (not time), from `docs/BLUEPRINT.md` — the strategy, revenue math, and reasoning live there. Work top-down; a phase's tasks unblock the next phase.

---

## Phase 0a — Unblock now (mortgage-safe: no credit pulls, no new financial accounts)

- [ ] **Get Anthropic API key** — console.anthropic.com, 5 min; Haiku for demo cost control; nothing AI works without it; do this first
- [ ] **Commit pending change + push** — 1 uncommitted change sitting since the session-5 work on the dev machine; verify, commit, push
- [ ] **Write the pricing sheet with real numbers** — starting tiers (market-validated, see BLUEPRINT.md): Hosted $200–500 setup + $50–100/mo · Automation $1,000–1,500 setup + $1,000–1,500/mo · Ops Partner $2,500 setup + $2,500–3,500/mo
- [ ] **Branded email** — `hello@logcoretech.com` via Cloudflare Email Routing (free)
- [ ] **Bitwarden vault** — all business credentials (VPS, Cloudflare, GitHub, registrar) in one place
- [ ] **2FA on all critical accounts** — Cloudflare, GitHub, Hetzner, registrar (Stripe when it exists)
- [ ] **Ask the loan officer** — "Does filing an LLC or receiving small side-business income before closing affect my underwriting?" — answer gates Phase 0b timing
- [ ] **Name check** — 15 min: USPTO trademark search + Google "LogCore" for conflicts

## Phase 0b — After the house closes (or lender clears it)

- [ ] **File Arkansas LLC** — standard $45 at sos.arkansas.gov (expedited $300 only if a full-price client's payment is waiting on it)
- [ ] **Get EIN** — irs.gov, free, ~5 min; required for business bank account
- [ ] **Open business bank account** — after LLC + EIN; business money separate from day one
- [ ] **Set up Stripe** — invoicing + payment links
- [ ] **Set up Wave accounting** — connected to the business bank account; set aside 25–30% of income for quarterly estimated taxes
- [ ] **Business credit card** — only after closing, never during underwriting (hard credit pull)

*Interim invoicing before 0b is done: sole proprietor via Wave (free), paid into a separate personal savings account — small, documented amounts.*

## Phase 1 — Pilot client (land investor as design partner)

- [ ] **Write the pilot agreement (one page)** — discounted rate (e.g., token setup + $250–500/mo, or 60 days free then Automation tier) in exchange for: written testimonial, publishable case study with real numbers, 2 warm referral intros, 15-min weekly feedback call; converts to full Automation tier at a named end date
- [ ] **Automation Inbox** — workflows write structured output to Brain JSON; users see results with per-item actions (Interested / Pass / Offer Made / Closed); workflow skips already-reviewed items
- [ ] **Land lead search & qualify workflow** — n8n pulling land listings (LandWatch, Land.com, county records — build a fallback source from day one) and AI-qualifying by investor's criteria; stub file in `automations_stubs/`; Brain JSON output schema; depends on Automation Inbox
- [ ] **Client onboarding runbook** — exact steps: VPS provision → tunnel → Infisical → first login handoff; includes off-site backups; write before deploying, not during
- [ ] **Demo + sign the pilot** — demo with his actual criteria loaded, get the agreement signed
- [ ] **Deploy his full instance** — follow the runbook (this validates it)
- [ ] **Weekly feedback loop** — log every piece of his feedback here as tasks; his polish list is the vertical's roadmap
- [ ] **Case study + referrals** — after 2–4 weeks of results: publish case study, collect the 2 referral intros
- [ ] **Convert pilot to paid** — at the named end date: full Automation tier or amicable exit with case study in hand

## Phase 2 — Public launch surface (do in order)

- [ ] **Privacy policy page on logcoretech.com** — blocker before demo goes public (GDPR/CCPA)
- [ ] **Terms of service page on logcoretech.com** — needed for demo and managed hosting
- [ ] **New Cloudflare Tunnel token for demo VPS** — set to `demo.logcoretech.com`; do before provisioning
- [ ] **Provision Hetzner CX22 for demo instance** — ~€4.50/mo, separate from personal
- [ ] **Deploy LogCore on demo VPS** — full stack (app + ntfy + n8n + tunnel), open registration on
- [ ] **AI cost protection for demo** — Haiku model AND a per-user daily message cap in the chat router; the cap is non-negotiable before any Reddit post
- [ ] **Daily demo reset script** — cron wipe of non-admin Brain folders + auth entries nightly
- [ ] **Demo banner in UI** — "this is a demo, data resets nightly"
- [ ] **UptimeRobot monitoring on demo URL** — free tier, set up immediately after deploy
- [ ] **Off-site backups for demo VPS** — Hetzner snapshots or object storage; on-box backup.sh alone is not a backup; same pattern goes into the client runbook
- [ ] **Screenshots in README** — 3+ images + a 30-second GIF of the AI using its memory
- [ ] **CONTRIBUTING.md** — how to run locally and submit a PR
- [ ] **GitHub issue templates** — bug report + feature request
- [ ] **GitHub Discussions** — one toggle in repo settings
- [ ] **GitHub Release tag v0.1.0** — also activates the built-in updater (GITHUB_REPO already wired)
- [ ] **Website: business-first copy + Try the Demo CTA** — hero leads with team/automations/managed workflows; CTA → demo.logcoretech.com
- [ ] **OG/social preview image for logcoretech.com** — `<meta og:image>` with branded screenshot
- [ ] **Managed hosting waitlist form** — Formspree, capture leads before Stripe checkout exists
- [ ] **Cloudflare Analytics enabled** — one toggle, free
- [ ] **LinkedIn company page** — logo, description, link

## Phase 3 — Client acquisition (clients #2–6 → $10k/mo)

- [ ] **Vertical offer #1: RE / property management** — "deal flow on autopilot"; land-lead workflow re-skinned for wholesalers, agents, property managers
- [ ] **Vertical offer #2: contractors & trades** — lead intake + quote follow-up + scheduling reminders, sold through the electrician network
- [ ] **Service agreement template** — liability cap, data-handling terms, "async support, 24–48h response"; required before client #2 signs
- [ ] **One-page offer PDF per vertical + 15-min demo call script**
- [ ] **List 50 prospects** — RE investors/property managers (Facebook groups, BiggerPockets, pilot's referrals) + contractors/GCs known by name
- [ ] **Outreach cadence** — 10 personal messages/week minimum (~2 hrs); track in LogCore's own Business workspace
- [ ] **Publish pilot case study** — website + Facebook page, cross-post to LinkedIn
- [ ] **Collect the 2 referral intros** — prospects #1 and #2
- [ ] **Close clients #2–#3 at full price** — never repeat the pilot discount; raise prices if closing >50%
- [ ] **Close clients #4–#6** — $10k/mo checkpoint: ~6 full-price clients averaging $1,700/mo
- [ ] **Weekly revenue tracker** — MRR, pipeline count, churn; review every week

## Phase 4 — Community & following (starts once Phase 2 ships; write once, cross-post everywhere)

- [ ] **Demo video/GIF** — 2–3 min unedited screen recording; biggest conversion asset
- [ ] **Facebook page announcement** — existing followers first
- [ ] **n8n cross-posting workflow** — one post → auto-publish Facebook + LinkedIn (doubles as a sellable case study)
- [ ] **Build-in-public cadence** — 1 post/week on Facebook, cross-posted; revenue milestones, feature ships, lessons
- [ ] **Discord server** — linked from README + website
- [ ] **Reddit launch** — r/selfhosted first (data ownership + AI memory + local-first, NOT the business pitch), then r/n8n, r/productivity, r/homelab; one evening each, spaced out
- [ ] **Show HN post** — after Reddit feedback is folded in
- [ ] **Community responsiveness** — reply to issues/Discussions/Discord within 24 hrs for the first 90 days (one daily 30-min slot)
- [ ] *Deferred until time bought back:* YouTube videos on the existing channel

## Phase 5 — Product features that unblock scale (build when a phase above demands it)

- [ ] **Ollama / local LLM support** — pulled forward from roadmap Phase 6; #1 r/selfhosted credibility feature; ship before/with the Reddit launch
- [ ] **Automation Inbox generalization** — from land-leads-specific to any workflow writing reviewable results
- [ ] **Instance provisioning script** — one command: VPS → tunnel → Infisical → configured instance; prerequisite for >5 clients
- [ ] **Importers: Todoist / Notion / Obsidian → Brain** — "import my digital life"
- [ ] **Stripe billing portal** — self-serve paid signup for hosted plans
- [ ] **Monthly value report per client** — auto-generated from Automation Inbox data (leads found, actions taken, hours saved); anti-churn tool + sales asset
- [ ] **Email digests** — ntfy is a barrier for normal business users; notifications block already designed in PROJECT.md

## Phase 6 — Second revenue stream (needs Phase 4 traction + provisioning + billing)

- [ ] **Launch hosted plans to the waitlist** — $15–30/mo personal, $50+/mo business
- [ ] **Hosted tier on website** — self-serve Stripe checkout
- [ ] **Demo → hosted conversion** — post-signup email/banner → hosted plan or self-host guide
- [ ] **At 5+ retainer clients: contract out routine maintenance** — owner time goes to sales + product
- [ ] **Revisit revenue mix** — hosting MRR > $1k/mo → invest in funnel; otherwise double down on retainers

---

## Product Backlog (pull in when a sales call or phase demands it)

- [ ] **User-customizable Dashboard per workspace** — widget config per-workspace in `brain/USERS/{name}/Dashboard/personal.json` and `business.json`; widgets: Top 3 Tasks, Streaks, Due Today, Smart Home (personal), Team Tasks (business)
- [ ] **Projects module** — project tracking with tasks, milestones, and status
- [ ] **Multi-day calendar events** — `start_date` / `end_date` schema + calendar renderer that spans cells
- [ ] **Personal calendar task completion toggle** — tasks in CalendarGrid day detail panel need a done/undo button
- [ ] **Projects / chat system evolution** — ChatGPT/Claude-style Projects: named projects with custom context, per-project chat archives, optional agent usage

---

## Done

- [x] **Business blueprint written** — `docs/BLUEPRINT.md`: $10k/mo in 6 months plan; retainers primary / hosting secondary; TASKS.md restructured around its phases (2026-07-06)
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
