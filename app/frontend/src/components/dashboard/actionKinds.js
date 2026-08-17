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
