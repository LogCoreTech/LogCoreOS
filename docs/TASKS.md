# TASKS.md — LogCoreOS Active Work Queue

Keep this up to date. When a task is completed, **remove it** rather than checking it off — the outcome belongs in `CHANGELOG.md` (user-facing changes) and the day's Daily Note (implementation detail), not here. Add new tasks as they surface. This is the single source of truth for active product work.

**Structure:** active build work → security → launch surface → features that unblock scale → AI agent findings → product backlog → idea backlog. Work top-down.

---

## Now — active build work

- [ ] **Land lead search & qualify workflow** — n8n pulling land listings (multiple sources with a fallback from day one) and AI-qualifying against configurable criteria; stub file in `automations_stubs/`; posts to the Automation Inbox (`POST /automations/inbox/items`, `GET /inbox/seen` to skip known listings)
All 14 `module_packages/` modules (the 13-module Mod Store rollout plus Goals) and the app-wide search bar + universal tags feature are confirmed working end-to-end on the owner's real instance — live-instance verification closed 2026-09-06. Full build history and design decisions: `docs/PROJECT.md`'s "Complete — Mod Store" section and `docs/MEMORY.md`'s 2026-08-24 through 2026-08-30 entries.

---

## UX Polish Batch — fully shipped 2026-09-05

Full triage of the former "Cross-App UX & Polish" Idea Backlog list (34 items), dispositioned item-by-item with the owner via a structured interview (2026-09-04), then scoped into 4 dependency-ordered tiers via a second interview round in plan mode. All 4 tiers now shipped and tested (backend suite 1443 passed; frontend `eslint --max-warnings 0` + `vite build` both clean across the whole `src` tree) — see `docs/Daily Notes/2026-09-04.md` and `2026-09-05.md` for the full build writeup, `docs/MEMORY.md` for the architecture decisions, and `CHANGELOG.md` for the user-facing description of every item. Not live-verified in a browser (no automation available in this environment) — flagged plainly per this project's own standard.

**Group Home Assistant entities by room/area** — removed from this batch (real scope: `ha_service.get_areas()` returns only a flat area-name list and is called from nowhere in the frontend; no entity-to-area mapping exists). Re-scope alongside other Home Assistant module backlog work.

**Shipped, Tier 1+2+3 (2026-09-04):**
- ConfirmDialog (all 34 `confirm()` sites migrated), Toast/snackbar infrastructure, Escape-to-close (retrofitted into ~40 existing modals)
- Progressive module/nav disclosure — fresh instances now auto-install Journal/Calendar/Notes/Goals alongside the always-on Tasks/Chat/Dashboards
- Welcome-back popup with optional AI summary
- "This week at a glance" as a 5th `suggestions_service.py` builtin (daily/weekly cadence)
- App-wide search fast-follow — cross-workspace search (permission-checked via the destination page's own existing access check, auto-switches workspace, shows a toast) + per-provider "show more". Real relevance ranking stays explicitly out of scope (the future RAG project's own job)
- Onboarding seed data — one "Example: ..." item per module (Tasks, Notes, Journal, Calendar, Goals, Assets, Contacts, Finance) at account creation
- "Today at a glance" dashboard block (`today_glance`, opt-in via Add Block, `module="dashboard"`-gated)
- Show/hide password toggle + real `autoComplete` hints on Login/Register
- Persist list-view filter/sort choices — server-side per-account (`tasks_filter`/`tasks_sort_mode` on `auth.json`), replacing Tasks' old localStorage-only sort and the filter's previous no-persistence default. The only concrete "resets on navigation" case found anywhere in the app — no other module had an unpersisted filter/sort worth migrating
- Plain "Duplicate" action on Tasks (`TaskView.jsx`), Events (`EventModal.jsx`), and Transactions (`TransactionModal.jsx`) — frontend-only, reuses each module's existing create endpoint; copies everything except completion/streak state, and stays in whatever scope (pool vs. personal) the original was in
- Purpose-built empty states with a CTA — new `components/EmptyState.jsx`, wired into Tasks/Notes/Contacts; Assets was left alone since it already had a better purpose-built empty state (two CTAs) than the generic component would provide
- Role-aware empty-state/Getting Started messaging — real bug found and fixed: `GettingStarted.jsx`'s 4-step checklist was NOT actually role-aware before this, linking every user to `/tasks`/`/chat` regardless of whether those modules were disabled for their feature role (a dead link for a restricted user). Now filters by `user.disabledModules`. Dashboard also gained a real empty-blocks message distinguishing "you have limited module access" from a plain new-dashboard empty state
- Context-aware destructive-action warnings — curated to the owner's own named example (Tasks' streak: "You'll lose its N-day streak"), both `TaskView.jsx` and `TaskModal.jsx`'s own delete confirms. Assets and Goals were checked and already have better linked-record context than a generic message would add (Goals' own delete flow already has real subgoal/linked-task cascade checkboxes) — left untouched
- "Save & add another" — scoped to Transactions (`TransactionModal.jsx`), the explicit named use case; retains account/category/date, clears amount/payee/notes/tags. Not extended to other create modals this pass
- Visible offline-state banner — `components/OfflineBanner.jsx`, wired into `Layout.jsx` alongside `DemoBanner`/`WhatsNewBanner`/`WelcomeBackPopup`. Combines `navigator.onLine`/`online`/`offline` events with a 15s-interval `GET /api/v1/health` reachability check, since `navigator.onLine` alone stays `true` even when DNS or a proxy is actually broken
- Custom PWA icon per accent color — new `services/icon_service.py` (Pillow, new backend dependency) rotates only the hue of the shipped icon's brand-orange pixels toward the user's `accent_color`, leaving the white glyph/dark badge untouched; `routers/pwa.py` serves a per-user `GET /api/v1/pwa/manifest.webmanifest` (cookie-authenticated, bakes the accent into its icon URLs) and a public `GET /api/v1/pwa/icon-{size}.png?accent=` (no auth needed — just a public brand asset recolored by a validated hex string); `lib/theme.js`'s `applyAccentColor()` swaps the `<link rel="manifest">`/`<link rel="apple-touch-icon">` hrefs to the dynamic endpoints on login and back to the static defaults on logout (iOS reads `apple-touch-icon` directly, not the manifest's `icons` array, so both links need swapping). Only affects fresh installs going forward — an already-installed PWA icon won't retroactively update
- Command palette / quick-add — `pages/settings/Shortcuts.jsx` gained a "Command Palette" section (on/off toggle + a checklist of which quick-create actions to show, both server-persisted via `command_palette_enabled`/`command_palette_actions`, never a static list — filtered live to the user's actually-enabled modules). `GlobalSearch.jsx`'s empty state (nothing typed yet) now shows those quick-create buttons instead of a second overlay; clicking one navigates to `<module>?create=1`, a new lightweight convention (`lib/deepLinks.js`'s `quickCreateUrl()`) each target page reads once on mount to open its own existing blank-create modal, mirroring that same page's existing `?task=`/`?event=`/etc. id-deep-link effect. Scoped to the 6 modules with one obvious single "new record" gesture already built — Tasks/Notes/Calendar/Assets/Contacts/Finance (the same 6-of-8 set #11's seed data uses, minus Journal — no discrete create-modal, an entry is just today's date — and Goals — no query-param deep-link plumbing exists there yet). Cmd/Ctrl+K itself stays ungated by `command_palette_enabled` — only the quick-create row is gated, since plain search shouldn't be something toggled off
- Warn before discarding unsaved form changes — `useEscapeToClose`'s reserved `{hasUnsavedChanges, onUnsavedAttempt}` shape now has its first real callers: Task/Event/Asset/Contact/Transaction/Goal's own create-edit forms. Each captures a snapshot of its own editable-fields state once at mount (or, for Goal, re-baselined inside its own async `load()` — its form data arrives after the fetch resolves, not synchronously from props, so a plain mount-time snapshot would have made every existing goal read as "changed" the instant Edit was pressed) and compares live; Escape/the X button/Cancel (and, for Goal, its backdrop-click-to-close) all route through the same guard, reusing each file's own existing `confirmState`/`ConfirmDialog` slot rather than a second dialog mechanism. Scoped to these 6 highest-value forms (real free-text fields a user would be upset to lose) — BookSettings/RecurringPanel/TransferEditModal/InvoicesPanel/Automations/admin config forms are a deliberate fast-follow, not done this pass
- Accessibility — ~59 icon-only buttons across 34 files gained a real `aria-label` (previously a screen reader announced bare "button" with no indication of what it does); `lib/toast.jsx`'s dismiss button grew from a 24×24px hit area to the 44×44px WCAG touch-target floor the plan's own mobile section names explicitly, via negative margins so the visible ✕ glyph stayed the same size. What's left of this item: the broader "audit of pre-existing pages" (keyboard/focus, not just labels/touch-targets) is still open, tracked below
- Diff-based list refresh (pull-to-refresh's other half) — real root cause found, not a generic "build a diffing utility": every affected page already keys its rows by a stable id, so React's own reconciliation already diffs correctly — the actual bug was each page's own `{loading ? <spinner> : <list>}` gate re-firing on every refetch (including ones triggered by an unrelated action elsewhere on the page, e.g. toggling one task complete), blanking the entire already-rendered list back to a skeleton loader. Fixed across 10 pages (Goals/Dashboard/Finance/Notes/Tasks/Contacts/Brain plus 5 admin list pages — Users/Household/Team/RoleDefinitions/ModStore) by narrowing each gate to `loading && <that page's own already-established empty-check>`, mirroring a fix `Finance.jsx` itself had already shipped once before for its own transactions list. Journal/Assets/Calendar audited and found NOT to have this bug (Journal's loading gate is legitimate per-day record navigation, not a redundant refresh; Assets/Calendar don't gate rendering on loading at all)
- Pull-to-refresh (the mobile gesture) — new `lib/usePullToRefresh.js` (hand-rolled touch-event tracking, no new dependency) + `components/PullToRefreshIndicator.jsx`, wired into Tasks/Contacts/Goals/Finance/Dashboard/Brain. Touch-only listeners are what naturally keep it mobile-only (desktop mouse drags never fire touchstart/touchmove). Dashboard disables it while `editing` (its own block drag/resize would otherwise compete for the same touch); deliberately NOT wired into Notes.jsx — its file-tree pane already has its own pointer-based drag-to-reorder, and a drag starting at the very top of the tree would be ambiguous with a pull-to-refresh attempt; needs its own conflict-resolution design, not a bolted-on fix. **Not live-verified** — no browser/touch-device testing tool is available in this environment; verify by hand on a real phone before trusting it (pull down from the top of Tasks/Contacts/Goals/Finance/Dashboard/Brain — should show a small spinner that fills in as you pull, refresh on release past the threshold, and snap back if released early)
- Accessibility — real keyboard-nav gaps found and fixed, 2026-09-05: (1) **no modal anywhere in the app trapped Tab focus** — a keyboard user could Tab straight past a modal's last element into the page behind it. New `lib/useFocusTrap.js` (same "hook every modal wires in individually" shape as `useEscapeToClose`), retrofitted into all ~42 modal instances across 32 files (led by a hand-built reference in `ConfirmDialog.jsx`, then two parallel background agents covering the rest, each diff read and verified before trusting it). Several files needed real judgment beyond the mechanical copy-paste: a modal whose content changes within one persistent component instance (Notes' 6 mutually-exclusive form blocks sharing one card ref, TaskModal's view/edit mode switch, GoalModal's delete popup, WelcomeBackPopup's self-toggled visibility) needed the hook's `active` param tied to that same condition, so the trap's effect re-attaches to the freshly-mounted card each time instead of staying bound to whatever was there at first mount. (2) **No skip-to-content link existed** — a keyboard user had to Tab through the entire sidebar/mobile nav on every single page before reaching real content; added to `Layout.jsx` (visually hidden until focused, jumps to a new `id="main-content"`/`tabIndex={-1}` on `<main>`). (3) `TagInput.jsx`'s own text input had `outline-none` with nothing replacing it on the wrapper — a focused tag field gave a keyboard user zero visual indication of where focus was; added `focus-within:ring-2 focus-within:ring-orange-500` to the wrapper, matching the app's own standard `.input` focus-ring convention exactly.
- Broader Toast adoption — replaced all 10 remaining raw browser `alert()` popups app-wide (Chat's load/delete-chat failures, Automations' workflow delete/toggle-active failures, Contacts' CSV import success+failure and bulk-convert success, Account's timezone/export failures, Appearance's save failure) with `toast.error()`/`toast.success()`. Every case audited individually rather than blindly swapped — a couple already had their own inline "Saved ✓"-style success indicator (Account, Appearance), so only their error path (still raw `alert()`) needed the toast; the rest had no success feedback at all beyond the blocking popup. Deliberately did NOT chase down every silently-swallowed `catch {}` in the app looking for more gaps — most of those are already deliberate, reviewed non-fatal cases (e.g. "surfaced by reload"), and a low-confidence blanket audit of all of them risked false positives more than it found real gaps.
- **Owner-reported bug fixed, 2026-09-05: ConfirmDialog ("are you sure" popups) weren't fixed on screen and background content kept scrolling.** Root cause: the SAME pre-existing "nested-modal clipping" bug class already documented for `assetDisplay.jsx`'s `ImageLightbox`/`GoalModal.jsx` (`.modal-card`'s `backdrop-blur-sm` creates a new containing block for `position: fixed` descendants) — but this time affecting `ConfirmDialog` itself, made far more visible by #9's own work earlier this batch, which massively increased how often `ConfirmDialog` opens NESTED inside an already-open edit modal (every "Discard changes?" prompt). Fixed at the root, once: `ConfirmDialog.jsx` now always renders via `createPortal(..., document.body)` (escapes every ancestor's CSS, fixing all ~40 call sites permanently, not just the reported one) plus a new `lib/useScrollLock.js` (module-level reference-counted, so stacked modals don't fight over restoring scroll) that locks `<main>` while open. Auditing "check all items" turned up the same bug in AssetModal.jsx's own main editor (a stale `useFocusTrap` — no `active` param tied to its view/edit mode toggle, so the trap attached once at mount and never again) and its `archivePrompt`/`SaveAsTemplateModal` popups (the exact 2 instances flagged unfixed back on 2026-08-29, now closed), plus `AssetView.jsx`'s mute-notifications popup and `RecurringPanel.jsx`'s two form popups (same stale-focus-trap bug). All given the same portal + scroll-lock + corrected `active` treatment. Two unrelated, lower-priority findings surfaced during the sweep, noted for the owner rather than fixed inline: `Journal.jsx`'s history drawer and `Tasks.jsx`'s reorder-priorities modal had neither Escape-to-close, focus-trap, nor scroll-lock at all — pre-existing gaps from before Tier 1's own retrofit, unrelated to the containing-block bug since neither is nested inside another modal. Journal's was fixed same-day on request (see below).
- Owner follow-up, same day: "fix the journal things you mentioned." `Journal.jsx`'s history drawer gained `useEscapeToClose`/`useFocusTrap`/`useScrollLock` (the same 3-hook baseline every other modal already has) plus an `aria-label="Close"` on its bare ✕ button. Not nested inside another modal (Journal is a top-level page), so no portal was needed — just the missing baseline protections.
- Owner follow-up, same day: "run this check on every single jsx page and popup and make sure they all are as should be." A genuinely exhaustive, systematic sweep rather than more reactive spot-fixes — three things checked across the entire app:
  1. **Every modal now has all 3 baseline hooks** (`useEscapeToClose`/`useFocusTrap`/`useScrollLock`), not just the ones already touched while chasing individual reports. `useScrollLock` had only reached 8 of 35 modal-owning files before this pass; retrofitted into the other 27 (~35 total instances) via two parallel background agents, each given the exact existing `useFocusTrap` call and argument to mirror so the two hooks stay active under the identical condition — every diff verified by hand afterward, not just the agents' own summaries. Also found and fixed two MORE genuinely un-audited modals this way (not just missing scroll-lock — missing all three hooks entirely, the same class of gap Journal's fix closed): `Layout.jsx`'s mobile "All Modules" drawer and `Chat.jsx`'s own "Chats" history drawer (near-identical in shape to Journal's). `Tasks.jsx`'s reorder-priorities modal (flagged but deliberately left alone on the "fix the journal things" request) was fixed here too now that the ask was explicitly "every single" one. File coverage confirmed identical afterward: `useEscapeToClose`/`useFocusTrap`/`useScrollLock` each now present in exactly 35 files.
  2. **A second, broader icon-only-button `aria-label` sweep** — the 2026-09-04 sweep only searched for the `✕`/U+2715 glyph; re-swept for `×`/U+00D7 (a visually near-identical but distinct character), `‹`/`›` (month-navigation arrows), and bare `+`/`＋` (add buttons), finding and fixing ~24 more instances across 11 files (RecurringPanel, TransactionModal, InvoicesPanel, ContactDetail, ContactModal, BookSettings ×7, Household, Team, Calendar month-nav arrows, PriorityList's category-add button) that the original sweep's narrower glyph search had missed entirely.
  3. Confirmed via `comm`-diffed file-list checks (not spot-checking) that no modal-shaped component anywhere in the app is missing from this inventory: every file accepting an `onClose` prop either owns a real modal (now covered) or is a page passing that prop through to an already-covered child component; every `role="dialog"`/`role="alertdialog"` component is covered.

  `eslint --max-warnings 0` across the full `src` tree and `vite build` both clean throughout.
- Owner follow-up: "fix the remaining accessibility things then enter plan mode for the two major ones." Closed the last named a11y gap — real ARIA Tabs pattern (`role="tablist"`/`"tab"`, `aria-selected`, roving `tabIndex`, arrow-key navigation via a new shared `lib/tabListKeyboard.js`) added to every genuine content-switching tab widget in the app: Goals' ME/pool tabs and Finance's view tabs (the two named in the backlog item), plus 3 more of the identical shape found during the same pass — Household's/Team's Calendar/Tasks tab bar and UserDetail's Personal/Business workspace tab. Deliberately did NOT apply the same pattern to Tasks'/Contacts' filter chip rows, Finance's Sort-mode picker, or TransactionModal's/ContactModal's Expense-Income-Transfer and Person-Company form-field selectors — those are filters and form controls, not tabs switching between content panels; mislabeling them `role="tab"` would tell a screen reader something false. Also checked every `<img>` in the app for a missing `alt` — both real (non-decorative) images already had one. This closes the "broader page-by-page audit" item — nothing further is open.

**Declined/dropped this session — do not re-propose without new information:**
- Native app-store wrapper (Capacitor) — dropped entirely. Doesn't remove the server dependency (this app was never offline-first) and the update-cycle concern is largely avoidable (a WebView pointed at the live domain means only native shell/plugin changes need store review) — but the owner judged it not worth building regardless.
- Non-color priority signal — retired. `Tasks.jsx:344` already renders priority as a plain text badge, not just a color (verified 2026-09-04); no color-only indicator exists anywhere in the app. Original backlog premise was stale.
- Split pasted comma/newline text into multiple tags (TagInput) — declined, owner's call.

**Deferred, revisit after the rest of this batch ships:**
- **User avatar / Profile-Contact merge** — owner wants Profile and the self-contact to eventually become the same record, with per-field privacy (others see only what the owner explicitly allows). Real architectural question raised and researched this session, deliberately parked: self-contact today is NOT stored in the user's own Brain folder — it's deliberately stored in the `_household` pool (`contacts_service.py:230-234`, verified 2026-09-04) specifically so it (a) survives account deletion for free and (b) is cross-workspace visible for free; moving it into the user's own folder would solve module-independence (today the feature breaks if Contacts is uninstalled) but reopen both of those already-solved problems. Two live options when this returns: (1) cheap fix — promote just the photo (maybe display name) to a core `auth.json` field, independent of Contacts entirely, mirroring how `get_profile`/`update_profile` already stayed core independent of Contacts' module state; (2) the full merge — Profile becomes the self-contact, gets permanent/uninstallable-module status (mirroring Tasks/Chat/Dashboards, since Profile is already unconditionally core), plus a new field-level privacy primitive (real small precedent already exists: `_PRIVATE_SHORT_FIELDS` hardcodes height/weight as always-private on a self-contact). Owner explicitly wants this held until the rest of this batch is done, not decided now.

---

## Security

From the 2026-07-19 audit (full detail in `docs/Security-Audit-2026-07-19.md`) plus later findings. All CRITICAL/HIGH items are shipped — see `CHANGELOG.md` [0.4.0]. What's left, roughly in order:

- [ ] **App-level 2FA (TOTP)** — the last open item from the audit's account-takeover threat model, and a v1.0-trust-stack gate. Needs its own design pass: TOTP enrollment/QR provisioning, recovery codes, storage on the user record, verify step wired into `/auth/login` + `/auth/token` (after the existing lockout check), optional admin enforcement policy, "remember this device"
- [ ] **Deploy verification for the infra-hardening pass** — the docker socket-proxy / port / image changes need a real-host check (no Docker in the build env): `docker compose config` parses; socket-proxy starts; the app reaches Docker via `DOCKER_HOST=tcp://socket-proxy:2375`; Admin → Automations can start/stop/restart n8n; n8n is reachable at `http://n8n:5678` internally but **not** on the host's public IP; secure installer defaults hold on a fresh boot. **Caution:** never rotate `N8N_ENCRYPTION_KEY` on an instance that already has n8n data
- [ ] **Defense-in-depth odds and ends** — checksum installer scripts (assessed 2026-08-12: `launch.sh --install-deps`'s `curl | sudo sh` bootstraps for Docker/NodeSource are already transparently documented as trust-on-first-use; a real fix is switching to their GPG-signed apt repositories, not a checksum, since the bootstrap scripts themselves change too often for a pinned hash to stay valid — needs its own pass, not a quick patch); signed-tag verification or a human gate in `update.sh`'s auto-pull (assessed 2026-08-12: a human gate conflicts with `update.sh`'s primary unattended `--cron`/`--watch` use case — needs a deliberate TTY-aware design, not a blind add)
- [ ] **Enable signed updates on managed instances** — `UPDATE_REQUIRE_SIGNATURE=true` already exists; needs GPG-signed release tags + the signing pubkey imported into each managed instance's updater keyring

---

## Launch surface (dev work only — business/ops/marketing items tracked in the private Business repo's `TASKS.md`, not here)

- [ ] **Screenshots in README** — 3+ images + a 30-second GIF of the AI using its memory
- [ ] **CONTRIBUTING.md** — how to run locally and submit a PR (CLA/DCO decision this depends on is tracked in the private Business repo — legal/licensing strategy, not dev work)

---

## Features that unblock scale (build when demanded)

- [ ] **Finance module — issues & redesign, bundled pass (owner, 2026-07-31)** — five related asks against the current Finance UI (`pages/Finance.jsx`, `finance_service.py`, `finance_planning_service.py`); needs a design pass before build, none of it shipped yet. (Last-opened book per user, originally item 1 of this bundle, shipped 2026-08-15 — see CHANGELOG.)
  1. **Recurring transactions: auto-draft vs. manual-confirm mode** — today `finance_planning_service.py` only reactively matches landing transactions to bills; add a per-item mode where **auto** posts a real transaction on `next_due`, **manual** creates it `pending_confirmation: true` (excluded from balances) and notifies the user with an inline confirm action.
  2. **Expense category sub-groups** — categories are a flat list today (`{name, kind}`); add a `parent` field + parent-aware aggregation in `finance_reports.py` and Budgets.
  3. **Finance page redesign** — book list → dedicated per-book page. Main page becomes just the book rows + "＋ New book"; clicking a book opens its own page with its own "＋ New transaction"/"＋ Add invoice"/"Ask AI" buttons; the Bank/SimpleFIN panel moves into that book's own Settings page.
  4. **Remove the "＋ Account" button** from the household/team pool balance card — pool bank accounts are admin-managed via Admin → Bank Connections, so a member-facing add button doesn't belong there.
  5. **Book Settings as its own page**, not a modal — fits naturally with #3's per-book page, more breathing room than the current 536-line modal.
- [ ] **Finance: recurring % auto-transfers (owner, 2026-07-20)** — the cross-book/cross-workspace Transfer primitive itself shipped 2026-08-14 (`POST /finance/transfers` + linked-pair edit/delete, excluded from income/expense reports); what's left is recurring percentage-based splits (e.g. auto-move 10% of every paycheck into savings) on top of it
- [ ] **Contacts overhaul — big feature bundle (owner batch, 2026-07-20)**:
  1. **Sharing to household/team + peer users** — mirror the Assets/Finance/Notes sharing pattern.
  2. **Tags UI parity** — pill chips with remove buttons like Assets/Notes; tags become a persistent, filterable vocabulary.
  3. **Contact links inside Journal and Notes entries.**
  4. **Per-contact profile page** — the read-first `<dl>`-grid card already shipped (2026-08-03) for every contact; still open is the AI re-inference/update cadence (every few days, batched, only if a link/field changed — owner-approved 2026-07-20, keeps AI cost bounded).
  5. **Name fields: split into First/Middle/Last + prefix/suffix** — apply to both Contacts and user accounts in the same pass.
  6. **Cosmetic: customizable contact avatar/"character"** — lowest priority in this bundle.
  (Cross-workspace contact sync — sub-item 3 of the original 7 — shipped 2026-08-17 as a per-contact `cross_workspace` toggle, one real record visible from both workspaces rather than an admin-only propagate-both-ways sync; see CHANGELOG.md.)
- [ ] **Cross-module stale-pointer repair on ownership transfer/deletion** — an Asset's `contact` field, a Deal's `linked_asset_ids`, an Invoice's `contact_id` can go stale when one side transfers to a different owner than the other, or one transfers while the other deletes. Deliberately deferred — matches the app's existing tolerance for stale cross-module ids elsewhere (owner-confirmed acceptable to defer)
- [ ] **Assets follow-ups (deferred)** — template-key rename; convert pool assets back to personal; multiple named templates with preset values per structure; bulk CSV import; map/gallery views; per-field required/validation rules at template level; pool-task linking; AI bulk ops / cross-branch relations / clone / export-import / history-revert; upgrade the member-name selector to a permissioned/opt-in model (currently any Assets user sees all member names)
- [x] **Ollama / local LLM support** — shipped 2026-09-02 as part of the full Admin → AI Settings picker overhaul (Ollama, LM Studio, vLLM, and other local runners alongside ~25 named cloud providers; opt-in live model-list fetch). See CHANGELOG.md / docs/MEMORY.md Key Decisions Log.
- [ ] **RAG over the Brain (v0.2)** — embeddings + semantic search over notes/journal/files, auto-fed into chat context. Design rule (locked): vector index is a disposable derived cache (e.g. Chroma), rebuildable from Brain files anytime, never source of truth. Local-embeddings option pairs with Ollama. Target with the public demo — also the durable fix for `search_brain` being substring-only (see AI Agent findings below)
- [ ] **AI-built n8n automations (v0.4)** — natural language → generated workflow + preview/approve before activation; the flagship demo
- [ ] **Automation Inbox generalization** — from land-leads-specific to any workflow writing reviewable results
- [ ] **Instance provisioning script** — one command: VPS → tunnel → Infisical → configured instance. Must clone via the public HTTPS remote (never `git@github.com:` — strands the updater when the cron user has no key) and install exactly one updater cron for the user owning the checkout
- [ ] **Importers: Todoist / Notion / Obsidian → Brain** — "import my digital life"
- [ ] **Stripe billing portal** — self-serve paid signup for hosted plans
- [ ] **Monthly value report** — auto-generated from Automation Inbox data (leads found, actions taken, hours saved)
- [ ] **Email digests + richer proactive digest (v0.3)** — calendar/journal-aware "what matters today"; email delivery (Web Push requires an install/permission grant, a barrier for non-technical users)

---

## AI Agent Architecture — findings (2026-07-31 code review)

From a full walkthrough of the chat agent (`services/agent_service.py`, `services/ai_provider.py`, `routers/chat.py`, `pages/Chat.jsx`) for efficiency/effectiveness/accuracy/humaneness gaps. Not yet scoped or scheduled — triage into Now/Backlog as needed.

- [ ] **No prompt caching on the agent system prompt** — `ai_provider.py`'s `_anthropic`/`_anthropic_agent` never set `cache_control` on the system block, even though the same system prompt (Brain context: profile + memory + tasks + priorities + help index) is resent unchanged on every step of a run (up to `MAX_STEPS=10`) and on every new chat turn. Cheap win, no behavior change
- [ ] **Long chats hard-fail instead of degrading** — `Chat.jsx` sends the full in-memory message array uncapped; `ChatRequest.history` has `max_length=50` and Pydantic 422s once a session crosses it — no client-side trim, no server-side summarization (could reuse the existing `append_memory`/`rewrite_memory` tools)
- [ ] **No retry/backoff on transient AI provider errors** — `ai_provider.py`'s `_anthropic`/`_openai` calls have no try/except; a single 429 or network blip anywhere in the loop kills the whole request and nothing from that run is saved (`_save_run` only fires at the end)
- [ ] **No streaming of agent steps to the UI** — `run_agent` runs its entire loop (up to 10 LLM round-trips + tool calls) server-side before `routers/chat.py` returns one JSON blob; SSE streaming of steps as they happen would be a meaningful perceived-responsiveness win for multi-step tasks
- [ ] **`search_brain` is substring matching, not semantic** (`agent_service.py:1548`) — plain `query.lower()` scan; misses synonym/paraphrase queries. Feeds into the RAG over the Brain item above rather than being a separate project

Cross-reference: the per-user JSON write race (`task_service.py` has no read-modify-write lock) is tracked above under Security and under Idea Backlog → Technical/Architecture/DevOps — not repeated here.

---

## Product Backlog (pull in when demand appears)

- [ ] **Dashboard page doesn't handle a "dashboard disabled for me" state gracefully** — found 2026-08-27 while checking dashboard/'s own conversion for cross-module issues (there aren't any; `dashboards_service.py` etc. all stay core, unconditional). Real, pre-existing, unrelated to the conversion itself: `App.jsx`'s root route (`/`) has always been hardcoded and unwrapped by `ModuleRoute` — necessarily so, since wrapping it would self-redirect-loop for a disabled user already at `/`. But an admin *can* still disable the "Dashboard" module for a role or user via the existing generic role editor (it's toggleable exactly like Tasks, another locked module), and `require_module("dashboard")` correctly 403s their API calls — the frontend just has no graceful handling for that case, unlike every other module's clean `ModuleRoute` redirect-away. `Dashboard.jsx` should detect the 403 and show a friendly message instead of a broken/empty page.
- [ ] **In-app Module Store (owner direction, 2026-08-03)** — owner wants to build out the growing module wishlist (see Idea Backlog below) personally, in-house. The product answer is a browsable in-app catalog where a user self-service activates/deactivates modules, reusing the existing `disabled_modules` + feature-role gating (no new permission model). Prerequisites: route-level code-splitting (today all pages ship in one JS bundle — tolerable at ~14 modules, not once most users have most of 30-40 switched off); curated default-on sets per profile type so onboarding isn't a 40-tile wall; store-eligibility gated per feature role/instance on top of the existing module gate
- [ ] **Profit First method for Finance** — allocation-based budgeting (Income → Profit / Owner's Comp / Tax / Opex accounts with target percentages, instant-assessment view, quarterly distributions); needs a design pass before build. Likely built on the cross-book Transfer primitive above
- [ ] **Cross-module linking: any-to-any generalization (last piece)** — the concrete client → job → money links (Deal↔Asset, Transaction↔Asset/Deal, Invoice↔Deal, Asset→Contact) all shipped; what's left is only a *generic* any-record-to-any-record link primitive if the pointer-per-pair pattern ever gets unwieldy
- [ ] **Waterfall/cascading account balance visualization** — chart showing balance flow across accounts; check whether the existing Overview/projection views already cover this before building a new component. Ties to the Transfer primitive above
- [ ] **Admin: reset a user's password** — generates a random temp password; user must set their own on next login. No UI reveal, no in-app notification needed
- [ ] **Journal: block future-dated entries + AI append-only writes** — disallow opening/creating a journal entry dated in the future; let the AI append-only to journal entries (never overwrite)
- [ ] **Help feedback delivery** — the Help page only instructs users to email support today, no backend. Add a `SUPPORT_WEBHOOK_URL` → Formspree/email relay for demo/managed instances; self-hosters get in-app admin-inbox delivery by default
- [ ] **Help follow-ups** — full interactive coach-mark product tour (v1 ships only the Getting Started checklist); short GIF/video walkthroughs per module; ⓘ buttons that open AI chat pre-asked "how do I use X?"; per-page inline empty-state/tooltip copy rewrite
- [ ] **Ongoing: keep `content/help.json` current** — update a module's Help guide/FAQ when its UX changes, add a `whats_new` entry every release
- [ ] **Library/Archive module** — ebooks, audiobooks, podcasts, custom book entries, "author a book" features, PDFs. Owner is debating one combined module vs splitting into `archive`/`library` — currently leaning toward splitting but undecided on the exact boundary. Needs a design pass: storage shape (likely Assets-template-style), file handling for large media, and transfer support between the two once split
- [ ] **Competitive research pass** — review comparable life-OS/productivity/media-library apps (Notion, Todoist, Obsidian, Habitica, Calibre-Web, Audiobookshelf, Plex — confirm list with owner) for concrete feature ideas, especially for the recurring-tasks and Library/Archive items
- [ ] **Projects module** — project tracking with tasks, milestones, and status
- [ ] **Multi-day calendar events** — `start_date`/`end_date` schema + a calendar renderer that spans cells
- [ ] **Personal calendar task completion toggle** — tasks in the CalendarGrid day detail panel need a done/undo button
- [ ] **Projects / chat system evolution** — ChatGPT/Claude-style Projects: named projects with custom context, per-project chat archives, optional agent usage
- [ ] **Quick capture** — email-to-inbox (forward email → task/note), PWA share_target, quick-add hotkey; capture must take <2s
- [ ] **Journal → insight loops** — weekly AI pattern detection (mood vs sleep etc.) beyond the existing weekly review
- [ ] **Offline-first PWA sync** — local-first data + background sync + conflict resolution; structural advantage of file-based storage, but a big lift
- [ ] **v1.0 trust stack — gates the Show HN post** — app-level 2FA, automated backups + one-click restore, audit logging, <10-min onboarding, real docs, test-coverage push; plugin API if feasible

---

## Idea Backlog — by category, awaiting owner triage

Generated across a systematic search→generate→compare→document pass over the whole codebase (pages, components, routers, services), plus two brainstorming passes for new-module ideas (2026-08-02 conversational, 2026-08-03 competitive research against real self-hosted OSS projects). Everything here is **unvetted** — nothing moves to an active section above until the owner pulls it in. Organized by module/theme so related ideas sit together (reorganized 2026-08-12, previously scored P0-P3 by impact — that scoring was dropped in favor of category grouping). ~219 ideas total. Roughly ordered highest-value-first within each category, but nothing here is sequenced against anything else.

### Growth & Revenue

- Self-serve pricing page + tier comparison on logcoretech.com. The README says "Hosted plans coming soon" with no pricing anywhere; blocks demo→paid conversion since a visitor can't self-qualify.
- In-app upsell path: self-hosted → managed hosting. Nothing in the app tells a happy self-hosted admin that managed hosting exists — zero-cost distribution to the best-qualified lead pool.
- Multi-tenant admin console (Business-repo tooling, not the OSS app) for managed hosting. Manual per-instance tracking stops scaling past a handful of tenants.
- Referral program (self-hosters → managed hosting signups) — cheap CAC channel once billing exists.
- SEO-indexable comparison page: LogCoreOS vs Notion AI / Khoj / Open WebUI.
- Reframe the "import your digital life" importer as the acquisition-funnel CTA itself, not just a migration convenience.
- Free/paid feature-gate design pass before Stripe billing lands — avoids re-architecting `disabled_modules`/usage-counter code later.
- Concrete managed-hosting tier proposal mapped onto the existing workspace/module system (Personal → Family → Business) — billing-implementable with zero new architecture.
- Managed-hosting module/feature engagement tracking — consent is already implicit in a hosted agreement; without this, every roadmap call is a guess.
- Tenant onboarding checklist/SOP doc (Business repo) — deploy steps are still manual and ad hoc per instance.
- Support ticket/help-request intake for managed customers, distinct from self-hoster mailto-only Help feedback.
- Track `last_active` per user — foundational; every retention/win-back/dormancy mechanism needs this one field first.
- Public roadmap page fed from a trimmed view of this file.
- GitHub Sponsors / OpenCollective for the OSS side.
- Case-study blog post using the owner's own dogfood usage.
- Add `CODE_OF_CONDUCT.md` (Contributor Covenant) — missing entirely, expected-by-default for OSS.
- "Good first issue" labeling pass across the existing backlog.
- Self-hoster showcase / "who's running LogCoreOS" opt-in wall.
- Real-time community channel (Discord or Matrix), distinct from async GitHub Discussions.
- "Invite your household/team" prompt after first-user setup — nothing currently nudges an admin toward the multi-user differentiator.
- Demo → real-signup bridge (carry over what a demo visitor created instead of losing it to the nightly reset).
- "Bring your own AI key" discount tier — transfers the biggest variable cost off LogCore's books using tech that already exists.
- Founding-member/early-adopter lifetime-discount pricing for the first N signups.
- AI usage overage pricing (pay-per-additional-message) as an alternative to a hard cap.
- Per-tenant data export/offboarding flow — the technical export exists; the business commitment/process doesn't.
- Managed-hosting SLA/uptime commitment page (sequence after the status page).
- Backup verification report per tenant.
- Opt-in, anonymous, aggregate telemetry toggle for self-hosted instances — the roadmap is currently flying blind on the majority of the userbase's actual usage.
- Lightweight in-app NPS-style feedback prompt.
- Public "Security & Trust" marketing page — the in-app version only reaches people who've already signed up.
- GDPR Data Processing Agreement template for managed-hosting business customers.
- EU data-residency option for managed hosting.
- Affiliate/creator partnerships (r/selfhosted YouTubers etc.) — sequence after the product is more polished and pricing is live.
- White-label option for reseller/agency managed hosting.
- Confirm no cookie-consent banner is legally required (a documentation check, not a build item).
- Cyber liability insurance for the managed-hosting business (a Business-repo/ops item, not app work).
- Multi-seat/family bundle discount pricing.
- Nonprofit/student discount tier.
- Trial-to-paid nudge sequence for managed hosting (day-3/day-10 check-ins).
- Contributor recognition in README (contributors section or all-contributors-style bot) — sequence after CONTRIBUTING.md and the good-first-issue pass.
- Post-launch release newsletter/mailing list, distinct from the pre-launch Waitlist form — keeps self-hosters engaged across releases.

### Trust, Security & Reliability

- Public status page (status.logcoretech.com) for demo + managed instances.
- One-click restore drill / documented DR runbook — backups exist but have never been verified end-to-end.
- Admin action audit log (who changed what, when) — user deletion, role changes, module toggles leave no queryable trail today.
- Self-service "Change password" in Settings — no path exists today for a logged-in user to rotate their own known password.
- "Sign out of all other devices/sessions" button — the JTI-revocation mechanism already exists, just isn't exposed for this.
- Block the last-admin demotion/deletion path — nothing stops permanently locking an instance out of its own admin functions.
- Warn (or block) deleting a feature role still assigned to users — can silently widen access via the `member` fallback (see the matching Security CHECK item above — same root issue).
- Fix the admin-create-user password handoff — no forced change, no invite-link option; the admin invents and relays a password by hand today.
- Decide deliberately whether `/docs`/`/redoc` stay enabled on every deployment, especially the public demo.
- Independent third-party penetration test before managed hosting accepts non-beta paying customers.
- SOC 2 readiness gap-assessment (a document, not an audit).
- Bug bounty / vulnerability reward program.
- Add a server-side confirmation/step-up requirement for physical-security-relevant Home Assistant domains (`lock`, `cover`) — the frontend `confirm()` is trivially bypassable via direct API calls.
- Consider a higher or NAT-aware login rate limit — a household sharing one IP can have one member's typo lock out the whole family.
- Scoped/multiple automation tokens instead of one shared instance-wide credential.
- Home Assistant Auto-mode carve-out — require approval for unlock/garage-open actions even in Auto mode, as a permanent exception regardless of how the general AI auto-mode destructive-action fix lands.
- Biometric/PIN app-lock on launch — the app opens straight to finance/journal data with no re-auth gate.
- Self-service "Delete my account" in Settings (right-to-erasure, land alongside the cascade-delete bug fix).
- Admin "view as"/impersonate a user for support troubleshooting, fully audit-logged and time-boxed.
- Terms-of-Service acceptance tracking (timestamp + version on the user record).
- Publish `/.well-known/security.txt` pointing to `SECURITY.md`.
- "Forgot password? Ask your admin" login-page hint — interim messaging fix so a failed-login user gets guidance instead of a generic error.

### AI & Chat Agent

- **Auto mode executes destructive AI actions (deletes) with zero human confirmation, and there is still no trash/undo backstop anywhere in the app.** The single most severe finding in the original backlog pass — an AI in Auto mode that misreads an instruction can permanently destroy real data with no confirmation and no recovery path. Fix before promoting Auto mode as safe for general use: either keep destructive tools approval-gated even in Auto mode, or ship a trash-bin/soft-delete backstop so any AI-driven delete is recoverable regardless of mode.
- ~~AI change-log / "what the AI did while I was away" digest~~ — shipped as the Welcome-back popup (UX Polish Batch section above, 2026-09-04) — the two ideas merged into one feature.
- Cross-module AI proactivity — surface overdue follow-ups, open deals, and 30-day-overdue linked invoices via the existing suggestions engine; the linking data already exists, this just makes it visible.
- "Ask your Brain" natural-language search (RAG-lite stepping stone) ahead of the full v0.2 RAG project.
- AI usage transparency widget for the end user, not just the admin.
- Differentiate destructive AI actions in the `ApprovalCard` UI — currently a benign edit and a permanent delete render identically, with a raw ID instead of a readable summary.
- First-AI-chat quick-start prompt chips, surfacing the example commands already documented as working.
- Messaging-platform bridge for the AI (WhatsApp or similar) — Khoj ships this; LogCoreOS has no equivalent.
- Local LLM quality/model-picker guidance once Ollama support ships.
- AI-drafted weekly/monthly "life report" (a narrative, not a task list).
- Multi-model side-by-side comparison in chat (sequence after multi-provider support ships).
- Chat inline citations/links when the AI references a specific Brain file it read.
- Optional inline correction field on Chat's "Deny" action.
- Smart chat auto-scroll — only auto-scroll when already at/near bottom; otherwise show a "↓ New messages" pill instead of forcing scroll during streaming.
- Automated prompt-injection red-team test suite for the AI tool registry.
- Voice input for chat (mobile PWA).
- Short-TTL cache for repeated/identical web searches (a modest AI-cost lever).

### Cross-App UX & Polish

Fully triaged 2026-09-04 — see the **UX Polish Batch** section near the top of this file for the 30 approved/specced items (build not yet started) and their disposition. Only one item from the original list wasn't pulled in:

- "Focus mode" toggle on the Dashboard (collapse to just the Top-3 card) — explicitly backlogged 2026-09-04, no build scheduled, still awaiting owner triage like everything else in this section.
- **Swipe gestures for common list actions** (complete, archive; swipe-right = primary, swipe-left = secondary) — approved and scoped as part of the UX Polish Batch (item #17), but pulled back out and returned to the general backlog 2026-09-05 (owner: "skip the swipe gesture. put it back on backlog") rather than built this pass. Real per-module design questions were never resolved (does it apply to every list — Notes, Contacts, Assets — or just Tasks; what does "swipe right" even mean on a Contact) — needs its own triage pass whenever it's picked back up, not just an implementation slot.
- Group Home Assistant entities by room/area instead of domain-only tabs — approved 2026-09-04, folded into the UX Polish Batch section above (listed there under its own line).
- User avatar/profile picture — see the UX Polish Batch section's "Deferred" list above; a real architectural question (Profile/Contact merge) is attached to this one, not a simple build.

### Technical / Architecture / DevOps

- Automated E2E test suite (Playwright) covering the golden paths. The entire test suite is backend pytest only — zero frontend/integration coverage. Every recent UI bug (mobile header clipping, footer gap, off-screen buttons) was owner-found by hand; a handful of Playwright specs on core flows would catch this whole bug class in CI.
- Structured error monitoring (Sentry or self-hosted GlitchTip) for backend + frontend. No centralized error visibility exists anywhere today — bugs are found by owner testing or user reports only. A self-hostable option fits the project's anti-vendor-lock-in ethos.
- Audit whether CI actually gates the frontend build, or only backend pytest.
- Baseline transactional email infrastructure (a provider-abstracted `email_service.py`) — unblocks password reset, Help feedback delivery, and email digests in one shot; the app currently has zero outbound email capability at all.
- Consolidate the four near-duplicate share/access-resolution implementations (Assets/Finance/Contacts/Notes) — the same bug class has independently been found and fixed at least twice for Assets alone.
- Break up `services/agent_service.py` (2,368 lines, the whole AI tool registry) into per-module tool files.
- Close the API-doc coverage gap — only ~39% of the actual 298-endpoint surface is documented in the hand-maintained `docs/API.md`.
- Hosted developer/API documentation site, generated from the OpenAPI schema — early groundwork for the Phase 7 plugin-ecosystem roadmap item.
- Migrate the remaining per-user JSON stores (Assets, Finance, Dashboards, …) to `file_service.update_json()` — the shared read-modify-write helper shipped 2026-08-12 (see `docs/MEMORY.md`) closes this race for Tasks specifically, and for Contacts' `create_contact()`/self-contact onboarding specifically as of 2026-08-17 (a real, no-longer-theoretical race once every user's self-contact converges on the same shared household-pool file); every other service, and every other Contacts mutator, still does an unlocked `read_json()`+`write_json()` pair and has the same theoretical lost-update exposure, just not yet demonstrated or fixed there.
- CONTRIBUTING.md scope note documenting the AI tool-registry pattern in `agent_service.py` — the least self-explanatory, most-touched file for new contributors.
- Feature-flag-driven canary rollout to managed instances before self-hosted `master`.
- Staged/canary rollout across managed tenants for releases, distinct from what gets installed.
- Structured application logging (JSON + level config) instead of ad-hoc `logger.*` calls.
- Dependency vulnerability scanning in CI (Dependabot/Renovate + `pip-audit`/`npm audit` gate).
- Load/perf smoke test before the public demo opens registration.
- Split `routers/auth.py` (1,009 lines, five unrelated concerns) by concern.
- Deep health-check endpoint — `GET /health` is a hardcoded `{"status":"ok"}` with zero real checks.
- Module scaffolding script implementing the documented 7-step "Adding a New Module" checklist.
- Scheduler job isolation audit (a verification pass, not a known bug).
- Fix the FastAPI app's hardcoded `title`/`version` to read from `VERSION`.
- Lightweight numbered ADRs for major decisions, cross-linkable from PRs.
- Container resource limits (`mem_limit`/`cpus`) — no service anywhere has a ceiling today.
- Import dry-run preview — show exactly what the Todoist/Notion/Obsidian importer will create (counts, sample mapped items) before committing anything.
- Automated Brain export/import round-trip test — export a seeded Brain, spin up a fresh instance, confirm it's actually usable; the portability promise is currently unverified.
- i18n framework foundation (react-i18next), even before translation itself is prioritized — no framework exists at all today.
- Admin at-a-glance instance health summary strip (user count, version, last backup, AI usage, failing jobs).
- Fix the request-amplification pattern behind full-reload-on-every-toggle, and add a clear 429 message with retry timing.
- Validate the timezone field against a real IANA zone list instead of free text.
- Route-level code-splitting via `React.lazy()` — all 21 pages ship in one bundle today.
- Virtualize the highest-volume lists (Finance transactions, Notes tree) — the app's own pitch is years of accumulated data, and nothing renders efficiently at that scale yet.
- "View as"/role preview for admins, without creating a throwaway test account — a dev/testing-tool variant distinct from the audit-logged support-impersonation item under Trust & Security above.
- Synthetic canary account per managed instance (scripted login + action check).
- Configurable data-retention windows (chat archive age, backup count, notification history).
- Formal quarterly dependency-upgrade cadence, distinct from automated vuln scanning.
- Aggregate crash/error-rate rollup across all managed tenants, once per-instance monitoring exists.
- Pre-update backup verification gate in `update.sh`.
- Near-zero-downtime updates for managed tenants (blue-green/rolling), once downtime is actually measured against a promise.
- Per-module selective export (e.g. just Contacts or Finance) distinct from the full Brain zip.
- Report bundle size on every PR to catch silent bloat.

### Finance module

- Multi-currency-aware Finance reporting (real FX conversion into one blended total) — `net_worth()` groups by currency instead of blending as of 2026-08-12 (correct, but a EUR book and a USD book still show as two separate numbers rather than one converted total); this is the fuller version of that fix, if a single blended figure is ever wanted.
- Split transactions across multiple categories.
- Bulk transaction recategorize/edit — bank sync and CSV import routinely land dozens of uncategorized transactions at once with no bulk tool.
- Savings goals tied to an account balance, distinct from task-type Goals.
- Budget rollover option (envelope-style, instead of a hard monthly reset).
- Auto-post planned one-off transactions on their due date instead of requiring manual re-entry.
- Period-over-period comparison + a trend chart in Reports — currently raw totals only, no direction.
- Manual "Sync now" button for bank connections.
- Category rename — today the only option is a destructive delete-and-recreate that strips all existing categorization.
- Recurring/subscription invoice generation for retainer clients.
- Accountant-friendly export formats (QIF/OFX) beyond CSV.
- "Skip this occurrence" on a recurring bill without pausing the whole rule.

### Assets module

- QR/barcode label generation + scan-to-open for Assets — the most tangible "built for real life" feature available in the product.
- Warranty/registration/service-due reminders — the actual killer feature of dedicated home-inventory apps, and mostly wiring existing pieces (templates, notifications) together.
- Estimated-value tracking over time, rolled into net worth separately from cash accounts.
- A dedicated Insurance view (everything tagged insured, with attached policy docs).
- Search/filter box in the asset tree picker — currently expand/collapse only, in a module explicitly built for large hierarchies.
- Drag-and-drop file upload for attachments (click-only today).
- Breadcrumb trail in the Asset modal for nested drill-down.
- Read-only public share link for an asset or subtree (e.g. for an insurance adjuster).

### Contacts/CRM module

- Wire up the already-stored Contacts `birthday` field to an actual reminder — validated and stored, but nothing ever reads it.
- Deal-pipeline analytics (win-rate, average deal size, time-to-close) — the kanban already tracks everything needed.
- Duplicate-contact merge tool, distinct from the create-time dedup search that only prevents new duplicates.
- Contact engagement/lead score based on interaction recency.
- Additional contact-list sort modes (recently added, most recent interaction) — the list is alphabetical-by-name with an A-Z jump strip as of 2026-08-14; those two other sort keys are still open.
- The "Employer" picker in a person contact's career-history editor doesn't filter to company-type contacts, and its quick-create hardcodes `type: 'person'` even in that context — noticed 2026-08-14 while building the company/person field split, deliberately left alone as a separate, smaller polish item.
- True drag-and-drop between kanban deal-stage columns, not just a dropdown.
- Contacts import from phone/Google contacts CSV.
- Email/calendar two-way sync for Contacts (blocked on the app having no email infrastructure at all).
- Convert a pool contact back to personal (2026-08-17 shipped the personal→pool direction, single + bulk; the reverse isn't built — mirrors the identical already-listed gap for Assets above).

### Notes & Journal

- In-module quick-filter for Notes' own folder tree (distinct from the 2026-08-29/30 app-wide search modal, which already covers title+content search for Notes/Journal from the header) — folder-tree-only browsing still stops scaling past a couple dozen notes when you're not searching, just navigating.
- Obsidian/editor plugin bridge for Notes — a low-switching-cost adoption wedge, as Khoj also ships.
- Notes version history / "restore previous version" — auto-save with no explicit save can silently overwrite a good edit.
- Journal mood/tag quick-picker on entry.
- Jump-to-date calendar picker for Journal (search-by-keyword shipped 2026-08-29/30 via the app-wide search bar — this is just the remaining "pick a date, land on that entry" navigation piece).
- Pin/favorite notes.
- Optional daily journal writing prompts.
- Basic conflict detection on Notes save (a stored-hash check, not a full CRDT) — concurrent edits from two devices silently overwrite one side today.
- Note templates, mirroring the pattern Assets already proves works well.
- Notes module improvements inspired by Trilium Notes (owner recommendation, 2026-08-03) — note attributes (arbitrary key/value metadata, not just folders/tags), note relations/cloning (one note appearing in multiple tree locations without duplicating content), built-in per-note encryption for sensitive entries, and a calendar/day-journal view over the note tree. Worth a design pass on which of these are worth porting rather than adopting wholesale.

### Automations/n8n

- Resolve whether the native vendor-agnostic "LogCore Workflows" engine PROJECT.md promises actually gets built, or revise the docs — today all automation runs through n8n with no fallback, contradicting the "n8n never required" pitch.
- Workflow failure alerting — execution history is already surfaced, nothing proactively watches it.
- Per-workflow ROI display on the Automations page itself.
- Community workflow-template gallery for self-hosters.

### Notifications

- Multi-device push support — one subscription per user, so a second device silently steals push from the first.
- Quiet hours/do-not-disturb window, independent of per-suggestion-type toggles.
- Event reminder lead-time — the push pipeline already exists end-to-end, this is wiring it to a new trigger.
- Notify affected members when a shared household/team item they didn't create is deleted.
- Send a softer message on a zero-completion week instead of no notification at all — the weekly-review mechanism currently only reaches already-engaged users.
- PWA app-icon badge count for unread notifications.
- Actionable push notifications with OS-level action buttons.

### Calendar & Tasks

- Calendar drag-to-reschedule for tasks/events.
- Inline single-line quick-add for tasks — creating one always costs a full modal with a dozen fields today.
- Recurring calendar events (weekly/monthly/yearly) — calendar events have zero recurrence support today, unlike tasks.
- Tasks saved filter views ("My overdue," "This week," per-category).
- One-tap "snooze to tomorrow" on Due Today tasks.
- Let a household member edit/delete events *they themselves created*, using `created_by` attribution the system already tracks.
- Auto-rotating chore assignment for recurring household tasks.
- Agenda/list view toggle for Calendar, alongside the month grid.
- Milestone call-outs at meaningful streak/completion thresholds (7/30/100 days), not just a bigger number.
- Household "this week" momentum strip — every stickiness mechanism today is individual, not shared.
- Rebuild the Tasks priority-reorder modal on pointer events — native HTML5 drag-and-drop likely doesn't work on touch devices at all, and Notes already solved this exact problem elsewhere in the codebase.
- Natural-language quick-add parsing ("Call dentist tomorrow 3pm" → title + due date auto-filled) once the inline quick-add input exists.
- Optimistic UI for completion toggles — flip the checkbox instantly and roll back only on failure, instead of waiting on a full reload.
- Streak freeze / grace period (a Duolingo-style forgiveness mechanic) — currently one missed day zeroes the count with no mercy.
- Household/Team shared shopping-list tab (already scoped in PROJECT.md Phase 5 but never promoted to the active backlog).
- Optional location field on calendar events.

### New Module Ideas

Two brainstorming passes: a 2026-08-02 conversational session, and a 2026-08-03 competitive-research pass cross-referenced against real self-hosted OSS projects for demand signal (Hacker News + GitHub issues/discussions + community roundups, since Reddit itself blocks Anthropic's crawler).

- **Health/Fitness** — meds, appointments, biometrics, workout log; complements the Journal insight-loop idea.
- **Meal planning + pantry** — recipes, grocery list generation, expiration tracking; strong Household-pool fit.
- **Vehicle/equipment maintenance** — dedicated service-schedule view with due-date reminders (mirrors Finance's recurring-bill matching) instead of folding into generic Assets templates.
- **Digital Legacy / Time Capsule** — letters/instructions delivered to family on a future date or via a "dead man's switch" (no login for N days → admin notified → trusted contact granted access); reuses the scheduler + notification stack almost entirely.
- **Break-glass emergency vault** — hardened Assets variant for wills/deeds/policies where a designated contact can request access, owner/admin gets notified, and it auto-grants after a timeout unless denied.
- **Family tree / genealogy** — visualizes person↔person relationships on top of the affiliation-linking already built for Contacts.
- **Decision journal** — structured big-decision records (options, reasoning, AI-assisted pros/cons) revisited later to see how the choice played out; distinct from Journal's daily-entry format.
- **Chores marketplace for kids** — Household tasks pay out points that redeem for allowance logged as a real Finance transaction.
- **Dream journal** — literal sleep dreams, separate from the reflective Journal, with AI symbol/theme pattern-detection over time.
- **Disaster-prep / muster module** — emergency plans, supply checklists, a household "where's everyone" check-in board.
- **Memorial mode for Contacts** — a deceased contact flips from an active CRM entry into a read-only memory page others can add letters/memories to, reusing the comment infrastructure Assets/Contacts already have.
- **Self-hosting meta-dashboard** — Homepage/Heimdall-style status panel for the *other* self-hosted services a LogCoreOS admin probably also runs (n8n, ntfy, Plex, Pi-hole, etc.) — unrelated to life management, but fits the target audience.
- **RSS reader / read-later** — self-hosted Instapaper/Feedly alternative, feeding into the Library/Archive idea.
- **Chat-agent easter egg** — hidden retro game or text-adventure powered by the existing tool-calling agent; cheap, memorable personality piece.
- **"This day in history" / daily curiosity widget** on the Dashboard — no functional purpose, just a reason to open the app unrelated to chores.
- **Investing/portfolio tracker** — stocks/crypto/retirement accounts (price feeds, cost basis, unrealized gains); distinct from Finance's cash-flow ledger model, which doesn't fit this shape.
- **Career module** — job applications (stage, follow-ups, tied to a recruiter Contact), resume/CV versions, performance-review notes, skills tracked over time.
- **Travel module** — trip itineraries, packing lists, passport/visa expiry reminders tied into Calendar.
- **Pets module** — vet records, medication schedules, weight/vaccination history.
- **Caregiving / elder care module** — shared medication schedules + caregiver shift log for an aging parent, living in the Household pool.
- **Kids/parenting milestones module** — growth charts, immunizations, school info; Household-pool fit.
- **Faith / spiritual practice module** — prayer/reflection log, scripture or meditation plans, shared prayer requests within a Household.
- **Collections module** — coins, cards, wine, etc.; Assets-template-shaped but with market-value tracking instead of insurance-value tracking.
- **Legal/contracts vault** — leases, POAs, NDAs with renewal-date reminders, more precise than dumping documents in Assets attachments.
- **Language/skill learning practice logs** — streak-based practice tracking (instrument, language, any skill), riding on the existing recurring-task/habit machinery.
- **Password/secrets vault** (Vaultwarden-tier) — self-hosted password manager module; LogCoreOS already runs its own auth/JWT and stores sensitive Brain data, so a first-class encrypted vault fits the "own your whole digital life" pitch.
- **Photo/video library** (Immich-tier) — one of the fastest-growing self-hosted categories: AI face/object recognition, timeline, map view, mobile auto-backup. Real gap — Assets/Notes only handle generic file attachments today, no dedicated photo library.
- **Document scanning + OCR** (Paperless-ngx-tier) — drop in a scanned doc/photo, it OCRs, tags, and becomes full-text searchable. Distinct from Assets attachments, which store files but don't read them; extends the Legal/contracts vault idea into something mechanically real.
- **Household bill-splitting / IOU settle-up** (Splitwise-tier — at least 4 independent OSS clones exist: SplitPro, Spliit, Cospend, ihatemoney). "Who owes who" + settle-up is a distinct mechanic from Finance's per-book ledger; the clone count alone is a strong demand signal.
- **Consumables/expiration inventory** (Grocy, literally branded "ERP beyond your fridge") — batteries, meds, cleaning supplies, not just groceries; validates and broadens the pantry idea above.
- **Freelance/solopreneur billing suite** — billable-hours time tracking + client portal + proposals (Kimai, Solidtime, Logr all thriving). Sharpens the Career module idea into something that could hook straight into Finance invoicing.
- **E-signature** (DocuSeal, OpenSign, LibreSign) — contract signing tied to Contacts/Deals and the Legal vault idea; a real category with several healthy OSS projects.
- **Public appointment booking** (Cal.com-tier) — a "book 30 min with me" link, distinct from the personal Calendar module; useful for Business (client booking) and Personal (family scheduling requests) alike.
- **Personal knowledge management / spaced repetition** (Anki-tier flashcards) tied to Notes/Library — for actual retention, not just storage.
- **"Aspirations" / identity domain** — a design idea, not an off-the-shelf project: Daniel Miessler's LifeOS (a comparable "personal AI operating system") added a 5th domain, Aspirations, after realizing its other four domains (what's happening to you, what others need from you, what you owe, what you have) were all reactive/external and missed "who you're becoming." LogCoreOS's Goals module is close but oriented around concrete short-term targets; a values/character-growth layer would be a genuine differentiator.
- **Family presence/location board** — an everyday "who's home" board, distinct from the disaster-prep muster idea (which is emergency-only); family-organizer research keeps surfacing location-sharing bundled with scheduling (e.g. FamilyWall).
- **Internal team/household chat module (Slack/Discord-style)** — real-time channels + DMs for household or business-team communication, distinct from the existing AI chat assistant entirely; a Redditor specifically asked for this. Would need its own storage/delivery model (not Brain-markdown-file-shaped like the rest of the app) and a decision on whether it's pool-scoped (Household/Team) like other shared surfaces.

---

## Format

```
- [ ] Task name — short description of what done looks like
```

When a task is finished, delete it rather than checking it off — the outcome belongs in `CHANGELOG.md` (user-facing changes) and the day's Daily Note (implementation detail). For long-form history, see git log.
