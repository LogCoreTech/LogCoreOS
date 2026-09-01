# Changelog

All notable changes to LogCore OS are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Added

- **Push notifications now work on multiple devices at once.** Enable it separately on your phone, tablet, and computer — a test or a real notification goes to all of them, and Settings → Notifications lists every enabled device with its own Rename and Remove buttons, so dropping an old device you no longer have doesn't touch the others. Previously, enabling push on a second device silently stole notifications from the first with no warning. Capped at 10 devices per account.
- **Recurring tasks now support a real day-of-week/day-of-month picker.** Pick any combination of weekdays, a specific day of the month (or "last day"), a "2nd Tuesday"-style pattern, monthly/yearly cadences, and an every-N-periods interval — not just a plain daily/weekly/monthly choice. A recurring task's due date is now always set automatically (at creation and, if it's ever somehow missing, by the nightly job), and each one keeps a log of which days it was actually completed vs. missed.
- **Tasks and Goals both got a read-first detail view.** Click a task's card (or a goal) to open a clean summary — category, due date, notes, tags, linked goal/asset, and for a recurring task a full calendar of its completion history — with an Edit button to make changes. Recurring-task history and a goal's own logged-metric history (weight, savings, anything tracked by hand) can be viewed as a month/year calendar or, for logged numbers, a trend graph — whichever reads better for what you're tracking. Calendar day cells now show the actual day-of-month number, so it's easier to spot a specific date at a glance.
- **Public demo instances now have real cost protection and a one-click "Try the Demo" account.** `DEMO_MODE` now forces every AI call onto a cheap model regardless of the configured provider model, so a demo can't rack up real inference costs. The demo login page's "Create Account" tab is replaced with a single button that generates a random guest account (no email/password) and drops the visitor straight into the app — everything resets nightly. Both are inert (no effect at all) on a personal or managed instance.

### Fixed

- **Push notifications now actually decrypt on the receiving device.** The Web Push payload encryption had a real key-derivation bug since it was first built — the push service itself always reported success (it only relays encrypted bytes, never decrypts them), but no device could ever actually decrypt and display the notification. Fixed the RFC 8291 key derivation to match spec.
- `VAPID_SUBJECT` (the contact address a push provider uses if it needs to flag a delivery problem) now defaults automatically to the domain already configured in Admin → Hosting, instead of requiring a manual `docker/.env` edit and restart.
- **Every scheduled job (morning digest, overdue alerts, weekly review, goal checks, and any custom AI-suggestion schedule) now actually fires at the configured local time.** They were silently running in the server's own system timezone instead of the configured `SCHEDULER_TIMEZONE` — invisible on a server already set to the right zone, but a several-hour miss anywhere else (the usual case: containers default to UTC).
- **A restart no longer waits until midnight to fix an overdue recurring task.** The nightly job that catches a recurring task whose due date slipped (and logs it as missed) now also runs once right after the app starts, instead of only at 00:01 local time — so recovering from a restart (or from the timezone bug above) doesn't leave tasks showing the wrong date/status for up to a day.
- **That boot-time catch-up now actually runs.** It (and four other startup jobs — business workflow sync, bank sync, the n8n status check, and the update-announcement recheck) never fired on any deploy, ever: each one computed its "run shortly after startup" time using the server's own raw clock reading mislabeled as the configured timezone, landing the job hours in the future instead of seconds. Fixed for all five.
- **A recurring task missed only once no longer skips an extra day when it resets.** It used to jump straight to tomorrow even though today itself was still a valid day to do it — now it correctly lands back on today.

### Security

- A push subscription's `endpoint` is now validated (must resolve to a public address over `https://`) before it's accepted, closing a server-side request forgery path where any authenticated account could point notification delivery at an internal-only address and have the server make outbound requests to it on every notification.

## [0.7.0] — 2026-08-30

### Added

- **App-wide search** (magnifying-glass icon in the header, or Ctrl/Cmd+K) — search your whole app
  from one place instead of hunting through each module separately: Tasks, Goals, Household/Team
  shared items, Contacts, Assets, Calendar, Finance transactions, Notes (including note content,
  not just titles), and Journal (including entry content). Filter by tag alongside a text search,
  and click a result to jump straight to it.
- **Tags**, previously only on Tasks and Goals, are now available on Assets, Calendar events,
  Finance transactions, Notes, and Journal entries too — sharing the same tag vocabulary across
  every module, so a tag you use in one place means the same thing everywhere, and it's all
  searchable from the new app-wide search above. Contacts' own tags field now uses the same
  pill-style picker as every other module instead of a plain comma-separated text box.
- **Goals now shows a real hierarchy** — matching Assets, subgoals collapse under their parent with
  a ▸/▾ toggle instead of every goal (parent and child alike) listing flat, and a goal's own linked
  tasks show right underneath it in the same tree, one level deeper.

- **Mod Store** (Admin → Mod Store): install and uninstall first-party LogCoreOS modules. Journal,
  Home Assistant, n8n Automation (renamed from "Automations"), Calendar, Household, Team, Notes,
  Assets, Contacts, and Finance are optional this way — none is a permanent core feature anymore, and a fresh install now ships
  without them by default; existing instances that already used one keep it installed automatically.
  Uninstalling a module never deletes its data — reinstalling picks everything back up untouched.
  Installing/uninstalling requires an admin-triggered restart to take effect (never automatic), with
  a warning if other users currently appear online. Tasks, AI Chat, and Dashboards are also now part
  of this same system, but shown as "Always active" — they're foundational enough that they can't be
  uninstalled. **Finance completes this list** — every module the Mod Store was ever meant to convert
  now has, and this is the last entry this bullet will ever gain.
- Calendar's household/team pool-events toggle (the 🏠/🧑‍🤝‍🧑 pill) now hides itself entirely when
  that pool module isn't installed and active, instead of remaining visible and silently doing
  nothing.
- **Goals is now a real, independent module** (previously just a special kind of Task) — install or
  uninstall it in Admin → Mod Store like anything else. Goals can now nest inside each other to any
  depth, link to as many tasks as you want, and track completion with a real progress bar instead of
  only ever being marked done by hand: pull a goal's percentage live from a Finance budget, from a
  number you track on your own Contacts profile (weight, or any other number), or from a running,
  dated log of manually-entered values against a target — subgoals and linked tasks still list
  underneath for organization even when a metric is driving the number. Due dates are optional now,
  no longer required. Deleting a goal with subgoals or
  linked tasks now asks what should happen to them (keep them, or take them with it) instead of one
  fixed behavior. You'll get notified the moment a goal's progress actually crosses 100%, and a
  goal that's stalled or running out of time now surfaces as its own distinct suggestion. Household
  and Team pool goals are supported the same way pool Finance books/Contacts/Assets already are.
- Goals can now be tagged, sharing the same tag vocabulary as Tasks — add a tag while creating or
  editing a goal or task, click any tag to filter the current list down to it, and pick from tags
  you've used before as you type a new one.
- Goals now has a dedicated Household/Team tab instead of merging pool goals invisibly into your own
  list — "ME" shows everything you personally own at any depth, and the pool tab shows your
  household's or team's goals, appearing only when that module is active for you.
- You can now link an existing goal as a subgoal, not just create a new one — search for a goal and
  move it under another, including re-parenting one that's already nested somewhere else.
- Track a weight goal against your own Contacts profile, with an Increase/Decrease toggle so a
  weight-loss goal actually reads as more complete as your weight goes down, not less.
- A goal linked to a recurring task now tracks real completion history instead of a simple done/not
  done check — its progress reflects how consistently you've completed that task over the last 30
  days.
- Linking a recurring task to a goal now lets you choose whether it counts toward the goal's own
  progress percentage or only shows its own completion rate for visibility — new links start as
  visibility-only until you turn tracking on, so you can link a task to a goal just to see how
  consistently you're doing it without moving the goal's percentage. Goals with recurring tasks
  linked before this change keep counting exactly as they always did.

### Fixed

- A dashboard's Household/Team pool-tasks block could show the wrong pool's data with no warning if
  the dashboard's own workspace was stale or mixed — closed by splitting the shared block into two
  workspace-specific ones that can no longer read the wrong pool at all.
- A user with AI Chat disabled could still read their own past agent tool-use run history through
  two endpoints (`GET /chat/runs`, `GET /chat/runs/{run_id}`) that weren't actually gated on the
  module. Chat's own conversation archives were also fully readable through the Brain file browser
  and the AI's own file-reading tools regardless of Chat's module state — both closed.
- **Compact density mode buried the AI Chat composer behind the fixed mobile bottom nav.** The
  compact-mode CSS rule for `<main>` used a shorthand `padding` that unintentionally overrode the
  reserved space for the mobile nav bar, on every page, for any user with Settings → Appearance →
  Density set to Compact — not just AI Chat, though the composer made it visible there first.
  Scoped the rule to only the sides it's meant to tighten.
- A user with Notes disabled could still list, read, create, update, delete, and move their notes
  through the AI chat, since none of the 7 note tools were actually gated on the module. Notes'
  archive folder was also fully readable through the Brain file browser and the AI's own
  file-reading tools regardless of Notes' module state, and its dashboard block (Note Embed) stayed
  visible in the block picker regardless of module state too — all three closed. A disabled user
  could also still search the *content* of notes shared with them (though not their own) via the AI
  chat's Brain search — closed the same way.
- A user with Dashboards disabled could still list, view, create, and edit dashboards (including
  adding/removing blocks and managing templates) through the AI chat, since none of the 10 dashboard
  tools were actually gated on the module — closed the same way as Chat's/Notes' own tool-gating gaps.
- A user with Assets disabled could still list, create, update, archive, move, search, and delete
  their assets and templates through the AI chat, since none of the 10 asset tools were actually
  gated on the module — closed the same way as Chat's/Notes'/Dashboards' own tool-gating gaps.
- A user with Contacts disabled could still list, create, and update contacts, log interactions, and
  create deals through the AI chat, since none of the 6 contact tools were actually gated on the
  module — closed the same way as Chat's/Notes'/Dashboards'/Assets' own tool-gating gaps.
- An admin with Contacts disabled for their own account could still edit Contacts' own custom-field
  definitions, since that endpoint (`PUT /contacts/fields`) was missing the module gate its own `GET`
  counterpart already had — closed.
- A user with Finance disabled could still list books/transactions, run reports, check budget
  status and balance projections, create invoices, add transactions, categorize transactions, and
  mark invoices paid through the AI chat, since none of the 9 finance tools were actually gated on
  the module — closed the same way as Chat's/Notes'/Dashboards'/Assets'/Contacts' own tool-gating
  gaps.
- An admin with Finance disabled for their own account could still manage every user's bank
  connections — claim, reveal, sync, disconnect, and the pool-level equivalents (13 endpoints in
  total) were gated by admin status alone, never the module itself — closed.
- A goal's own "+ Subgoal"/"+ Task"/delete-confirmation popups, and an asset's own linked-task
  quick-create popup, could render clipped or undersized when opened from inside another already-open
  modal — both now open correctly at full size regardless of nesting.
- Linking or creating a task from a household/team goal's detail view now correctly adds it to that
  pool's own tasks instead of silently creating a personal one.
- Searching for a task in the goal-linking picker could hide an exact-title match entirely once you
  had enough older tasks sharing a word with it — a fixed 8-result limit, applied before ranking
  results by relevance, could bury the one you were looking for. Results are now ranked so exact
  and best matches come first, and neither a search nor browsing the full unfiltered list cuts off
  at 8 anymore — scroll to see the rest either way.

### Changed

- Every module in the app has now been converted into this same self-contained format, including
  foundational ones like Tasks, AI Chat, and Dashboards (marked non-removable, not excluded) —
  journal, Home Assistant, n8n Automation, Calendar, Tasks, Household, Team, AI Chat, Notes,
  Dashboards, Assets, Contacts, and Finance are the first thirteen, and — as of Finance — also the
  last thirteen: no further modules are planned for conversion. Finance's own conversion is the
  first with more than one router file backing a single module (six, composed into one at the
  manifest level, since the module system's `get_router()` only ever supports returning a single
  router per module) — everything else about how a module plugs in stays exactly as it's always
  worked.
- Assets' admin-only n8n automation token reveal/rotate moved from inside the Assets module itself
  to Admin → n8n (now backed by `/auth/admin/automation-token`), so admins keep the ability to
  view/rotate it regardless of whether Assets is installed — Contacts' own separate automation API
  depends on the same token.
- Goals was the last feature in the entire app that couldn't be turned off — with it now a real
  module in its own right, there is no longer any single feature anywhere that can't be disabled per
  role or per user.

## [0.6.4] — 2026-08-22

### Security

- **Closed a critical SSRF gap in SimpleFIN bank-connection setup**: a claim URL decoded from a submitted setup token was accepted for any `https://` host with no domain allowlist, letting a malicious token point the server at an internal-only service. Now restricted to `simplefin.org` (and subdomains).
- **A crafted `javascript:`/`data:` link in AI chat content (e.g. echoed from a web search) could render as a clickable link** in the chat markdown renderer. Now only `http(s)`/`mailto`/in-app relative links render as links; anything else renders as inert text.
- **9 admin-facing endpoints (Home Assistant/n8n connection tests, n8n workflow sync, GitHub release check) no longer return raw exception text in their HTTP response** — full detail still goes to server logs.
- Added `permissions: contents: read` to the CI workflow (previously implicit/unscoped).
- Dependency bumps: `python-multipart` 0.0.18 → 0.0.32, `python-dotenv` 1.0.1 → 1.2.3, `pytest` 8.2.2 → 9.1.1 (+ `pytest-asyncio` → 1.4.0), `black` 24.4.2 → 26.5.1. Clears the GitHub Dependabot/code-scanning alert backlog aside from one CSV-import validation-message alert left as-is (deliberate, safe user-facing text about the user's own file, not a real leak).
- **The Infisical secrets cache and token file (`brain/_system/infisical_cache.json`/`infisical_config.json`) are now encrypted at rest**, closing the last open item from the alert sweep above. Only relevant to managed-hosting instances with Infisical connected — self-hosted instances never create these files. Requires a new `INFISICAL_CACHE_KEY` in `docker/.env` (auto-generated for fresh installs by `launch.sh`, auto-provisioned for existing ones on their next `update.sh` run); falls back to today's plaintext behavior with a one-time warning if it's ever missing, rather than failing to start.

## [0.6.3] — 2026-08-22

### Fixed

- **AI Chat on mobile: the composer could sit noticeably higher than the bottom of the screen, with empty space below it.** The page was reserving clearance for the mobile navigation bar twice over — once as part of the shared page layout, and again inside the chat page itself. Removed the duplicate; the composer now sits where it should.

## [0.6.2] — 2026-08-22

### Fixed

- **The AI Chat page could render with the whole app shell shifted upward and a dead gap at the bottom** — most noticeable with several modules enabled and a shorter browser window. Chat's auto-scroll-to-latest-message was scrolling more than just the message list; now scoped to only the container that actually needs it.
- **The sidebar's module list can now scroll on its own** when there are enough enabled modules to exceed the window height, so Settings/Help/Sign out stay reachable instead of potentially running off the bottom with no way to get to them.
- **Reopening a saved AI chat conversation from the business workspace no longer fails.** It was always looking in the personal workspace's folder regardless of which one the conversation was actually in. While fixing this, also closed a related gap where a personal-workspace request could read or write a business-workspace file directly by path.

## [0.6.1] — 2026-08-22

### Fixed

- **Fixed the actual reason both real deployed instances (the public demo and a managed-hosting client) had silently stopped auto-updating for over a week, and closed it permanently.** The 2026-08-14 CORS hardening release correctly made the app refuse to start with a wildcard `ALLOWED_ORIGINS`, with a shell-script self-heal (`migrate_insecure_cors()` in `launch.sh`/`update.sh`) that auto-derives a real origin from Admin → Hosting's configured domain. Both instances hit this exactly at the hardening commit: the new container crashed at startup, the health check failed, and `update.sh` rolled the whole working tree — including `update.sh` itself — back to the last commit before the self-heal function existed, so the fix could never reach them on its own. **The startup check itself now consults the same live domain the CORS middleware already trusts at request time** (`hosting_service.effective_domain_url()`) before refusing anything — a configured real domain makes the static env var moot, and when nothing is configured yet it falls back to a safe localhost-only default instead of refusing to boot, rather than bricking a fresh instance before its owner can even reach Admin → Hosting. This self-heals every currently-stuck instance automatically on its next update, no manual fix needed — see `docs/MEMORY.md` for the full mechanism.
- The FastAPI app's reported version (visible at `/docs` and in the OpenAPI schema) was hardcoded to `0.1.0` regardless of what was actually installed — now reads the same `installed_version.json` that `update.sh`/`launch.sh` already maintain.
- A flaky test (`test_transfer_leg_never_false_matches_a_recurring_bill`) hardcoded a date that aged out of its own assertion window as real time passed it; now computed relative to today.

### Added

- **Login and registration now link to the Privacy Policy and Terms of Service.**
- **`DEMO_MODE`** — a new, off-by-default instance flag for public demo deployments only. Shows a standing "this is a demo, data resets nightly" banner (with Privacy/Terms links), and is the required safety gate for a new nightly reset script (`demo_reset.py` / `docker/demo_reset.sh`) that wipes non-admin accounts — the script refuses to run at all unless this flag is explicitly set, so it can't be copy-pasted onto a personal or managed instance by mistake.
- `docker/.env.example` now documents using a Haiku model for `AI_MODEL` on a public demo, to control per-message AI cost.

## [0.6.0] — 2026-08-18

### Added

- **Tasks now show the due time next to the due date** on the task card, when one is set — previously only used for sort ordering, never displayed.
- **Dashboard action buttons can now have a color** — a small fixed palette (default/blue/green/red/purple/gray) in the block's config panel, instead of one fixed style for every button.
- **An open dashboard now picks up changes made elsewhere on its own** — polls every 45 seconds while the tab is visible, so a task or record created in another session shows up (with its buttons) without a manual reload.
- **Assets can now be created blank, without picking a template first** — mirrors the "start blank or from a template" choice Dashboards already had; a blank asset gets a name and notes only.
- **Every user's own contact is now permanently visible to their whole household and business team** — no separate "share my profile" step needed, and it's reachable from either workspace, not just the one it lives in. A new contact you create now defaults to shared with your household/team too, with a "keep this personal" option if you'd rather it stay private to you. Any contact can also be flipped to show up in your other workspace as well (one real record, not a copy) via a new toggle in the contact editor.
- **Admins can now link a new user account to an existing household contact when creating it**, instead of always starting that person's profile from scratch — picks up their existing contact info as their profile.
- **A small green/red dot now shows whether a household or team member is currently online**, on their contact card and in the contacts list — click their photo for exactly how long ago they were last seen (minutes for the first hour, hours for the first day, days after that).
- **Assets started without a template can now have their own custom fields** — a "Custom fields" section lets you add your own label/value pairs directly, no template required.
- **A personal contact can now be converted into a shared household/team contact**, from its edit screen — and a new bulk action on the Contacts page converts many at once, with a checklist to include or exclude specific ones (defaults to everything selected).
- **A blank asset's custom fields can now be typed, not just plain text** — pick from the same six field types (text, number, date, yes/no, dropdown, contact) the admin Template editor uses, right on the asset itself. A new "Save as template" button turns those fields into a real, reusable template and switches the asset over to using it.
- **Core Values on a contact are now pill entries** you add one at a time, instead of a single field you had to comma-separate by hand.
- **Career history can now include a past role added directly**, with its own start and end dates, not just by ending your current role and starting a new one — past roles can also be edited after the fact, and the list now sorts with the most recent past role first.
- **Your own profile's sensitive sections can now be hidden from your household or team**, section by section — Values & Principles, Family, Career, Address, Personal, and Priorities each get their own "Hide from others" toggle, visible only to you and settable only by you.
- **Dashboard blocks can now have their card background and header toggled on or off**, individually, from the block's own config panel — both default on. The AI can also set these when building or editing a dashboard on your behalf.
- **A dashboard can now be flagged to show up in both your personal and business workspaces**, instead of only the one it was created in — a "Also show in my [other workspace] workspace" toggle in Dashboard Settings, for anyone with both workspaces. Off by default, so nothing changes unless you turn it on for a specific dashboard.
- **Reopening the Dashboard module now returns you to whichever dashboard you had open last**, as long as it's been less than 30 minutes — switching back and forth between dashboards (or workspaces) no longer resets you to the default every time.
- **You can now pin your favorite modules to the desktop sidebar**, the same way mobile already lets you pin shortcuts to its bottom bar — same settings screen, same list, just also shown on desktop now.
- **Household and Team can now connect a joint/family bank account directly to the pool** — Settings → Admin Settings → Household/Team → Bank Connections → "Connect a joint family account". This is a real SimpleFIN connection owned by the pool itself, not tied to any one member's own connection, for accounts that genuinely aren't one person's. Admin-only to set up (no request/approve handshake needed), with the same connect/reveal/sync/disconnect controls and account-mapping UI members already get for their own connections — feeding straight into this pool's own books. Included in the regular background sync alongside every member's own connection.
- **Finance now has a real Transfer type**, alongside Expense and Income. Moving money between two books — including between your personal and business books, if you have both — no longer has to be logged as a fake expense in one and a fake income in the other; pick "Transfer," then a source book/account and a destination book/account (same currency required — no FX conversion yet), and both sides are created together and stay linked as one unit. A transfer shows with a ⇄ badge and the other side's book/account name instead of a category, is edited or deleted as one unit from either side, and — the actual point of the feature — never counts as income or expense in Monthly Reports, P&L, or budget spent-so-far totals, so moving money between your own books no longer inflates either number. Editing or deleting one side directly, outside the Transfer flow, is blocked to keep both sides in sync. Same-book transfers between two of your own accounts work the same way.
- **Contacts now sorts alphabetically by name with an A-Z jump strip** beside the list, making a long contact list much faster to search. **Company contacts now show different fields than person contacts** — no more gender, pronouns, or career history on a business card. Companies get Locations (one or more addresses) and Hours (open/close per day of the week) instead; the "Family" section is relabeled "Affiliated People" for a company and drops the marital-status/pets fields (the link-a-related-contact feature itself still works the same for both). Your own profile can no longer be switched to a company, through the edit form or a direct API call — it stays a person. **Company contacts can now have their own custom fields, too** — Settings → Admin Settings → Contact Fields is a new screen for defining extra contact fields (previously only reachable through the API, with no in-app way to create one), and each field can be scoped to show on person contacts, company contacts, or both.
- **AI Chat now runs in the background and supports real multiple conversations.** Sending a message no longer blocks the screen — the reply is saved the moment it's ready regardless of whether you're still watching, and you get a notification either when it finishes or when it needs your approval. The "Chats" button now opens straight into a conversation on click (no more preview-then-Continue step), and each row shows a live dot for one still generating and a bolder unread mark for one that finished or needs input while you were elsewhere. Switching to a different conversation — or starting a brand new one — no longer waits on whatever the previous one was doing; both keep working independently. Notification bell taps land you straight in the right conversation.
- **Dashboard blocks can now have their own buttons.** Add one or more small buttons directly onto a Tasks, Assets, Contacts, Notes, or Events block instead of cluttering the dashboard with separate standalone action blocks for every single action — an "Open" button per row jumps straight to that record, and task/asset blocks also offer one-click status buttons (Mark Done/Pending/Skipped, Archive/Unarchive). Configure them from the same block-edit panel every other block setting already uses. New **Contacts List** block type, for a plain list of your visible contacts — there wasn't one before. The Tasks dashboard blocks (Top 3 Tasks, Due Today) also gained a "Sort by" option (Priority, Date/Time, Alphabetical), matching the standalone Tasks page.
- **Finance now remembers the last book you had open**, per workspace, so reopening Finance takes you back to where you left off instead of always defaulting to the first book. A `?book=` link (from a notification, for example) still always wins.
- **The AI can now see where every block on a dashboard actually sits, and move or resize an existing one accordingly** — ask it to make something bigger, move something out of the way, or tidy up the layout, and it can now do that directly instead of only ever adding blocks to the bottom. New blocks still always stack at the bottom by default.
- **AI Chat notifications are now quieter when you're already watching.** A conversation that finishes or needs your input no longer also pings/badges you if you're still sitting right there looking at it — the notification only fires once you've actually stepped away.

### Changed

- **The Settings screen's Shortcuts row is no longer mobile-only** — since it now also configures the new desktop sidebar pins, it shows on every screen size.
- **Frontend build tooling modernized: ESLint 8 → 9 (flat config) and Vite 5.4 → 8.** No user-visible behavior change, but closes a real gap: CI's lint step (`eslint src/`, no `--ext` flag) had been silently checking only the project's 6 `.js` files and skipping all 92 `.jsx` files — effectively the entire React component tree — since ESLint 8's directory default only walks `.js` unless told otherwise. Flat config (required by ESLint 9+) matches files by explicit glob instead, which fixes this as a side effect of the migration. Fixing it for real surfaced 64 previously-invisible issues (mostly unescaped quote characters in JSX text, a few real dead-code/stale-comment cleanups, and some deliberately-scoped `useEffect` dependency arrays now documented inline); all fixed or, where blindly "fixing" a dependency array risked changing real behavior (e.g. an intentional mount-only fetch), left as-is with an explanatory suppressing comment. `react/prop-types` is now explicitly off — never adopted anywhere in this codebase's ~90 components, an established convention rather than oversight. `launch.sh` now checks the actual Node version (not just that `node` exists) before building, since Vite 8 requires Node 20.19+/22.12+.
- **Tasks no longer groups tasks by category with a header and gap above each group** — every task (including ones assigned to you from a shared pool) now sits in one flat, ranked list. A new "Sort by" control above the list switches between Priority score (default), Date/Time, and Alphabetical; your choice is remembered. Priority mode now genuinely ranks every task against every other one regardless of category — a High-priority Family task correctly outranks a Medium-priority Religion task instead of the two only ever being compared within their own category group.

### Fixed

- **An AI Chat message could be lost if you navigated away within 5-10 seconds of sending it.** The user's message was only written to the saved conversation *after* the AI's reply finished — if the request failed or you left too soon, it was never archived at all. It's now saved to the conversation the instant it's sent, before the AI is even asked to respond.
- **The dashboard block-button color picker was unreadable** — a dropdown showing color names crowded out the button-label field next to it in an already-narrow row. Replaced with a small color swatch that opens a compact picker, freeing the label field back up to its full width.
- **The "Thinking…" indicator in AI Chat disappeared if you reloaded the page (or reopened the conversation) while the AI was still working**, even though it genuinely was still working — the indicator only ever lived in that browser tab's own memory, with nothing to bring it back on reload. Reopening a conversation that's still running now shows it again and updates automatically once the reply is ready.
- **A blank (no-template) Asset couldn't be saved again after creation** — any edit failed with a confusing "Template not found" error, because the backend couldn't tell "no template at all" apart from "the template used to exist and was deleted." Fixed as part of adding custom fields to blank assets above.
- **There was no way to delete a contact anywhere in the app** — the delete function always worked correctly on the backend, but no button anywhere in the interface was ever wired up to call it. Added to the contact editor, with the same permission rule Assets already uses: you can delete your own contacts, but a shared household/team contact needs an admin.
- **The online/offline dot could stay wrong for as long as the Contacts page was left open.** It read correctly the moment the page loaded, but Contacts never refreshed itself afterward, so it could keep showing someone as offline well after they came back online. Contacts now quietly refreshes itself every minute while the tab is visible, the same way the Dashboard already does.
- **The last-seen popover could open half off-screen** — it anchored from the photo's right edge, running off the left side of the window for contacts near the left of the list. It now opens toward the right instead.
- **The last-seen popover could still be partially hidden behind the contact below it in the list**, even after the previous fix — a background blur effect on every contact row was quietly creating its own stacking layer, so the row underneath could paint over the popover regardless of which side it opened on. Fixed by raising the open row above its neighbors while its popover is showing.
- **Dashboard block buttons didn't consistently line up on the right side** — some did, some sat flush left, depending on which block type. Buttons now always align to the right, everywhere.
- **The Top 3 Tasks dashboard block's buttons could still sit flush left**, even after the fix above — a different, second cause specific to that one block's row layout. Now aligns right like every other block.
- **Opening the Dashboard module showed a "Dashboard not found" error the very first time, every time** (not when picking any other dashboard afterward) — a loading bug caused the page to check for a dashboard twice in a row, and the second check could run before the URL had settled. Fixed.
- **Switching workspaces while a dashboard was open could leave the previous workspace's dashboard on screen**, or fail to load a valid one for the new workspace, instead of reliably loading the right dashboard (or the default) for wherever you just switched to.
- **Typing in the "Add core value" field, or entering options in an Assets blank custom field, zoomed the page in slightly** on mobile — an iOS quirk triggered by that input rendering a touch too small. Fixed, along with two other inputs found to have the same issue while checking.
- **A blank asset's custom fields didn't show up anywhere outside of edit mode** — they saved correctly and the editor showed them fine, but the read-first view never displayed them at all, including any contact-type field's name or its quick status control.
- **A team dashboard created by asking the AI in chat immediately showed "Dashboard not found," including for whoever just created it** — found while investigating the issue above; the AI's dashboard-creation tool was saving a team dashboard to the wrong internal location. Never affected household dashboards, or anything created through the Dashboard page itself.
- **A newly created custom feature role (Settings → Admin Settings → Users & Roles → Role Definitions) could fail to save further changes or assign to a user right after creation.** Role names are stored lowercased and trimmed (e.g. "Cleaner" is stored as "cleaner"), but editing, deleting, or assigning the role using the as-typed casing shortly after creating it was rejected as "not found." Role lookups are now case/whitespace-normalized everywhere a role name is used, and the Role Definitions page uses the server's saved name instead of its own local copy.
- **Tasks and Goals due today could show a red "OVERDUE" badge hours before they were actually due** — as early as 7 PM local time (6 PM in winter), not midnight. The badge compared each task's due date against a "today" computed from the browser's UTC clock instead of local time, so it silently rolled over to tomorrow's date partway through the evening for anyone west of UTC. Now uses the same locally-computed date the rest of the page already used correctly.
- **`GET /finance/networth` no longer blends balances from books in different currencies into one meaningless total.** A user with both a USD book and a EUR book previously got a single summed number with no currency attached; the response now reports a total per currency (`totals_by_currency`) instead. Not currently surfaced in any UI (no Dashboard block reads this endpoint yet), so this only affects direct API/automation callers today.
- **The Notes "···" menu (rename/move/share/archive/delete) no longer opens off to the side of the sidebar** — it now opens centered on screen (a bottom sheet on mobile), matching every other menu/dialog in the app. Every other Notes dialog (new note/folder, rename, move, delete, share) was also moved off Notes' own one-off popup style onto the same app-wide dialog style everything else already uses, so Notes now looks and behaves consistently with the rest of the app.
- **The AI chat agent can now see and work with notes shared with you** — from another person or a household/team pool — not just your own. It previously could only find, read, edit, or create notes in your own personal notes, so asking it for help with a shared note failed as if the note didn't exist. It now respects the same read/contribute/edit access levels a person gets on the Notes page: it can find and read anything shared with you, but only edits or deletes a note if your access level actually allows it, and says so plainly if it doesn't.
- **After the on-screen keyboard opened and closed, taps could land noticeably above whatever you were actually trying to tap** — the page content visually snapped back to its normal position, but the browser's touch/scroll coordinates stayed mapped to the keyboard-open layout. The page now resizes instead of just panning when the keyboard opens, plus a backstop that forces the scroll position back when the keyboard closes. Could not be verified on a real device in this environment — flagged for on-device confirmation.
- **Attachment images now open in a full-screen viewer instead of a new browser tab** — both on an asset's own page and in the dashboard's Documents block (one shared component, one fix covers both). Other file types (PDFs, etc.) still open in a new tab as before. The viewer now also opens truly centered and full-screen (it previously got trapped inside its own small thumbnail card on some pages, and a square/non-tall image sat in the bottom half of the screen on mobile).
- **AI Chat now actually reopens your last conversation** — including after switching between personal and business workspaces, which previously always landed on a blank new chat instead of that workspace's own last one.
- **A paused approval/question/plan card no longer disappears when you leave and come back to a conversation.** Reopening a chat that was waiting on you previously showed the AI's prompt text ("I need your approval to make these changes...") with no way to actually act on it — the Approve/Deny buttons, the question's answer options, and the plan's confirm/cancel were all gone, and the only way forward was starting over. They now reload correctly.
- **Fixed a real crash: approving a card in AI Chat could permanently break that conversation**, with every message afterward failing with an "unexpected role" error. Approving, declining, or answering a question silently corrupted the saved conversation the first time it happened; the very next time that conversation reloaded (switching workspaces and back, reopening the app), sending any further message in it failed outright. Both sides of the bug are fixed — new conversations are unaffected, and existing broken ones repair themselves the next time you send a message in them.
- **Fixed a second real crash: asking the AI to move or resize a dashboard block could crash the whole Chat page**, and once it did, that conversation crashed again every single time it reopened (including automatically, since Chat reopens your last conversation) — there was no way back into it except starting a new chat. The approval-preview card for a block move/resize had a bug that made it fail every time a position or size change was actually proposed. Also hardened AI messages generally against crashing on an empty reply (a turn that's a pure tool call with no accompanying text) instead of just rendering blank.
- **Finance transfers no longer auto-open the on-screen number keyboard when you switch to "Transfer"** — the Amount field's autofocus (intended for quickly typing an Expense/Income amount) was staying active and covering the book/account picker fields you actually needed next.
- **Deleting a Finance transfer between two accounts in the *same* book now actually removes both sides** — it previously only removed one, silently leaving the other behind. (A transfer between two *different* books already worked correctly.)
- **Push notification failures are now diagnosable instead of a generic crash.** A malformed or expired push subscription could previously escape as an unhandled server error with an opaque, misleading client-side message (worse on Safari specifically). `POST /push/test` now reliably returns its intended distinguishable error (400 vs 502) in every case, and any other unexpected server error now returns a real, readable message instead of a cryptic one.
- **Notes and Journal no longer zoom the whole page in when you tap into the editor on mobile** — you previously had to manually pinch back out to see the full screen again. The editor text was rendering slightly smaller than the size mobile Safari requires to avoid its automatic zoom-on-focus behavior.
- **The on-screen keyboard opening no longer causes a visible double-jump or a repeated auto-scroll-down.** Traced to a viewport setting change that was never actually released — reverted it and the extra correction code layered on top of it back to how keyboard handling worked before.

### Security

- **Two real bugs found and fixed while moving self-contacts into the shared household pool, both about who counts as "the owner" of a profile record.** A profile's private fields (health, schedule, finances, AI preferences) were always meant to be visible only to their own owner — that check used to compare the record's storage location to the viewer's name, which stopped working correctly once profiles moved into a shared pool location. Left alone, this would have made users unable to view or update their own private profile fields (a functionality bug), not a data leak to others — the protection against *other* household/team members seeing this data was never affected and has been directly verified with new tests, from both the household and business-team side.
- **Frontend dev-server advisory closed**: the Vite 5.4.x line couldn't reach a fix for a residual esbuild dev-server advisory (`GHSA-67mh-4wv8-2f99`) without a breaking major bump. Vite 8 closes it. Dev-server-only — production always served from the pre-built `dist/` — so real-world risk was already low.
- **Brain export no longer bundles the SimpleFIN bank-access URL.** `GET /user/export` zips a user's entire Brain folder, and a connected bank's read-only access URL lives inside it at `Finance/simplefin.json` — meaning a self-export let a user pull their own bank credential out through a side door, bypassing the admin-only-reveal design (normally rate-limited and only ever output by a dedicated admin endpoint). Excluded the same way `push_subscription.json` already was.
- **A user without business-workspace access could no longer self-serve unlock it by sending an `X-Workspace: business` header.** The header was only checked for being a literally valid value, never against the admin-controlled `workspaces` grant on the account. Impact was bounded to the user's own directory (never another user's data), but it bypassed a real admin-set boundary. Every endpoint that reads the workspace now gets the already-entitlement-checked value.
- **The server now refuses to start with `ALLOWED_ORIGINS` set to `"*"`** (previously just a log warning), matching the existing refuse-to-start behavior for a placeholder `SECRET_KEY`. A wildcard CORS origin combined with credentialed requests lets any website read authenticated API responses through a visiting user's browser. Local development can still opt in via `ALLOW_INSECURE_CORS=true`. **Note for self-hosters:** if your instance still has the old `ALLOWED_ORIGINS=*` default from before this security pass, it will refuse to start on the next restart/update until you set a real origin (or the escape hatch) — see `docker/.env.example`.
- **The `ALLOWED_ORIGINS=*` refuse-to-start guard above now fixes itself on affected instances instead of just going down.** `launch.sh` and `docker/update.sh` both auto-migrate a leftover `*` value to the real domain already on file in `Admin → Hosting` (`brain/hosting.json`'s `domain_url`) before starting/updating; if no domain is on file yet, they now print the actual cause and fix instead of a generic health-check timeout. Found the hard way: an existing instance relaunched for the first time since the guard above shipped and went down with no clear signal why. The auto-updater's existing rollback-on-failed-health-check already kept instances from actually going down mid-update, but silently re-installed the same old pre-hardening version forever rather than landing the real update — this closes that gap so updates actually land. One caveat: an instance already stuck in that rollback loop needs one manual `git pull && bash launch.sh` (or a one-line `docker/.env` edit) to break out, since the fix itself has to land before it can apply.
- **Fixed a real, demonstrated data-loss bug**: two concurrent requests updating the same user's tasks could silently lose one side's change (confirmed: 20 simultaneous updates against a test file landed as 1). `services/task_service.py`'s writes now go through a proper atomic read-modify-write helper instead of separate read-then-write calls with a race window between them.
- **Deleting a custom feature role now shows who's actually assigned it** ("1 user currently has it — Bob Worker") instead of a generic "users will fall back to member" message, so an admin isn't guessing at the blast radius before confirming.
- **`react-router-dom` bumped 6 → 7 (`^7.18.2`), closing a moderate `npm audit` finding** (open redirect via a backslash-prefixed path in `<Link>`/`useNavigate`, range `6.0.0–7.17.0`). Checked whether this app actually has a reachable path to it: every dynamic navigation target in the codebase is built from an internal template (record ids, route paths) or literal string, never an attacker-controlled full URL or raw redirect query param, so there was no live open-redirect surface here — this closes the audit finding rather than a working exploit. The app only uses React Router's stable declarative API (`BrowserRouter`/`Routes`/`Route`/`Link`/`useNavigate`/`useSearchParams`/`useLocation`/`useParams`) and none of v7's data/framework-mode APIs, so the upgrade needed no route or navigation code changes.
- **Web Push notifications get better diagnostics.** Investigating a report of push notifications not arriving found that Web Push was already fully implemented and already firing for nearly every notification type — not missing. The default VAPID contact address is a placeholder, not a real one, which some push services may reject or deprioritize; it's now a documented, configurable `VAPID_SUBJECT` setting. `POST /push/test`'s error message now distinguishes "no subscription on file" from "a subscription exists but the send itself failed," instead of one generic message that made real diagnosis impossible without server log access.

---

## [0.5.0] — 2026-08-10

### Changed

- **AI Chat has a sleeker, clearer look.** Assistant replies now render real formatting — bold, italic, inline code, code blocks, headings, lists, and links — instead of showing raw markdown symbols. The message box auto-grows as you type instead of staying a single line (Enter sends, Shift+Enter starts a new line). The three separate memory icons are now one "Memory" pill that opens a popup with the short-term/long-term memory links and the cross-workspace toggle, each with a short description. The mode selector, usage badge, Memory pill, and message box now sit together in one bordered composer instead of a loose row of controls. Pending-approval cards now look different depending on what they're asking instead of one orange treatment for everything: a clarifying question is blue, a dashboard-change preview is neutral, and an actual proposed change or plan stays orange. New messages and cards fade in, and the "thinking" indicator is now a shimmering label instead of three bouncing dots.
- **Profile is no longer a separate form — it's your own Contact.** Every user now has one self-contact (marked as "yours," pinned to the top of your Contacts list labeled "ME") that IS their profile: the same read-first card every other contact uses, with an Edit button instead of an always-open form. It's a single record shared across both personal and business workspaces (the one place Contacts intentionally isn't split per workspace), except Life Priorities, which still has its own personal/business lists. Health, finances, and AI-preference fields on your profile are always private — they never become visible to anyone you share your contact with, no matter what access level you grant, and nobody but you can ever be granted edit access to your own contact at all (others can still be given read/contribute access to see basic info or log interactions). The embedded Goals list and the "Big Long-term Goal"/"Savings Goal" text fields are gone from Profile (Goals was always redundant there — use the Goals page). Family fields (`partner`/`children`) are now real linked contacts instead of free text, shown on both sides of the link. Your own profile now opens as a full page (there's a lot more on it than a typical contact); everyone else's contact — including a self-contact someone shared with you — still opens in the compact card. Existing profile data is migrated automatically on next update; nothing is deleted.
- **Every contact — not just your own — now has a compact, easy-to-read profile card** with an Edit button, instead of the previous plain field list. Contacts can now be filtered to just people or just companies.
- **Work & Career is now a real resume**, not a handful of flat fields — add a role with employer (pick an existing company contact or create one), industry, education level, years of experience, and skills; "Archive this role & start a new one" closes it out with an end date and opens a fresh current role, keeping your past roles listed below.
- **Height, weight, and blood type are now pickers** instead of free text — height supports feet/inches or centimeters, weight supports pounds or kilograms, and blood type is a fixed list. Daily Routine's four time fields are now real time pickers, and Work Hours is a start/end pair.
- **Contacts and your profile can now have a photo**, shown at the top of the card in place of the default icon. Added a Gender field (male/female) that also picks a more specific default icon when no photo is set.
- **Phone numbers now support a country code and extension**, and multiple numbers per contact format themselves as you type. Emails are now validated — an invalid address won't save.
- **Journal redesigned to match Chat's layout**: the page itself no longer scrolls — only the entry text box does, so the date navigator and Save button stay fixed on screen instead of drifting off with a long entry. The date navigator, editor, and Save button are now one seamless panel instead of separate boxes with gaps between them. "History" now opens as a slide-in panel (matching Chat's saved-chats drawer) instead of an inline list that pushed the rest of the page down.

- **Settings and Admin merged into one drill-down menu — the standalone Admin page is gone.** Settings is now a menu of icon+label rows (Profile, Appearance, Notifications, Shortcuts, Account, and an admin-only "Admin Settings" row); every row opens its own dedicated page instead of an always-expanded card. Admin Settings is the same pattern one level deeper: Users & Roles, AI, General, Team, Household, Hosting — each its own page, reorganized by the part of the app they configure rather than by setting type. Users & Roles drills further: tap a user for their own full page (role, feature role, workspace access, pool-management grants, module overrides, and their bank connection), or open Role Definitions for the custom feature-role editor. The `/admin` and `/admin/ai-usage` routes are removed with no redirect — bookmarks to them will land on the dashboard; use Settings → Admin Settings instead.
- **Session length is now a single instance-wide setting, not a per-user choice.** Admins set it once in Settings → Admin Settings → General; it applies to every login going forward (existing sessions are unaffected). The per-user session-length picker in Settings is gone, along with the `PATCH /auth/session` endpoint.
- **Team and Household admin pages show a read-only bank-connections summary** — which members currently have a SimpleFIN account mapped into that pool's books — plus a "coming soon" section for connecting a business/joint account directly to the pool (not tied to any one member's own connection). That direct pool-level connection is UI-only for now; the backend for it is tracked as a follow-up.

### Added

- **The AI can now build and manage your Dashboards directly from chat** — create a dashboard, add/update/remove blocks, and create or edit dashboard templates, using the exact same search-based pickers and grid rules the Dashboard page itself uses. Changing a template shared instance-wide always comes with a plain-language warning stated in the chat, since every dashboard built from it updates immediately. When the AI proposes adding or changing a dashboard block, you now see a live preview of your actual dashboard with the change applied, right in the chat, before you approve it.
- **The AI can now ask you a clarifying multiple-choice question mid-conversation** instead of guessing when something's ambiguous — pick one or more options right in the chat and it continues from your answer.
- **Approving (or declining) an AI-proposed change is now guaranteed to do exactly what was shown** — previously, clicking Approve re-asked the AI to decide what to do from scratch, which could occasionally differ from what was actually reviewed. The same fix applies to confirming a proposed plan in Plan mode.
- **Custom Dashboards** — the fixed Dashboard page is replaced with an unlimited, build-it-yourself dashboard system. Create as many dashboards as you want, each a freeform grid (desktop) of blocks pulling live data from almost every module: tasks, goals, streaks, Smart Home, Household/Team, Calendar, Finance, Contacts, Assets, Notes, Journal, Automations, and your own AI usage/recent activity — plus plain text, links, and headings for organizing the layout. The grid is fine-grained — place a block at almost any point and resize it in small increments, including snug side-by-side with another block, without other blocks jumping around when you drop or resize one. Linking a block to a specific task, contact, asset, calendar event, finance book, note, or automation workflow is done by searching and picking it from a real list, never by typing an internal ID — and a block's link can be changed later from its own "✎" edit button without deleting and re-adding it. Share a dashboard with another person or your household/team pool at read, contribute, or edit level; an optional owner-only toggle lets you share the underlying data too, so someone you've shared with sees exactly what you'd see — never more. Your existing dashboard becomes your first "Home" dashboard automatically; your last remaining dashboard in a workspace can't be deleted, so there's always a landing page. "Referenced by" jump-links back from other modules, admin-only usage-analytics blocks, and external data sources (weather, RSS, etc.) are still on the way. A "⚙ Settings" button while editing now consolidates renaming a dashboard, changing its icon, sharing, setting it as default, and deleting it in one place — previously a loose row of buttons that could overflow awkwardly on narrow phone screens. The block resize handle is also now a clearly visible accent-colored corner mark instead of a barely-visible default icon. Sharing a dashboard now offers a real dropdown of household/team members and roles instead of a plain text box, matching every other module's sharing UI. Fixed a real bug where the dashboard grid could get stuck using a narrow 2-column mobile layout on a normal desktop window instead of the intended fine-grained grid. **Dashboard editing — including drag and resize — now works fully on mobile**, with its own independent block arrangement from desktop (the same dashboard can look different, on purpose, on a phone vs. a laptop). Two new block types: **Navigate To…** (a button that jumps to any page — including a specific section or tab within Finance, Automations, or Settings — or a specific task/contact/asset/event/note/finance book/dashboard) and **Status/Archive Action** (a one-click button that marks a task done/pending/skipped, updates a contact's gender or marital status, or archives/unarchives an asset or sets one of its own fields) — every option in both is picked from a real list, never typed, and a custom button label you type now actually shows up on the button. Both now render as a small standalone pill button with no card or label around it, so several fit edge-to-edge in a small space. **Moving a block on mobile now requires a brief press-and-hold before it starts following your finger** — a quick swipe over a block scrolls the page like normal instead of grabbing it, matching how the resize handle already worked. **Removing a block now asks you to confirm first**, instead of deleting it the instant you tap "✕". **Every block's own name/icon label is now edit-mode only** — dashboards look cleaner in normal view, with the label reappearing only while you're arranging things. The Documents/Attachments block now shows real image thumbnails and clickable file previews instead of a plain filename list. A few record-linked block names were tweaked to say where their data actually comes from (e.g. "Contact's Deals", "Asset's Linked Contact"). **Dashboard Templates have arrived** — build a reusable block set once (optionally tied to "a contact" or "an asset" as its subject, e.g. one dashboard template per client), then create as many dashboards from it as you need; editing the template's blocks updates every dashboard made from it automatically, while each dashboard's own layout (position/size) stays yours to arrange independently. Templates are entirely optional, not a requirement to make a dashboard, and mirror Assets' own template system: admins manage global templates for everyone, and anyone can also build and share their own personal ones. A "Detach from template" option lets any dashboard become fully independent later if you need to customize it beyond what the template allows. The dashboard switcher and the "Navigate To…" button's dashboard picker both now group dashboards by their template — handy once you have a large number of them, e.g. many per-client dashboards — with an "Other" section for dashboards not made from a template. **A dashboard with a subject now shows who or what it's about** — an identity banner with a photo/icon and name sits above the blocks automatically. **Blocks now look like what they actually are** instead of every single one being an identical box — a plain list of items no longer sits inside its own bordered card. A new **Collection** block shows a whole list (or a status-grouped board) of records at once — any asset template, optionally narrowed to just the ones linked to the dashboard's own contact — with a one-click status control per item wherever the template has a status-style field, and a Count-only mode for a simple "how many" tile. "+ Add Block" now has a search box so the growing catalog stays easy to scan.
- **AI usage counter + caps** — Settings → Admin Settings → AI shows instance-wide, personal, and business AI usage (messages + input/output tokens), plus a per-user table with each user's live status. Admins can set a global default message/token limit (with per-user overrides) and, per user, pick a cap period (daily/weekly/monthly) and a mode: **off** (unlimited, the default), **soft** (warns, requires an explicit "Continue anyway?" confirmation in Chat once over), or **hard** (blocks the AI outright until the next period or a raised limit). A live usage-percentage badge also appears in the Chat toolbar. Automation (n8n) AI usage is not tracked — it's architecturally invisible to the backend when a workflow holds its own provider credential.
- **Notes can now be archived** — a "Show archived" toggle and Archive/Unarchive action, matching Assets/Finance/Contacts (the one module that didn't have this yet). Archiving a folder cascades to everything inside it (same rule as sharing a folder) and is purely organizational — it has no effect on delete permissions.
- **Deleting a user with shared items now opens a review page instead of a blind confirm.** If the user owns anything already shared with someone else (an Asset tree, Finance book, Contact, or shared Notes folder), Settings → Admin Settings → Users & Roles → a user → Delete User now opens a review page listing every such item; the admin must choose, per item, to transfer it to another user, transfer it to the workspace's household/team pool, or delete it outright, before the account can actually be removed. Existing shares to other people survive a transfer unchanged; transferring to a pool converts those shares into the equivalent pool-contributor grants so they keep working. A read-only section also shows what the departing user will separately lose access to elsewhere. Users with nothing shared still delete instantly, same as before.

### Fixed

- **Adding, editing, or removing a Dashboard block no longer kicks you out of Edit mode.** Previously, every single addition silently returned you to view mode, hiding the toolbar and every block's edit/remove buttons until you clicked "Edit Dashboard" again.
- **The bottom of most pages was hidden behind the mobile footer nav** — nearly every Settings page (and Assets, Automations, Finance, Goals, Help, Home, Team, and the Brain file list) was missing the bottom clearance that Contacts and a few other pages already had. Also hardened the app against the whole page scrolling as one block instead of just the content area — the app shell (sidebar, header, footer) should now stay locked in place no matter what, on every page.
- **The file editor (Brain) and note editor (Notes) could grow taller than their allotted space on mobile**, which could push their own scrolling out of the intended container. Both now size correctly.
- **The new Custom Dashboards page was missing the same mobile bottom clearance** other pages have.
- **Admins couldn't edit, rename, move, share, or delete Notes shared into the household/team pool** — the note/folder context menu treated any pool item the same as a note someone personally shared with you, hiding every management action and offering only "Leave" (which doesn't apply to pool items). Admins can now manage pool notes the same way they already could pool Assets, Finance books, and Contacts.
- **Deleting a user could leave dangling references to them in other people's/pools' share lists and stale derived share-index caches.** The Brain folder itself was already fully removed on delete, but their name could linger in other users' `shared_with`/`contributors`/`hidden_from` entries indefinitely. Deletion now always scrubs every reference to the departing user from every other store as part of the same operation.
- **The last contact in the list was hidden behind the mobile footer nav.** Added bottom clearance so it's always fully visible.
- **The contact editor scrolled sideways.** A single modal-wide fix (no element inside a modal can force horizontal scroll anymore).
- **Linking an affiliated contact ("+ Link") silently did nothing until you closed and reopened the editor.** The link was actually saved immediately — the new pill just failed to appear, so it looked like you had to save all your other edits and go back in to add another one. Fixed.
- **Your own full-page profile and a contact's full-page edit view could hide their own Save/Cancel buttons behind the mobile footer nav**, requiring a manual scroll to reach them. Added the same bottom clearance the contact list already had.
- **Contact photos didn't show up in the Contacts list** — only in the full detail view. They now display everywhere a contact appears.
- **Weight entered in pounds was saved as if it were kilograms** (e.g. entering 155 lbs displayed back as 342 lbs) — the weight field always stores kilograms internally and converts for display, but the editor wasn't converting your typed number into kilograms first when "lbs" was selected. Fixed; if you entered a weight before this fix, open your profile's Edit page and re-enter it once to correct the stored value.
- **Weight drifted by a pound or two on round-trip** (155 lbs would come back as 154) — height/weight conversions were rounded to a whole number on both save and display, and rounding twice compounds. Weight now keeps 1 decimal place throughout.
- **The bottom of Tasks, AI Chat, Journal, Calendar, and Household was hidden behind the mobile footer nav** — the same gap already fixed on Contacts. Each now has the same bottom clearance.
- **On the installed iPhone app, the entire screen (including the top header) could scroll as one block instead of staying put while only a page's own content scrolled** — a long-documented iOS quirk where hiding page overflow isn't always enough to stop the whole screen from dragging. Locked the app shell down so only the intended content area moves.

## [0.4.4] — 2026-07-30

### Fixed

- **Mobile footer nav floating above the true screen bottom on the installed PWA (regular browser tab was always fine)** — four earlier attempts fixed the layout's height-resolution chain, moved the footer to `position: fixed`, and moved it outside every `overflow: hidden` ancestor including `body`; all four verified clean in Chromium and still failed on-device. The actual cause: standalone iOS PWAs (not regular Safari tabs) have a documented WebKit bug where the page renders as if an invisible browser toolbar is still pushing content upward, shorting the bottom of the page by roughly the top safe-area amount — confirmed by testing the same URL in a plain browser tab, where it rendered correctly. `html` now reserves deliberately-oversized `min-height` (100% plus the top safe-area inset) so that phantom shift has somewhere to go instead of shorting the real content
- **Custom background gradient/photo didn't reach the same area** — `body` had `background-attachment: fixed`, a well-known unreliable property on iOS Safari; it served no purpose anyway since `body` never scrolls. Removed, so the chosen background now paints consistently instead of falling back to the plain light/dark background color in some regions

## [0.4.3] — 2026-07-20

### Changed

- **Updates are now atomic: instances install exactly the published release** — the updater previously fetched the tip of `master`, so commits pushed after a release (including half-finished work toward the next one) silently shipped to anyone updating, while the app still reported the release's version number. The updater now asks GitHub for the latest published release and installs exactly the commit its tag points at — work landing on `master` between releases never reaches instances until the next release is published. Dev boxes that *want* to track `master` can set `UPDATE_CHANNEL=edge` in `docker/.env`
- **Never updates backwards** — if an instance is already ahead of the latest release (e.g. a dev box that tracked `master`), the updater treats it as up to date instead of attempting a downgrade

## [0.4.2] — 2026-07-20

### Fixed

- **The updater can no longer report "Update successful" without actually updating** — if `git fetch` failed (e.g. the host clone's SSH remote had no key the update cron could use), the updater silently rebuilt the code it already had and re-recorded the old version as a successful update, leaving Admin → Updates claiming the old version was installed with the new one still "available". A failed fetch now aborts the update immediately with a clear `fetch-failed` status and a log hint about switching the host clone to the public HTTPS remote
- **The recorded version now self-heals** — if a past update deployed new code but died (or failed) before recording the new version, every later check would report "already up to date" while showing the old version forever; the updater now detects the mismatch and re-stamps the running version once the app is confirmed healthy
- **Version recording is verified and loud** — the write to `installed_version.json` is read back and any failure is logged prominently (new `success-stamp-failed` status) instead of being silently swallowed; it also no longer requires `python3` on the host
- **Admin → Updates surfaces every failure** — the card now shows a clear banner for any unsuccessful update result (fetch failed, fast-forward refused, version-record failure, unhealthy rollback), not just automatic rollbacks
- **The updater falls back to HTTPS when an SSH fetch fails** — if the host clone's `git@github.com:` remote can't authenticate (typically because the update cron runs as a different user than the one holding the SSH key, e.g. after a `sudo launch.sh`), the updater now retries the same repository over public HTTPS (no credentials needed) and continues, instead of stranding the instance; the log still recommends fixing the remote permanently. Forks are respected — the fallback URL is derived from the configured remote, never hardcoded

## [0.4.1] — 2026-07-20

### Fixed

- **Mobile footer nav no longer sits above the true screen bottom** — on iOS/PWA the layout's `100dvh` height could stop short of the real screen edge, exposing a strip of the page background below the nav; the root layout now resolves its height through an explicit `height: 100%` chain instead of `dvh`
- **Finance's "+ New book" button is reachable on mobile** — it used to sit in a header button row that overflowed off-screen on narrow viewports; it now also appears beside the Finance title on mobile, while desktop keeps the original layout
- **Saved-chats drawer header no longer hidden behind the notch** — the "Chats" panel in AI Chat now respects the device's top safe-area inset, matching the fix already applied to the main app header

*Note: the notification-channel rotation and optional ntfy publisher auth documented under [0.4.0] below landed on `master` a few hours after the `v0.4.0` tag was cut, so instances updating by tag receive them with this release.*

## [0.4.0] — 2026-07-19

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

**In-app Security & Privacy help**
- A new **Help → Security & Privacy** section explains, in plain language *and* technical detail, how your account and data are protected — password hashing, login lockout, data isolation, session cookies, headers, and self-host hardening — plus two new FAQ entries ("Is my data private?" and "Why am I getting 'too many attempts'?")

**Rotate your notification channel**
- Settings → Notifications now shows when your ntfy channel was last rotated and gives you a **Rotate channel** button — regenerates the ID immediately if you ever think it's leaked, no need to touch a config file. LogCore also reminds you here once a channel is over 30 days old

### Fixed

- **What's-New broadcast now fires after in-place updates** — `update.sh` stamps the installed version only after the restarted app passes its health check, so the boot-time announce saw the old version and stayed silent. The scheduler now re-checks 3 minutes after boot and during the daily update check
- **Release tags with a capital V are parsed correctly** (`V0.3.0` previously broke version comparison, hiding updates)
- **Updates card ↺ now really checks** — the refresh button hits a new cache-busting endpoint (`POST /update/check`) instead of re-reading the 4-hour cache, so a fresh release is visible immediately

### Security

- **Login brute-force hardening** — the programmatic token endpoint (`POST /auth/token`) is now rate-limited just like the browser login, and both share one attempt budget so they can't be combined to double the allowance
- **Account lockout** — after 10 failed attempts against one account within 15 minutes, further logins for that account are temporarily refused (HTTP 429) until the old failures age out. This stops distributed credential-stuffing — many IPs each trying a few passwords against one account — that the per-IP rate limit alone misses. The lock is temporary and only counts genuine failed attempts (attempts made while already locked don't extend it), so it can't be used to lock a victim out permanently
- **Constant-time login** — an unknown email now takes the same time to reject as a known one, closing a timing side-channel that could reveal which addresses have accounts
- **Automation Inbox links are scheme-checked** — inbox items may only carry `http(s)` links; a `javascript:`/`data:` URL is now rejected on the way in (and defused in the UI), removing a stored-XSS path a leaked automation token could otherwise use against a reviewing admin
- **Stronger security headers** — responses now send `Strict-Transport-Security` (over HTTPS) and a restrictive `Permissions-Policy`
- **Dependency updates** — `python-jose` → 3.4.0 (algorithm-confusion / JWE advisories) and `python-multipart` → 0.0.18 (multipart-parsing ReDoS); AI/Docker SDK deps gained upper bounds for reproducible installs
- **Scoped automation secret sync** — when Infisical is enabled, only n8n-scoped secrets are written into the n8n container's environment instead of the whole vault (extend via `N8N_ENV_ALLOWLIST`)
- **Backups can be encrypted** — `docker/backup.sh` now supports opt-in GPG encryption (`BACKUP_GPG_RECIPIENT` or `BACKUP_PASSPHRASE`), restricts backup file permissions, and warns that unencrypted archives are secret-grade
- **Automation asset export locked down** — the automation API's asset *read* endpoint now only serves the shared `_team`/`_household` pools, not an arbitrary named user, so a leaked automation token can no longer dump any individual's entire asset store (writes still target a specific user, as before)
- **Content-Security-Policy added** — the app now ships a CSP (`script-src 'self'`, tight defaults, Google Fonts allow-listed) so any future injected script is contained; the one inline script was moved into the bundle to keep the policy strict
- **Refuses to start with an insecure signing key** — a deploy left on the default/empty `SECRET_KEY` (which would let anyone forge an admin token) now fails fast instead of running silently; set a real key (the installer generates one) or `ALLOW_INSECURE_SECRET_KEY=true` for local dev
- **Secure-by-default installer** — fresh installs now default to `COOKIE_SECURE=true` and no wildcard CORS; opt into LAN/plain-HTTP mode explicitly (existing installs are unchanged)
- **Docker socket no longer exposed to the app** — the web app used to bind-mount the host Docker socket (an app compromise ≈ host root). It now reaches Docker through a locked-down `docker-socket-proxy` that permits only the container operations the updater/tunnel need and blocks everything else (exec, volumes, networks, …). **Re-run `launch.sh` on your next deploy so the new `socket-proxy` service starts.**
- **n8n and ntfy ports are now loopback-only** — published to `127.0.0.1` instead of all interfaces; reach the n8n UI via the tunnel or an SSH port-forward. Fresh installs also get strong random `N8N_API_KEY`/`N8N_ENCRYPTION_KEY` instead of shipped defaults
- **ntfy publishing can now require authentication** — if you give ntfy a public hostname (e.g. through the Cloudflare tunnel) for push notifications away from home, `launch.sh` provisions a dedicated publisher account and flips ntfy's default access to read-only: subscribing to your channel stays login-free, but publishing now requires the app's token, closing the open-publish spoofing risk that comes with any internet-reachable ntfy server
- **Pinned third-party images** — `cloudflared`, `ntfy`, `n8n`, and the socket-proxy are pinned to specific versions (no more silent `:latest` pulls), so builds are reproducible and roll-backable
- **Signed-update verification (opt-in)** — the in-place updater (`docker/update.sh`) now *fetches* a new release and verifies it **before** it touches the working tree: with `UPDATE_REQUIRE_SIGNATURE=true` it refuses to build any commit that isn't GPG-signed (commit or annotated tag) by a trusted key, and it fast-forwards only (no silent merge of divergent history). Defends the auto-updater against a compromised origin or MITM. Default off so unsigned deployments are unaffected
- **Vite updated to 5.4.x** — closes the Vite dev-server path-traversal advisories flagged in the audit (dev-tooling; production is served from the built bundle). The remaining esbuild dev-server advisory needs a future major (Vite 8) and is deferred
- **Documented the `--install-deps` bootstrap** — `launch.sh` now warns that `--install-deps` runs the vendors' `curl | sudo sh` scripts as root (trust-on-first-use) and points to the manual-install path for operators who'd rather not

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
