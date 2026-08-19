// Shared by blockRegistry.js (BlockPicker's ActionsEditor config UI) and
// blocks.jsx (the actual button rendering) — kept in its own file since
// blockRegistry.js imports components FROM blocks.jsx, so blocks.jsx can't
// import blockRegistry.js back without a circular dependency.
//
// `nav` always opens the record's own page via deepLinkUrl (lib/deepLinks.js)
// — the module is implied by a block's declared recordKind, never asked for,
// since a button attached to a Tasks block can only ever mean "open this
// task." `status` offers a curated preset list per kind (not status_button's
// full generic record-type/field composer) — deliberately smaller than a
// fully free-form action builder, matching how much a per-row button
// plausibly needs.
export const ACTION_MODULE_BY_KIND = {
  task: 'tasks',
  asset: 'assets',
  contact: 'contacts',
  event: 'calendar',
  note: 'notes',
}

// Per-button color selectability (owner ask, 2026-08-17) — a small fixed
// palette rather than a free color picker, since the app has no multi-color
// infrastructure to extend (lib/theme.js's accent color is one global hex,
// not a per-item palette). 'default' matches the button's original look
// exactly (no bg, orange hover only) so existing configured actions with no
// `color` field render unchanged.
// `classes` is the REAL button's style (hover-only backgrounds — nav-pill
// look at rest, color only reveals on hover, matching this app's minimal
// button aesthetic). `swatch` is a separate, always-solid fill used only by
// the picker UI below (BlockPicker.jsx's ColorSwatchPicker) — `classes`
// alone would render 'default' as a blank/invisible square in a picker,
// indistinguishable from "nothing selected."
export const BUTTON_COLORS = [
  { id: 'default', label: 'Default', classes: 'hover:bg-orange-100 dark:hover:bg-orange-900/30', swatch: 'bg-white dark:bg-charcoal-800 border-dashed' },
  { id: 'blue', label: 'Blue', classes: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 hover:bg-blue-200 dark:hover:bg-blue-900/50', swatch: 'bg-blue-500' },
  { id: 'green', label: 'Green', classes: 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 hover:bg-green-200 dark:hover:bg-green-900/50', swatch: 'bg-green-500' },
  { id: 'red', label: 'Red', classes: 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 hover:bg-red-200 dark:hover:bg-red-900/50', swatch: 'bg-red-500' },
  { id: 'purple', label: 'Purple', classes: 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 hover:bg-purple-200 dark:hover:bg-purple-900/50', swatch: 'bg-purple-500' },
  { id: 'gray', label: 'Gray', classes: 'bg-charcoal-100 dark:bg-charcoal-700 text-charcoal-600 dark:text-charcoal-300 hover:bg-charcoal-200 dark:hover:bg-charcoal-600', swatch: 'bg-charcoal-400 dark:bg-charcoal-500' },
]

export function buttonColorClasses(colorId) {
  return (BUTTON_COLORS.find(c => c.id === colorId) || BUTTON_COLORS[0]).classes
}

export const ACTION_PRESETS_BY_KIND = {
  task: [
    { value: 'mark_done', label: 'Mark Done' },
    { value: 'mark_pending', label: 'Mark Pending' },
    { value: 'mark_skipped', label: 'Mark Skipped' },
  ],
  asset: [
    { value: 'archive', label: 'Archive' },
    { value: 'unarchive', label: 'Unarchive' },
  ],
  contact: [],
  event: [],
  note: [],
}
