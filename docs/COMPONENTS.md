# Frontend Component & Hook Reference

Inventory of the shared frontend building blocks in `app/frontend/src/lib/` and
`app/frontend/src/components/` — what each one does, its real signature, and a
real call site pulled from the actual code. Written after a single audit batch
(2026-09-05/06) independently reproduced the **same** `useFocusTrap`/
`useScrollLock` wiring bug three separate times, in three different files
(`AssetModal.jsx`, `RecurringPanel.jsx`, `AssetView.jsx`), because nothing
written down told anyone the rule. Section 2 below is that rule. Read it
before wiring a new modal or popup.

No shared `<Modal>` wrapper exists in this codebase — every modal hand-rolls
its own `.modal-overlay`/`.modal-card` markup, and `useEscapeToClose` /
`useFocusTrap` / `useScrollLock` are wired into each one individually. That's
a deliberate, existing tradeoff (see each hook's own file for why), not
something this doc proposes fixing — but it's exactly why the wiring rules
below have to be written down instead of enforced by a wrapper.

---

## 1. Shared hooks (`app/frontend/src/lib/`)

### `useEscapeToClose(onClose, { hasUnsavedChanges = false, onUnsavedAttempt } = {})`

File: `app/frontend/src/lib/useEscapeToClose.js`

Global `window` `keydown` listener; calls `onClose()` on Escape. If
`hasUnsavedChanges` is true and `onUnsavedAttempt` is given, it calls that
instead of closing — so Escape defers to the caller's own "discard changes?"
prompt, matching what clicking outside or the X button already do.

Plain call (no unsaved-changes guard) — `components/ConfirmDialog.jsx`:
```js
useEscapeToClose(onCancel)
```

Guarded call — `module_packages/assets/frontend/AssetModal.jsx`:
```js
useEscapeToClose(mode === 'view' ? () => {} : onClose, {
  hasUnsavedChanges,
  onUnsavedAttempt: () => confirmDiscard(onClose),
})
```
(The `mode === 'view' ? () => {} : onClose` guard exists because this
component conditionally renders `AssetView` instead of its own editor overlay
in view mode, and `AssetView.jsx` wires its own independent
`useEscapeToClose(onClose)` — this call should only fire while this
component's editor overlay is actually showing.)

A component can call this hook more than once for independently-closable
layers stacked on the same screen (a popup on top of a modal) — see
`AssetModal.jsx`, which calls it once for the editor and again for its
archive-confirmation popup (`useEscapeToClose(() => setArchivePrompt(false))`).

### `useFocusTrap(containerRef, active = true)`

File: `app/frontend/src/lib/useFocusTrap.js`

Traps Tab/Shift+Tab cycling inside `containerRef`'s own focusable elements
while `active`, per the ARIA Dialog pattern (no modal in this app trimmed Tab
focus before this hook existed — a keyboard user could Tab straight through
an open modal into the page behind it). `containerRef` must point at the
modal's own root — its `.modal-card`, not `.modal-overlay` — both to keep the
`querySelectorAll` scan small and to make the intent explicit.

**See section 2 — this is the hook the "active must be tied to the real
visibility flag" rule is about.**

### `useScrollLock(active = true)`

File: `app/frontend/src/lib/useScrollLock.js`

Sets `overflow: hidden` on `<main>` (`components/Layout.jsx` — the app's
single scrollable container, the same node `usePullToRefresh` targets) while
`active`. Uses a **module-level reference count**, not per-instance state:
a dialog can open on top of an already-open modal (a "Discard changes?"
confirm over an edit form), each independently calling this hook, and only
the *last* one to unmount should actually restore scrolling — otherwise
closing the inner popup would silently re-enable background scroll while the
outer modal is still open.

Plain call — `components/ConfirmDialog.jsx`: `useScrollLock()`
Tied call — `module_packages/finance/frontend/RecurringPanel.jsx`:
`useScrollLock(!!form)`

Same active-flag rule as `useFocusTrap` applies here (section 2) — but note
the failure mode is different and *louder*: because `active` defaults to
`true`, a bare `useScrollLock()` call inside an always-mounted parent locks
`<main>`'s scroll immediately and permanently from that parent's own mount,
regardless of whether the popup it was meant to guard is open — the app
becomes visibly unscrollable right away, not silently broken. `useFocusTrap`
has no such default-true tell; its bare-call failure is silent until someone
tests Tab-key navigation. That difference is *why* the same bug pattern got
caught for `useFocusTrap` specifically (three times) rather than
`useScrollLock` — a broken scroll lock is obvious in five seconds of manual
testing; a broken focus trap isn't.

### `usePullToRefresh(onRefresh, { threshold = 70, containerRef, enabled = true } = {})`

File: `app/frontend/src/lib/usePullToRefresh.js`
Returns `{ pullDistance, refreshing, threshold }`.

Hand-rolled touch-only (touchstart/touchmove/touchend) pull-to-refresh
gesture over `<main>` by default — sqrt-damped elastic resistance so the
indicator doesn't track the finger 1:1. Touch-only is what keeps it
mobile-only for free (desktop mouse drags never fire touch events).

- `containerRef`: pass when a page scrolls its own nested region instead of
  `<main>` — otherwise `main.scrollTop` always reads 0 there and the gesture
  fires on nearly every downward drag.
- `enabled`: turn the gesture off while the page's own touch/pointer
  interaction is active, to avoid two gesture recognizers fighting over the
  same touch.

Real call sites:
```js
// module_packages/tasks/frontend/Tasks.jsx
const pull = usePullToRefresh(load)

// pages/Brain.jsx — disabled while a file is selected (its own touch UI takes over)
const pull = usePullToRefresh(loadFiles, { enabled: !selected })

// module_packages/dashboard/frontend/Dashboard.jsx — targets its own scroll container
const pull = usePullToRefresh(() => loadCurrent(current.id, { resetEditing: false }), { ... })
```
Pairs with `components/PullToRefreshIndicator.jsx` — a purely presentational
spinner; pass it the same `{pullDistance, refreshing, threshold}` object the
hook returned.

Deliberately **not** wired into `module_packages/notes/frontend/Notes.jsx`:
its file-tree pane already has its own pointer-based drag-to-reorder, and a
drag starting at the top of the tree would be ambiguous with a pull-to-refresh
attempt. Needs its own conflict-resolution design, not a bolted-on fix.

### `useBulkSelect(getId = (item) => item.id)`

File: `app/frontend/src/lib/useBulkSelect.js`
Returns `{ active, setActive, stop, selected, toggle, toggleAll, clear, isSelected, count }`.
`selected` is a `Set` of ids.

Shared multi-select state for list-view bulk actions. `toggleAll(visibleItems)`
only ever operates over the ids the caller hands it directly — it's the
caller's job to pre-filter to the currently visible/filtered set; never pass
it a full unfiltered dataset.

Real call sites:
```js
// module_packages/assets/frontend/Assets.jsx / module_packages/tasks/frontend/Tasks.jsx
// module_packages/contacts/frontend/Contacts.jsx — default getId (item.id)
const bulkSelect = useBulkSelect()

// module_packages/notes/frontend/Notes.jsx — tree is keyed by path, not id
const bulkSelect = useBulkSelect(item => item.path)
```
Pairs with `components/SelectCheckbox.jsx` (a real 44×44px touch target
wrapping a small visible checkbox) and `components/BulkActionBar.jsx`
(`{count, onCancel, actions}` — one component for both the mobile bottom bar
and the desktop sticky toolbar).

### A naming surprise: `Toast` / `useToast` is not in `components/`

`ToastProvider` and `useToast` live in **`app/frontend/src/lib/toast.jsx`**,
not `components/Toast.jsx` — there is no `Toast.jsx` component file to find.
It's grouped with `lib/` because it's provider/context plumbing (like
`lib/auth.jsx` and `lib/workspace.jsx`) rather than a component you render
directly. `useToast()` returns `{ show, success, error, dismiss }`; success
toasts auto-dismiss after ~4s, error toasts persist until manually dismissed,
and multiple toasts stack rather than replacing each other. It portals to
`document.body` for the same reason covered in section 3.

---

## 2. The rule: tie `active` to the real visibility flag, or it silently never fires

This is the actual bug, found independently three times in one audit batch,
that this doc exists to prevent a fourth time.

**The rule:** if a modal/popup's card is mounted *conditionally inside an
already-persistent parent* — the parent component itself never remounts,
e.g. a popup toggled by `showX`/`archivePrompt`/`form` state inside a
component that's always rendered — then `useFocusTrap`'s and
`useScrollLock`'s `active` argument **must** be tied to that exact boolean:

```js
useFocusTrap(cardRef, showDelete)
useScrollLock(showDelete)
```

**Not** called bare:
```js
useFocusTrap(cardRef)   // WRONG in this shape
useScrollLock()          // WRONG in this shape (see section 1's note on why this one fails loudly instead)
```

**Why it breaks:** `useFocusTrap`'s effect dependency array is
`[containerRef, active]`. `containerRef` is a stable ref *object* across
renders (React guarantee) — it never changes identity even though `.current`
changes — and a bare call's `active` defaults to `true` and never changes
either. So the effect runs exactly **once**, at the moment the *parent*
component first mounts — while `containerRef.current` is still `null`,
because the popup's own card hasn't rendered yet. The effect's early
`if (!container) return` bails out immediately, and because neither
dependency will ever change again, **the effect never re-runs** — not when
the popup opens, not ever, for the entire lifetime of the parent. It silently
no-ops forever. Nothing crashes and nothing errors; a keyboard user just
finds Tab walks straight out of the popup into the page behind it.

**Contrast — when a bare call is correct:** if the component holding the ref
is itself freshly mounted per-open (a component only rendered while some
`modal !== null`/`confirmState !== null` state is truthy, so React tears the
whole component down on close and instantiates a brand-new one on the next
open), the ref starts fresh and gets attached during that mount's own render,
before the effect runs. A bare `useFocusTrap(cardRef)` is correct there —
tying it to a flag would be redundant, not wrong, but the persistent-parent
failure mode above doesn't exist in this shape.

### Real "tied" examples (popup card conditional inside a persistent parent)

- `module_packages/finance/frontend/RecurringPanel.jsx` — the panel itself is
  a persistent, always-mounted tab body; its two form popups toggle inside it:
  ```js
  useFocusTrap(formCardRef, !!form)
  useScrollLock(!!form)
  useFocusTrap(plannedCardRef, !!plannedForm)
  useScrollLock(!!plannedForm)
  ```
- `module_packages/assets/frontend/AssetModal.jsx` — the archive-confirmation
  overlay stacks on top of the already-mounted editor overlay:
  ```js
  useFocusTrap(archiveCardRef, archivePrompt)
  useScrollLock(archivePrompt)
  ```
- `module_packages/assets/frontend/AssetView.jsx` — the mute-settings popup
  stacks on top of the persistent asset view:
  ```js
  useFocusTrap(muteCardRef, mutePopup)
  useScrollLock(mutePopup)
  ```
- `components/WelcomeBackPopup.jsx` — the whole component is rendered
  unconditionally by `Layout.jsx` (`<WelcomeBackPopup />`, never
  conditionally mounted itself); its own popup visibility is entirely
  internal state:
  ```js
  useFocusTrap(cardRef, !!(state && state.show))
  useScrollLock(!!(state && state.show))
  ```
- `components/Layout.jsx` — the app shell is the most persistent component
  in the app by definition; its mobile drawer toggles inside it:
  ```js
  useFocusTrap(drawerCardRef, showDrawer)
  useScrollLock(showDrawer)
  ```
- `module_packages/goals/frontend/GoalModal.jsx` — the delete-confirmation
  popup toggles inside the modal's own persistent-while-open instance
  (contrast with that same file's own main `cardRef`, below):
  ```js
  useFocusTrap(deleteCardRef, showDelete)
  ```

### Real "bare is correct" examples (component itself remounts fresh per open)

- `components/ConfirmDialog.jsx` — every call site conditionally mounts a
  fresh instance (`{confirmState && <ConfirmDialog .../>}`); there's no
  internal `open` prop to manage, so a plain `useFocusTrap(cardRef)` /
  `useScrollLock()` is correct as-is.
- `module_packages/assets/frontend/AssetModal.jsx`'s own main `cardRef` — its
  parent, `Assets.jsx`, mounts it as
  `{modal && <AssetModal key={modal.asset?.id || 'new'} .../>}`; the `key`
  even forces a fresh instance per asset. Bare `useFocusTrap(cardRef)` here
  is correct — it's the *same file* as the archive-popup example above, and
  the difference is entirely about which ref is freshly-mounted vs.
  conditionally-toggled-within-a-mount.
- `module_packages/goals/frontend/GoalModal.jsx`'s own main `cardRef` — its
  parent, `Goals.jsx`, mounts it as
  `{(openGoalId || showCreate) && <GoalModal .../>}`. Bare is correct.
- `module_packages/notes/frontend/Notes.jsx`'s `ContextMenu` and
  `NoteShareModal` — both separate function components, each conditionally
  mounted by Notes (`{contextMenu && <ContextMenu .../>}`,
  `{shareModal && <NoteShareModal .../>}`). Bare is correct in both.
- `components/GlobalSearch.jsx` — mounted by `Layout.jsx` as
  `{searchOpen && <GlobalSearch onClose={...} />}`. Bare is correct.
- `module_packages/dashboard/frontend/DashboardAccessModal.jsx` — mounted by
  `Dashboard.jsx` as `{showAccess && current && <DashboardAccessModal .../>}`.
  Bare is correct.

**The one question to ask before wiring either hook into a new
modal/popup:** *"Does the component holding this ref get torn down and
recreated by its parent every time this closes and reopens, or does it stay
mounted the whole time and just toggle a boolean?"* Fresh-mount-per-open →
bare call. Toggled-inside-a-persistent-mount → tie `active` to that exact
boolean.

---

## 3. Portal convention: `createPortal(..., document.body)`

**The mechanism (full writeup: `docs/MEMORY.md`, "Known Gotchas" — search
`backdrop-filter`):** Tailwind's `backdrop-blur-*` (`backdrop-filter`) on an
ancestor creates a new CSS containing block for `position: fixed`
descendants, per spec, the same as `transform`/`filter`/`perspective`/
`contain: paint`. Every `.modal-card` in this app uses `.card`, which carries
`backdrop-blur-sm`. So a `fixed inset-0` overlay nested inside an
already-open `.modal-card` doesn't cover the true viewport — it resolves
against that ancestor's (possibly scrolled, possibly small) box instead,
visually "trapping" the nested overlay inside the outer card and scrolling
it along with the outer card's own content. This was first caught on
`assetDisplay.jsx`'s `ImageLightbox` (opened from an attachment thumbnail
inside `AssetModal`'s `.modal-card`) and again on `ConfirmDialog.jsx` (opened
from inside another modal as a Delete button or the "Discard changes?"
prompt — see that file's own docstring for the full incident writeup).

**When you need a portal:** any modal, popup, or full-screen overlay that
*could ever* render nested inside another already-open `.modal-card` —
which in practice means any shared/reusable overlay component, since you
can't control every future call site. Known portal users today:
`components/ConfirmDialog.jsx`, `components/assetDisplay.jsx` (`ImageLightbox`),
`components/SimpleFormModal.jsx`'s callers area — check the component before
assuming — `components/BulkActionBar.jsx` (mobile bar only; desktop is
`position: sticky`, which doesn't share this concern), and `lib/toast.jsx`.

**When you don't:** a component you're certain is only ever rendered at the
top level of a page (never embedded inside another modal), or anything using
`position: sticky` instead of `fixed` (sticky doesn't create/need to escape a
containing block the same way). When in doubt — anything shared across more
than one call site — default to the portal; that's the standing guidance in
`docs/MEMORY.md`'s writeup, not a case-by-case judgment call.

---

## 4. Shared top-level components (`app/frontend/src/components/`)

One-line description of each. Check here before hand-rolling a new version
of one of these.

| Component | What it does / when to reach for it |
|---|---|
| `AssetPickerField.jsx` | Single-asset reference field for dashboard block config — compact "current selection + Change ▾" inline tree toggle. Falls back to a plain text input if the Assets module is unavailable (403). |
| `AssetTreePicker.jsx` | Foldered asset picker (expand/collapse) reused by Move and the create-asset parent chooser. A node whose parent isn't in the candidate set floats to top level. `onPick(assetId \| null)`. |
| `BulkActionBar.jsx` | Shared bulk-action bar for list views — `{count, onCancel, actions}`. Mobile: portaled fixed bottom bar. Desktop: sticky top toolbar. Pairs with `useBulkSelect`/`SelectCheckbox`. |
| `CalendarGrid.jsx` | Full month calendar grid — day cells, holiday engine, event rendering. Calendar module's main view. |
| `ConfirmDialog.jsx` | Shared confirmation dialog (Yes/No/Cancel, or a stricter "type X to confirm" variant for account deletion). Replaced 34 raw `confirm()` call sites. Always portals; parent conditionally mounts it. |
| `DemoBanner.jsx` | Non-dismissible banner shown only when the backend reports `demo_mode: true`. |
| `EmojiPicker.jsx` | Curated, self-contained emoji swatch grid (no external picker/CDN). Manual type/paste also works. |
| `EmptyState.jsx` | Shared "No X yet" empty state — icon + message + optional CTA button, replacing each module's own hand-rolled version. |
| `ErrorBoundary.jsx` | Class component; catches render errors app-wide. Logs full error/stack to the console (the on-screen fallback message is minified). |
| `EventModal.jsx` | Calendar event create/edit modal (personal + household variants). Exports `EVENT_COLORS`. |
| `EventPicker.jsx` | Search-autocomplete over the user's calendar events, mirroring `ContactPicker`'s pattern. Single id in/out. |
| `GettingStarted.jsx` | First-run checklist card on the Dashboard. Steps are filtered by the viewer's own `disabledModules` so a restricted role never sees a dead link. |
| `GlobalSearch.jsx` | App-wide search modal, opened from `Layout.jsx`'s header search icon. Modeled on `DashboardSwitcher.jsx`. |
| `HelpButton.jsx` | Small ⓘ affordance next to a page title; deep-links to that module's section in the Help guide. |
| `HistoryCalendar.jsx` | Generic month/year calendar for visualizing dated history data (a task's `completion_log`, a goal's metric log). Knows nothing about tasks/goals — callers build `entriesByDate` themselves. |
| `Layout.jsx` | The app shell — header, nav, mobile drawer, global search trigger, banners. The one component that's truly always-mounted; see section 2. |
| `MetricGraph.jsx` | Inline-SVG line chart for a goal's dated numeric metric log. No charting library — a few dozen points don't need one. |
| `NotePicker.jsx` | Search-autocomplete over the user's notes, mirroring `ContactPicker`. Keys off `path`, not id. Excludes folders. |
| `OfflineBanner.jsx` | Persistent banner on connectivity loss. Combines `navigator.onLine` with a periodic `/api/v1/health` reachability check (online-ness alone is unreliable). |
| `PullToRefreshIndicator.jsx` | Purely presentational spinner; pass through the `{pullDistance, refreshing, threshold}` a page's own `usePullToRefresh()` call returned. |
| `RecurrenceLog.jsx` | Task-specific adapter over `HistoryCalendar` — maps a task's `completion_log` into `entriesByDate`. |
| `RecurrencePicker.jsx` | Structured recurrence-rule editor, create-only. Also exports `describeRecurrence()` for read-only display of an existing pattern. |
| `SelectCheckbox.jsx` | Native checkbox wrapped in a real 44×44px touch target (the visible box stays small). Pairs with `useBulkSelect`. |
| `SimpleFormModal.jsx` | Shared chrome for a small single-purpose form modal — title/✕, body, error line, Cancel/Confirm footer. Extracted from Notes.jsx's six near-identical modals. Deliberately does **not** wire `useEscapeToClose`/`useFocusTrap`/`useScrollLock`/portal itself — pass in a shared `cardRef`; the caller owns that wiring once against whichever `modal` state drives several mutually-exclusive instances. |
| `TagInput.jsx` | GitHub-topics-style chip input. Free-text mode (any value becomes a chip) or selector mode (`suggestions`, optionally `strict`). |
| `TaskModal.jsx` | Task create/edit modal. Read-first: an existing task opens via `TaskView` (view mode) before flipping into the editor. |
| `TaskPicker.jsx` | Search-autocomplete over the user's own tasks. Single id in/out. |
| `TaskView.jsx` | Read-first view of a single task — `TaskModal`'s view mode. |
| `TrashLink.jsx` | Small 🗑 affordance next to a module's title; links to `/trash?module=X`. |
| `WelcomeBackPopup.jsx` | Middle-screen "welcome back" popup, checked once per app load, shown if the user's been away past a threshold. Rendered unconditionally by `Layout.jsx`; visibility is fully internal state. |
| `WhatsNewBanner.jsx` | Dismissible banner shown for a few days after an app update. Per-version dismissal remembered locally. |
| `assetDisplay.jsx` | Shared helpers/subcomponents used by **both** `AssetView` and `AssetModal` — `formatChanges`, `fieldDisplay`, `ContactFieldInput`, `FieldInput`, `CapsSelector`, `AttachmentThumb` (includes the portaled `ImageLightbox`). Kept in its own module specifically to avoid a circular import between the two. |

The subdirectories `components/contacts/`, `components/dashboard/`,
`components/finance/`, and `components/settings/` hold module-scoped pickers
and widgets (e.g. `dashboard/BlockPicker.jsx`, `contacts/ContactPicker.jsx`,
`finance/money.js`) rather than general-purpose shared components — not
inventoried here, but worth checking if you're building something
dashboard/contacts/finance/settings-specific before writing a new one.

---

## Related docs

- `docs/MEMORY.md` — "Known Gotchas" section (search `backdrop-filter`) has
  the full incident writeups this doc's portal section summarizes.
- `docs/AGENTS.md` — overall architecture and conventions.
