import {
  AiUsageMeBlock, AiUsageOverviewBlock, CustomFieldsBlock, DocumentsBlock, DueTodayBlock,
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
export const BLOCK_REGISTRY = {
  top3_tasks: { Component: Top3TasksBlock, icon: '🎯', label: 'Top 3 Tasks', defaultLayout: { w: 12, h: 9 } },
  due_today: { Component: DueTodayBlock, icon: '📅', label: 'Due Today', defaultLayout: { w: 12, h: 9 } },
  streaks: { Component: StreaksBlock, icon: '🔥', label: 'Active Streaks', defaultLayout: { w: 12, h: 9 } },
  goals_progress: { Component: GoalsProgressBlock, icon: '🏆', label: 'Goals Progress', defaultLayout: { w: 12, h: 9 } },
  single_task: { Component: SingleTaskBlock, icon: '✅', label: 'Single Task', defaultLayout: { w: 9, h: 6 } },
  home_favourites: { Component: HomeFavouritesBlock, icon: '💡', label: 'Smart Home Favourites', defaultLayout: { w: 18, h: 9 } },
  pool_tasks: { Component: PoolTasksBlock, icon: '🧑‍🤝‍🧑', label: 'Household/Team Tasks', defaultLayout: { w: 12, h: 9 } },
  upcoming_events: { Component: UpcomingEventsBlock, icon: '📆', label: 'Upcoming Events', defaultLayout: { w: 12, h: 9 } },
  single_event: { Component: SingleEventBlock, icon: '📌', label: 'Single Event', defaultLayout: { w: 9, h: 6 } },
  finance_activity: { Component: FinanceActivityBlock, icon: '💰', label: 'Finance Activity', defaultLayout: { w: 12, h: 9 } },
  finance_book_report: { Component: FinanceBookReportBlock, icon: '📊', label: 'Finance Book Report', defaultLayout: { w: 9, h: 9 } },
  // Labels below spell out the data's actual source (a linked Contact or
  // Asset) rather than just the shape of what's shown — owner feedback:
  // these "record widget" names were confusing without that context. Kept
  // short since both the catalog grid and the (edit-mode-only) block header
  // truncate long labels.
  linked_deals: { Component: LinkedDealsBlock, icon: '🤝', label: "Contact's Deals", defaultLayout: { w: 12, h: 9 } },
  custom_fields: { Component: CustomFieldsBlock, icon: '🗂️', label: 'Custom Fields (Contact/Asset)', defaultLayout: { w: 9, h: 9 } },
  linked_assets: { Component: LinkedAssetsBlock, icon: '🔗', label: "Contact's Linked Assets", defaultLayout: { w: 9, h: 9 } },
  documents: { Component: DocumentsBlock, icon: '📎', label: 'Asset Documents/Files', defaultLayout: { w: 9, h: 9 } },
  linked_tasks: { Component: LinkedTasksBlock, icon: '✅', label: "Asset's Linked Tasks", defaultLayout: { w: 12, h: 9 } },
  linked_contact: { Component: LinkedContactBlock, icon: '👤', label: "Asset's Linked Contact", defaultLayout: { w: 9, h: 6 } },
  my_assets_summary: { Component: MyAssetsSummaryBlock, icon: '🗃️', label: 'My Assets Summary', defaultLayout: { w: 12, h: 9 } },
  note_embed: { Component: NoteEmbedBlock, icon: '📝', label: 'Note Embed', defaultLayout: { w: 12, h: 9 } },
  journal_entry: { Component: JournalEntryBlock, icon: '📔', label: 'Journal Entry', defaultLayout: { w: 12, h: 9 } },
  workflow_status: { Component: WorkflowStatusBlock, icon: '⚙️', label: 'Automation Workflow Status', defaultLayout: { w: 9, h: 6 } },
  inbox_summary: { Component: InboxSummaryBlock, icon: '📥', label: 'Automation Inbox Summary', defaultLayout: { w: 9, h: 6 } },
  ai_usage_me: { Component: AiUsageMeBlock, icon: '🤖', label: 'AI Usage — My Usage', defaultLayout: { w: 9, h: 6 } },
  ai_usage_overview: { Component: AiUsageOverviewBlock, icon: '🛡️', label: 'AI Usage — All Users', defaultLayout: { w: 12, h: 9 } },
  recent_ai_actions: { Component: RecentAiActionsBlock, icon: '🕘', label: 'Recent AI Actions', defaultLayout: { w: 12, h: 9 } },
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
export const CONFIG_FIELD_SCHEMAS = {
  single_task: [{ key: 'task_id', label: 'Task', kind: 'task' }],
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
  return (CONFIG_FIELD_SCHEMAS[type]?.length ?? 0) > 0
}
