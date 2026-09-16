# Design System

This is the reference for LogCoreOS's visual/component conventions: the design
tokens defined in `app/frontend/src/index.css` and `tailwind.config.js`, plus
a handful of canonical answers to real inconsistencies an audit found in the
codebase (this doc **resolves** those — it doesn't just describe both sides).

For hook usage details (`useEscapeToClose`/`useFocusTrap`/`useScrollLock`,
etc.), see `docs/COMPONENTS.md`.

---

## 1. Design tokens

All quoted verbatim from `app/frontend/src/index.css` and
`app/frontend/tailwind.config.js` as of this writing. If these drift, the CSS
file is the source of truth — fix this doc, not the other way around.

### CSS custom properties (`:root`, light mode)

```css
--accent-400: 251 146 60;   /* #fb923c */
--accent-500: 249 115 22;   /* #f97316 */
--accent-600: 234 88  12;   /* #ea580c */

--card-radius: 0.75rem;
```

`--accent-*` are space-separated RGB triples specifically so Tailwind's
`<alpha-value>` opacity modifier works on them (`rgb(var(--accent-500) / 0.65)`
etc. — see the dashboard resize-handle rules further down in `index.css`).
`--card-radius` is set dynamically by `theme.js`'s `applyCornerStyle`; every
component radius below is defined *relative to it*, not as its own hardcoded
value, so a user's corner-style setting propagates everywhere automatically.

### `charcoal` palette (`tailwind.config.js`)

```js
charcoal: {
  50:  '#f5f5f5',
  100: '#ebebeb',
  200: '#d4d4d4',
  300: '#b0b0b0',
  400: '#888888',
  500: '#6d6d6d',
  600: '#555555',
  700: '#3a3a3a',
  800: '#2a2a2a',
  900: '#1a1a1a',
  950: '#111111',
},
```

`orange` (`400`/`500`/`600`) is the same file mapping straight onto the
`--accent-*` custom properties above — that's how `bg-orange-500` etc.
resolve to the live accent color instead of a fixed Tailwind orange.

### `.card`

```css
.card {
  @apply bg-charcoal-50/80 dark:bg-charcoal-800/80 backdrop-blur-sm border border-charcoal-200/70 dark:border-charcoal-700/70;
  border-radius: var(--card-radius);
}
```

Note the `backdrop-blur-sm`: this creates a new containing block for any
`position: fixed` descendant, which is why nested modals/dialogs must
`createPortal(..., document.body)` rather than relying on being "fixed" —
see `ConfirmDialog.jsx`'s own comments for the real bug this caused.

### `.modal-overlay` / `.modal-card`

```css
.modal-overlay {
  @apply fixed inset-0 bg-black/60 z-50 flex items-end md:items-center justify-center;
  padding: 1rem;
  padding-top: max(1rem, env(safe-area-inset-top));
  padding-bottom: max(1rem, env(safe-area-inset-bottom));
}
.modal-card {
  @apply card w-full overflow-y-auto overflow-x-hidden;
  max-height: 85dvh;
}
```

Bottom-sheet on mobile (`items-end`), centered on desktop (`md:items-center`).
`.modal-card` composes `.card` — it inherits the blur/border/radius above.

### `.btn-primary`

```css
.btn-primary {
  @apply bg-orange-500 hover:bg-orange-600 text-white font-medium px-4 py-2 transition-colors;
  border-radius: calc(var(--card-radius) * 0.6);
}
```

**Hover direction: base `500` → hover `600` — the accent gets *darker* on
hover.** This is the reference convention the new `.btn-danger` pattern
(§2) is deliberately made to match.

### `.btn-ghost`

```css
.btn-ghost {
  @apply text-charcoal-600 dark:text-charcoal-300 hover:bg-charcoal-100 dark:hover:bg-charcoal-700 px-3 py-2 transition-colors;
  border-radius: calc(var(--card-radius) * 0.6);
}
```

### `.btn-pill` / `.btn-pill-error`

```css
.btn-pill {
  @apply inline-flex items-center justify-center bg-orange-500 hover:bg-orange-600 text-white font-medium text-sm px-4 py-1.5 transition-colors disabled:opacity-60 whitespace-nowrap max-w-full truncate;
  border-radius: 9999px;
}
.btn-pill-error {
  @apply bg-red-500 hover:bg-red-600;
}
```

`.btn-pill` is always a true pill (`border-radius: 9999px`), regardless of
the user's corner-style setting — deliberate, per the comment above it in
`index.css` ("only the pill button so there can be many of them added on a
small space"). `.btn-pill-error` is an override *class* meant to be combined
with `.btn-pill` (`className="btn-pill btn-pill-error"`) to recolor it red;
note it already uses the `500`→`600` darker-on-hover direction — it's the one
existing piece of the codebase that already agrees with the §2 decision
below.

### `.input`

```css
.input {
  @apply bg-white dark:bg-charcoal-700 border border-charcoal-300 dark:border-charcoal-600 px-3 py-2 text-charcoal-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-orange-500 w-full;
  border-radius: calc(var(--card-radius) * 0.6);
  color-scheme: light;
}
.dark .input {
  color-scheme: dark;
}
```

### `.badge`

```css
.badge {
  @apply text-xs font-medium px-2 py-0.5 rounded-full;
}
```

Unlike `.btn-*`, `.badge` carries no color — every call site supplies its own
background/text color utilities on top (e.g.
`badge bg-charcoal-100 dark:bg-charcoal-700 text-charcoal-600 dark:text-charcoal-300`,
as used in `Tasks.jsx`/`Finance.jsx`).

---

## 2. DECISION: the canonical `.btn-danger` pattern

**There is no `.btn-danger` class in `index.css`.** Two incompatible
hand-rolled destructive-button patterns currently coexist in the codebase:

- **Pattern A** — `bg-red-500 hover:bg-red-600` (base `500`, hover `600`,
  gets **darker** on hover). Confirmed live in
  `module_packages/goals/frontend/GoalModal.jsx:536` and
  `module_packages/notes/frontend/Notes.jsx:1053,1074`:
  ```jsx
  className="flex-1 py-2 rounded-lg bg-red-500 hover:bg-red-600 text-white text-sm font-medium transition-colors"
  ```
- **Pattern B** — `bg-red-600 hover:bg-red-500` (base `600`, hover `500`,
  gets **lighter** on hover — the opposite direction). Confirmed live in
  `components/ConfirmDialog.jsx`'s own `danger` prop:
  ```jsx
  danger ? 'bg-red-600 hover:bg-red-500' : 'bg-orange-500 hover:bg-orange-400'
  ```

### The decision

**Pattern A (`bg-red-500 hover:bg-red-600`) is canonical, going forward.**

Reasoning: `.btn-primary` — the one actual design-token definition for a
filled action button in `index.css` — hovers `orange-500 → orange-600`,
i.e. darker on hover. A destructive button is still a filled action button;
it should follow the exact same interaction convention as every other
filled button in the system, just in red instead of orange. Pattern B not
only conflicts with Pattern A elsewhere in the app, it also runs backwards
relative to `.btn-primary` itself — hovering *lighter* reads as "less
intense," which is a strange signal for the button that deletes something.
(`.btn-pill-error` already agrees with this direction, for what it's worth
— it was Pattern B's `ConfirmDialog.jsx` that was the outlier.)

### Canonical class string

There is still no dedicated `.btn-danger` component class — this doc
establishes the utility string to hand-roll consistently until one is added
to `index.css`. For a full-width/flex modal destructive action (the common
case, matching the real call sites above):

```
bg-red-500 hover:bg-red-600 text-white text-sm font-medium rounded-lg transition-colors
```

For an inline text-only danger control that isn't a filled button, follow
the same base→darker-on-hover direction (see `Notes.jsx:175`'s `danger`
class constant: `hover:bg-red-50 dark:hover:bg-red-900/20 text-red-600
dark:text-red-400` — hover *adds* a tint rather than shifting the text
color, which is consistent with "gets more intense, not less").

**`ConfirmDialog.jsx`'s `danger` prop is the one call site that currently
implements the wrong (Pattern B) direction and should be flipped to
`bg-red-600 hover:bg-red-700`** (its base is `600`, one step darker than the
`500` used elsewhere, since it's already a deliberately weightier
alertdialog action — keep the base, just fix the hover direction to match
`.btn-primary`'s darker-on-hover convention) — **as a follow-up, not in this
pass.** Also note while flipping it: `ConfirmDialog.jsx`'s *non-danger*
confirm button currently hovers `bg-orange-500 hover:bg-orange-400`
(lighter), which likewise disagrees with `.btn-primary`'s `500→600`
direction and should be corrected to `hover:bg-orange-600` in the same
cleanup pass.

**Scope note:** this pass only establishes the canonical answer. Existing
call sites (including the two Pattern-B spots named above) are **not**
retrofitted here — that's separate, deferred cleanup work. New code should
use the canonical string above; do not add new Pattern-B call sites.

---

## 3. DECISION: the canonical form-label pattern

Form labels currently split roughly along module lines into two
incompatible patterns:

- **Bold camp** — `block text-sm font-medium mb-1`. Confirmed live in
  `components/TaskModal.jsx` (e.g. line 227: `<label className="block
  text-sm font-medium mb-1">Task</label>`) and `components/EventModal.jsx`
  (e.g. line 190: `<label className="block text-sm font-medium
  mb-1">Title</label>`). Used throughout Tasks, Calendar, Assets.
- **Muted-small camp** — `text-xs text-charcoal-500 dark:text-charcoal-400`.
  Confirmed live in
  `module_packages/finance/frontend/TransactionModal.jsx` (e.g. line 314:
  `<label className="text-xs text-charcoal-500
  dark:text-charcoal-400">Amount</label>`),
  `module_packages/goals/frontend/GoalModal.jsx` (e.g. line 279: `<label
  className="text-xs text-charcoal-500 dark:text-charcoal-400">Title</label>`),
  and `module_packages/contacts/frontend/ContactModal.jsx` (e.g. line 27:
  `<label className="block text-xs text-charcoal-500
  dark:text-charcoal-400">`). Used throughout Finance, Goals, Contacts.

### The decision

**The bold camp (`block text-sm font-medium mb-1`) is canonical, going
forward.**

Reasoning: a form label's job is to be found and read *before* the field is
focused — that's a scannability problem, not a decoration problem. `text-xs`
+ a muted charcoal color are both moves that reduce a label's visual weight
at exactly the moment (a person scanning a multi-field modal top to bottom)
where weight is what helps. `text-sm font-medium` at full text color is also
the far more common convention on the web generally, and it's already the
majority pattern inside this codebase (Tasks/Calendar/Assets vs.
Finance/Goals/Contacts). Muted-small labels read fine in isolation but
under-perform specifically in the dense, many-field modals
(`TransactionModal`, `GoalModal`) where this pattern is currently used —
the one place where legibility matters most.

### Canonical class string

```
block text-sm font-medium mb-1
```

**Scope note:** existing Finance/Goals/Contacts forms are **not**
retrofitted in this pass — that's deferred cleanup work for a future pass.
New form fields, in any module, should use the canonical string above.

---

## 4. ARIA tablist vs. filter chip / sort picker / form-field selector

A `flex gap-1 bg-charcoal-100 dark:bg-charcoal-800 rounded-lg p-1` row of
buttons is the app's generic "segmented control" visual shape. It is used for
two *semantically different* things, and only one of them is a real tab:

### IS a real tab → gets `role="tablist"` + `lib/tabListKeyboard.js`

A segmented control is a real tab bar when selecting an option **switches
which content panel is displayed** — the ARIA Authoring Practices definition
of a tab. These get the full pattern: `role="tablist"` on the container,
`role="tab"` + `aria-selected` + roving `tabIndex` (`0` for the active tab,
`-1` for the rest) on each button, and `onKeyDown` wired to
`handleTabListKeyDown` from `lib/tabListKeyboard.js` (Left/Right moves *and*
activates the adjacent tab; Home/End jump to the ends — the standard
non-scrolling-tablist interaction).

Real, current examples (confirmed live):
- **Goals'** ME / pool tabs (`module_packages/goals/frontend/Goals.jsx:152`)
- **Finance's** Book-view tabs (`module_packages/finance/frontend/Finance.jsx:215`)
- Household's and Team's own Calendar/Tasks tab bars
- `UserDetail.jsx`'s Personal/Business workspace switcher
- `pages/Trash.jsx`'s admin-only Personal/Household-or-Team tabs

Minimal shape (from `Goals.jsx`):
```jsx
<div role="tablist" aria-label="Goals view" className="flex gap-1 bg-charcoal-100 dark:bg-charcoal-800 rounded-lg p-1">
  <button
    role="tab"
    aria-selected={tab === t}
    tabIndex={tab === t ? 0 : -1}
    onClick={() => setTab(t)}
    onKeyDown={e => handleTabListKeyDown(e, { tabs, activeIndex: i, onActivate: setTab, refs: tabRefs })}
    ...
  >
```

### Is NOT a tab → no tab semantics, plain buttons

Same visual shape, but selecting an option **filters or sorts the current
view, or picks a value inside a form** — nothing about which content panel
is showing changes. Giving these `role="tab"` would misrepresent a filter or
form field as content-panel switching to a screen reader, so they
deliberately stay plain buttons with no ARIA tab roles and no
`tabListKeyboard.js` wiring.

Real, current examples (confirmed live):
- **Tasks'** filter chips — `pending`/`all`/`done`/`overdue`
  (`module_packages/tasks/frontend/Tasks.jsx:272`) and its own
  **Sort by** picker (`Tasks.jsx:300`, `SORT_MODES`)
- **Contacts'** type filter chips (`module_packages/contacts/frontend/Contacts.jsx:267`)
- `TransactionModal`'s / `ContactModal`'s in-form field selectors (e.g.
  Expense/Income/Transfer, Person/Company) — these live inside a `<form>`
  and call `set('field', value)`; they're form controls, not navigation

This is a settled decision, not an open question — it was the last item
closed out in the 2026-09-05/06 accessibility pass (see `docs/TASKS.md` and
`docs/MAP.md`'s `tabListKeyboard.js` entry for the original reasoning). Any
new segmented-control-styled row should be classified the same way before
it's built: does choosing an option swap the content panel (→ real tab), or
does it filter/sort/set a form value (→ plain buttons, no tab roles)?

---

## 5. Confirm dialogs, empty states, and the accessibility baseline

### `ConfirmDialog` vs. a plain confirm

Use `components/ConfirmDialog.jsx` for **every** destructive or
consequential confirmation in the app — it's the shared, accessible
replacement for raw `confirm()`/`window.confirm()` calls (the app is down to
one known legacy holdout, `pages/settings/admin/General.jsx:501`, which is
pre-existing and not part of this pass).

- Pass `danger` (boolean) whenever the confirmed action is destructive
  (delete, permanently remove, etc.) — it drives the red confirm-button
  styling per §2 above. Omit it for a plain "are you sure?" that isn't
  destructive (it falls back to the orange/primary styling).
- Pass `requireTypedText="DELETE"` (or similar) **only** for the highest-
  stakes actions — currently reserved for account deletion — where the
  confirm button should stay disabled until the typed value matches
  exactly.
- Don't hand-roll a new confirm modal. `ConfirmDialog` already handles
  nested-modal portal placement correctly (`createPortal(...,
  document.body)`, working around the `backdrop-blur` containing-block
  issue noted in §1) — a new hand-rolled dialog would very likely
  reintroduce that bug.

### `EmptyState` vs. custom empty copy

Use `components/EmptyState.jsx` for the "this list/view has nothing in it
yet" case on any page — it's the shared icon + title + optional-description
+ optional-CTA shape (e.g. `Contacts.jsx`'s `<EmptyState icon="👥" title="No
contacts yet" description="Add your first contact to get started."
ctaLabel="+ New Contact" onCta={...} />`). Reach for custom empty-state copy
only when the situation genuinely isn't "no items yet" — e.g. "no results
match your filter" inline messaging that needs to sit next to active filter
controls rather than replace the whole view, or a state that needs richer
content than icon/title/description/CTA supports. Default to `EmptyState`
first; only skip it with a concrete reason.

### The accessibility baseline every new page/modal is expected to meet

Every new modal (and any page-level dialog-like surface) is expected to
wire up the same three hooks `ConfirmDialog.jsx` itself uses:

- `useEscapeToClose`
- `useFocusTrap`
- `useScrollLock`

See `docs/COMPONENTS.md` for how each hook is used (signatures, ref
requirements, gotchas) — not repeated here.
