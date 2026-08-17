import {
  AiUsageMeBlock, AiUsageOverviewBlock, CollectionBlock, ContactsListBlock, CustomFieldsBlock, DocumentsBlock, DueTodayBlock,
  FinanceActivityBlock, FinanceBookReportBlock, GoalsProgressBlock, HeadingDividerBlock,
  HomeFavouritesBlock, InboxSummaryBlock, JournalEntryBlock, LinkButtonBlock, LinkedAssetsBlock,
  LinkedContactBlock, LinkedDealsBlock, LinkedTasksBlock, MyAssetsSummaryBlock, NavButtonBlock,
  NoteEmbedBlock, PoolTasksBlock, RecentAiActionsBlock, SingleEventBlock, SingleTaskBlock,
  StatusButtonBlock, StreaksBlock, TextBlock, Top3TasksBlock, UpcomingEventsBlock, WorkflowStatusBlock,
} from './blocks'

// Frontend render-component mirror of the backend registry (services/dashboard_blocks/registry.py).
// Icon + Component + default grid size live here; admin_only/workspace gating comes from
// GET /dashboards/catalog (the backend stays the single source of truth for GATING).
//
// Grid units are 36 cols / 24px rows / 6px margin (see DashboardGrid.jsx) — every
// defaultLayout below is ×3 the pre-rescale values so blocks keep their original
// visual proportions on the finer grid.
// `shape` (default 'detail' when absent) tells BlockRenderer.jsx how much
// chrome the content area gets: 'list' drops the padded/bordered wrapper for
// blocks that are just rows + dividers, 'stat' is a bare number (currently
// only the Collection block's Count view), 'detail' (the default) keeps
// today's bordered card for single-record content. Owner feedback: every
// block looked like the same box regardless of what was inside it.
export const BLOCK_REGISTRY = {
  top3_tasks: { Component: Top3TasksBlock, icon: '🎯', label: 'Top 3 Tasks', defaultLayout: { w: 12, h: 9 }, shape: 'list', recordKind: 'task' },
  due_today: { Component: DueTodayBlock, icon: '📅', label: 'Due Today', defaultLayout: { w: 12, h: 9 }, shape: 'list', recordKind: 'task' },
  streaks: { Component: StreaksBlock, icon: '🔥', label: 'Active Streaks', defaultLayout: { w: 12, h: 9 }, shape: 'list', recordKind: 'task' },
  goals_progress: { Component: GoalsProgressBlock, icon: '🏆', label: 'Goals Progress', defaultLayout: { w: 12, h: 9 }, shape: 'list', recordKind: 'task' },
  single_task: { Component: SingleTaskBlock, icon: '✅', label: 'Single Task', defaultLayout: { w: 9, h: 6 }, recordKind: 'task' },
  home_favourites: { Component: HomeFavouritesBlock, icon: '💡', label: 'Smart Home Favourites', defaultLayout: { w: 18, h: 9 } },
  // No recordKind: pool tasks live in the household/team pool store, routed
  // through sharedApi/teamApi (never tasksApi) depending on t._source — and
  // Tasks.jsx's own ?task= deep-link lookup only searches the viewer's own
  // task list, not assigned pool tasks. Wiring actions here would either
  // write to the wrong store or silently no-op on nav — worse than omitting.
  pool_tasks: { Component: PoolTasksBlock, icon: '🧑‍🤝‍🧑', label: 'Household/Team Tasks', defaultLayout: { w: 12, h: 9 }, shape: 'list' },
  upcoming_events: { Component: UpcomingEventsBlock, icon: '📆', label: 'Upcoming Events', defaultLayout: { w: 12, h: 9 }, shape: 'list', recordKind: 'event' },
  single_event: { Component: SingleEventBlock, icon: '📌', label: 'Single Event', defaultLayout: { w: 9, h: 6 }, recordKind: 'event' },
  finance_activity: { Component: FinanceActivityBlock, icon: '💰', label: 'Finance Activity', defaultLayout: { w: 12, h: 9 }, shape: 'list' },
  finance_book_report: { Component: FinanceBookReportBlock, icon: '📊', label: 'Finance Book Report', defaultLayout: { w: 9, h: 9 } },
  // Labels below spell out the data's actual source (a linked Contact or
  // Asset) rather than just the shape of what's shown — owner feedback:
  // these "record widget" names were confusing without that context. Kept
  // short since both the catalog grid and the (edit-mode-only) block header
  // truncate long labels.
  linked_deals: { Component: LinkedDealsBlock, icon: '🤝', label: "Contact's Deals", defaultLayout: { w: 12, h: 9 }, shape: 'list' },
  custom_fields: { Component: CustomFieldsBlock, icon: '🗂️', label: 'Custom Fields (Contact/Asset)', defaultLayout: { w: 9, h: 9 } },
  linked_assets: { Component: LinkedAssetsBlock, icon: '🔗', label: "Contact's Linked Assets", defaultLayout: { w: 9, h: 9 }, shape: 'list', recordKind: 'asset' },
  documents: { Component: DocumentsBlock, icon: '📎', label: 'Asset Documents/Files', defaultLayout: { w: 9, h: 9 } },
  linked_tasks: { Component: LinkedTasksBlock, icon: '✅', label: "Asset's Linked Tasks", defaultLayout: { w: 12, h: 9 }, shape: 'list', recordKind: 'task' },
  linked_contact: { Component: LinkedContactBlock, icon: '👤', label: "Asset's Linked Contact", defaultLayout: { w: 9, h: 6 } },
  my_assets_summary: { Component: MyAssetsSummaryBlock, icon: '🗃️', label: 'My Assets Summary', defaultLayout: { w: 12, h: 9 }, shape: 'list' },
  // The generic block: pick a template, optionally link it to this
  // dashboard's own contact ($subject-aware like any other contact field),
  // pick which fields to show and which select field is the status — no
  // new code needed for a new use case, just configuration. See
  // dashboard_blocks/_collections.py for the resolver.
  collection: { Component: CollectionBlock, icon: '📋', label: 'Collection (List/Board)', defaultLayout: { w: 18, h: 12 }, recordKind: 'asset' },
  contacts_list: { Component: ContactsListBlock, icon: '👥', label: 'Contacts List', defaultLayout: { w: 12, h: 9 }, shape: 'list', recordKind: 'contact' },
  note_embed: { Component: NoteEmbedBlock, icon: '📝', label: 'Note Embed', defaultLayout: { w: 12, h: 9 }, recordKind: 'note' },
  journal_entry: { Component: JournalEntryBlock, icon: '📔', label: 'Journal Entry', defaultLayout: { w: 12, h: 9 } },
  workflow_status: { Component: WorkflowStatusBlock, icon: '⚙️', label: 'Automation Workflow Status', defaultLayout: { w: 9, h: 6 } },
  inbox_summary: { Component: InboxSummaryBlock, icon: '📥', label: 'Automation Inbox Summary', defaultLayout: { w: 9, h: 6 }, shape: 'list' },
  ai_usage_me: { Component: AiUsageMeBlock, icon: '🤖', label: 'AI Usage — My Usage', defaultLayout: { w: 9, h: 6 } },
  ai_usage_overview: { Component: AiUsageOverviewBlock, icon: '🛡️', label: 'AI Usage — All Users', defaultLayout: { w: 12, h: 9 }, shape: 'list' },
  recent_ai_actions: { Component: RecentAiActionsBlock, icon: '🕘', label: 'Recent AI Actions', defaultLayout: { w: 12, h: 9 }, shape: 'list' },
  text_block: { Component: TextBlock, icon: '📄', label: 'Text', defaultLayout: { w: 12, h: 6 } },
  link_button: { Component: LinkButtonBlock, icon: '🔘', label: 'Custom Link/Button', defaultLayout: { w: 6, h: 3 } },
  heading_divider: { Component: HeadingDividerBlock, icon: '➖', label: 'Heading/Divider', defaultLayout: { w: 12, h: 3 } },
  // chromeless: no card/header chrome, just the bare pill button filling the
  // grid cell (owner request: "only the pill button so there can be many of
  // them added on a small space") — BlockRenderer.jsx checks this flag.
  // Default sizes sit at the grid's own MIN_W/MIN_H floor for the same reason.
  nav_button: { Component: NavButtonBlock, icon: '➡️', label: 'Navigate To…', defaultLayout: { w: 5, h: 3 }, chromeless: true },
  status_button: { Component: StatusButtonBlock, icon: '🔄', label: 'Status/Archive Action', defaultLayout: { w: 6, h: 3 }, chromeless: true },
}

// Config field schema for record-linked / configurable block types. Each field's
// `kind` selects the picker component BlockPicker.jsx renders for it — plain
// text/textarea/date/select for genuinely free-authored values, or a real
// search/tree picker for anything that references another module's records
// (never a raw id/path typed by hand). Shared with BlockRenderer.jsx so it can
// tell whether a block type has anything worth an "edit config" affordance for.
const TASK_SORT_MODE_FIELD = {
  key: 'sort_mode',
  label: 'Sort by',
  kind: 'select',
  optional: true,
  options: [
    { value: 'priority', label: 'Priority' },
    { value: 'date', label: 'Date/Time' },
    { value: 'alpha', label: 'A–Z' },
  ],
}

export const CONFIG_FIELD_SCHEMAS = {
  single_task: [{ key: 'task_id', label: 'Task', kind: 'task' }],
  top3_tasks: [TASK_SORT_MODE_FIELD],
  due_today: [TASK_SORT_MODE_FIELD],
  finance_activity: [
    { key: 'asset_id', label: 'Asset', kind: 'asset', optional: true },
    { key: 'contact_id', label: 'Contact', kind: 'contact', optional: true },
    { key: 'book_id', label: 'Finance Book', kind: 'financeBook', optional: true },
  ],
  finance_book_report: [{ key: 'book_id', label: 'Finance Book', kind: 'financeBook' }],
  linked_deals: [{ key: 'contact_id', label: 'Contact', kind: 'contact' }],
  custom_fields: [
    { key: 'contact_id', label: 'Contact', kind: 'contact', optional: true },
    { key: 'asset_id', label: 'Asset', kind: 'asset', optional: true },
  ],
  linked_assets: [{ key: 'contact_id', label: 'Contact (shows the assets linked to them)', kind: 'contact' }],
  collection: [
    { key: 'template_id', label: 'Show records from', kind: 'assetTemplate' },
    { key: 'link_contact_id', label: 'Only ones linked to a contact', kind: 'contact', optional: true },
    { key: 'display_fields', label: 'Fields to show', kind: 'templateFields', dependsOn: 'template_id' },
    { key: 'status_field', label: 'Status field (optional — adds a one-click status control)', kind: 'templateSelectField', dependsOn: 'template_id', optional: true },
    {
      key: 'view',
      label: 'Layout',
      kind: 'select',
      options: [
        { value: 'list', label: 'List' },
        { value: 'kanban', label: 'Kanban (grouped by status)' },
        { value: 'count', label: 'Count only' },
      ],
    },
  ],
  documents: [{ key: 'asset_id', label: 'Asset', kind: 'asset' }],
  linked_tasks: [{ key: 'asset_id', label: 'Asset', kind: 'asset' }],
  linked_contact: [{ key: 'asset_id', label: 'Asset (shows its linked contact)', kind: 'asset' }],
  note_embed: [{ key: 'path', label: 'Note', kind: 'note' }],
  journal_entry: [{ key: 'date', label: 'Date', kind: 'date' }],
  single_event: [{ key: 'event_id', label: 'Event', kind: 'event' }],
  workflow_status: [{ key: 'workflow_id', label: 'Workflow', kind: 'workflow' }],
  text_block: [{ key: 'text', label: 'Text', kind: 'textarea' }],
  link_button: [
    { key: 'label', label: 'Button label', kind: 'text' },
    { key: 'url', label: 'URL (https://...)', kind: 'text' },
  ],
  heading_divider: [
    { key: 'text', label: 'Heading text (leave blank for a plain divider)', kind: 'text' },
    {
      key: 'style',
      label: 'Style',
      kind: 'select',
      options: [
        { value: 'heading', label: 'Heading' },
        { value: 'divider', label: 'Divider' },
      ],
    },
  ],
  nav_button: [
    { key: 'module', label: 'Where does this button go?', kind: 'moduleAndRecord' },
    { key: 'label', label: 'Button label (optional)', kind: 'text', optional: true },
  ],
  status_button: [
    {
      key: 'record_type',
      label: 'What kind of record?',
      kind: 'select',
      options: [
        { value: 'task', label: 'Task' },
        { value: 'contact', label: 'Contact' },
        { value: 'asset', label: 'Asset' },
      ],
    },
    { key: 'task_id', label: 'Task', kind: 'task', showIf: { key: 'record_type', equals: 'task' } },
    {
      key: 'new_status',
      label: 'Set status to',
      kind: 'select',
      options: [
        { value: 'pending', label: 'Pending' },
        { value: 'done', label: 'Done' },
        { value: 'skipped', label: 'Skipped' },
      ],
      showIf: { key: 'record_type', equals: 'task' },
    },
    { key: 'contact_id', label: 'Contact', kind: 'contact', showIf: { key: 'record_type', equals: 'contact' } },
    {
      key: 'contact_field',
      label: 'Field to update',
      kind: 'contactField',
      showIf: { key: 'record_type', equals: 'contact' },
    },
    { key: 'asset_id', label: 'Asset', kind: 'asset', showIf: { key: 'record_type', equals: 'asset' } },
    {
      key: 'asset_action',
      label: 'Action',
      kind: 'select',
      options: [
        { value: 'archive', label: 'Archive' },
        { value: 'unarchive', label: 'Unarchive' },
        { value: 'set_field', label: 'Set a field value' },
      ],
      showIf: { key: 'record_type', equals: 'asset' },
    },
    {
      key: 'select_field',
      label: 'Field to set',
      kind: 'assetSelectField',
      dependsOn: 'asset_id',
      showIf: { key: 'asset_action', equals: 'set_field' },
    },
    { key: 'label', label: 'Button label (optional)', kind: 'text', optional: true },
  ],
}

export function isConfigurable(type) {
  return (CONFIG_FIELD_SCHEMAS[type]?.length ?? 0) > 0 || !!BLOCK_REGISTRY[type]?.recordKind
}

// Block-embedded action buttons (2026-08-15) — a user-built repeater of small
// buttons on any block whose rows/subject are a real, addressable record
// (declared per block type above as `recordKind`; blocks showing aggregated
// stats instead of individual records — my_assets_summary, inbox_summary,
// ai_usage_overview, recent_ai_actions, finance_activity, linked_deals — have
// no recordKind and so never offer this, since there's no single meaningful
// "open this row" destination for an aggregate or no per-row page exists).
// See actionKinds.js for the module/preset maps (kept in their own file since
// blocks.jsx, which also needs them, can't import this file back).
export { ACTION_MODULE_BY_KIND, ACTION_PRESETS_BY_KIND } from './actionKinds'
