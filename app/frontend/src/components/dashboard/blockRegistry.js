import {
  AiUsageMeBlock, AiUsageOverviewBlock, CustomFieldsBlock, DocumentsBlock, DueTodayBlock,
  FinanceActivityBlock, FinanceBookReportBlock, GoalsProgressBlock, HeadingDividerBlock,
  HomeFavouritesBlock, InboxSummaryBlock, JournalEntryBlock, LinkButtonBlock, LinkedAssetsBlock,
  LinkedContactBlock, LinkedDealsBlock, LinkedTasksBlock, MyAssetsSummaryBlock, NoteEmbedBlock,
  PoolTasksBlock, RecentAiActionsBlock, SingleEventBlock, SingleTaskBlock, StreaksBlock,
  TextBlock, Top3TasksBlock, UpcomingEventsBlock, WorkflowStatusBlock,
} from './blocks'

// Frontend render-component mirror of the backend registry (services/dashboard_blocks/registry.py).
// Icon + Component + default grid size live here; admin_only/workspace gating comes from
// GET /dashboards/catalog (the backend stays the single source of truth for GATING).
export const BLOCK_REGISTRY = {
  top3_tasks: { Component: Top3TasksBlock, icon: '🎯', label: 'Top 3 Tasks', defaultLayout: { w: 4, h: 3 } },
  due_today: { Component: DueTodayBlock, icon: '📅', label: 'Due Today', defaultLayout: { w: 4, h: 3 } },
  streaks: { Component: StreaksBlock, icon: '🔥', label: 'Active Streaks', defaultLayout: { w: 4, h: 3 } },
  goals_progress: { Component: GoalsProgressBlock, icon: '🏆', label: 'Goals Progress', defaultLayout: { w: 4, h: 3 } },
  single_task: { Component: SingleTaskBlock, icon: '✅', label: 'Single Task', defaultLayout: { w: 3, h: 2 } },
  home_favourites: { Component: HomeFavouritesBlock, icon: '💡', label: 'Smart Home Favourites', defaultLayout: { w: 6, h: 3 } },
  pool_tasks: { Component: PoolTasksBlock, icon: '🧑‍🤝‍🧑', label: 'Household/Team Tasks', defaultLayout: { w: 4, h: 3 } },
  upcoming_events: { Component: UpcomingEventsBlock, icon: '📆', label: 'Upcoming Events', defaultLayout: { w: 4, h: 3 } },
  single_event: { Component: SingleEventBlock, icon: '📌', label: 'Single Event', defaultLayout: { w: 3, h: 2 } },
  finance_activity: { Component: FinanceActivityBlock, icon: '💰', label: 'Finance Activity', defaultLayout: { w: 4, h: 3 } },
  finance_book_report: { Component: FinanceBookReportBlock, icon: '📊', label: 'Finance Book Report', defaultLayout: { w: 3, h: 3 } },
  linked_deals: { Component: LinkedDealsBlock, icon: '🤝', label: 'Linked Deals', defaultLayout: { w: 4, h: 3 } },
  custom_fields: { Component: CustomFieldsBlock, icon: '🗂️', label: 'Custom Fields', defaultLayout: { w: 3, h: 3 } },
  linked_assets: { Component: LinkedAssetsBlock, icon: '🔗', label: 'Linked Assets', defaultLayout: { w: 3, h: 3 } },
  documents: { Component: DocumentsBlock, icon: '📎', label: 'Documents/Attachments', defaultLayout: { w: 3, h: 3 } },
  linked_tasks: { Component: LinkedTasksBlock, icon: '✅', label: 'Linked Tasks', defaultLayout: { w: 4, h: 3 } },
  linked_contact: { Component: LinkedContactBlock, icon: '👤', label: 'Linked Contact', defaultLayout: { w: 3, h: 2 } },
  my_assets_summary: { Component: MyAssetsSummaryBlock, icon: '🗃️', label: 'My Assets Summary', defaultLayout: { w: 4, h: 3 } },
  note_embed: { Component: NoteEmbedBlock, icon: '📝', label: 'Note Embed', defaultLayout: { w: 4, h: 3 } },
  journal_entry: { Component: JournalEntryBlock, icon: '📔', label: 'Journal Entry', defaultLayout: { w: 4, h: 3 } },
  workflow_status: { Component: WorkflowStatusBlock, icon: '⚙️', label: 'Automation Workflow Status', defaultLayout: { w: 3, h: 2 } },
  inbox_summary: { Component: InboxSummaryBlock, icon: '📥', label: 'Automation Inbox Summary', defaultLayout: { w: 3, h: 2 } },
  ai_usage_me: { Component: AiUsageMeBlock, icon: '🤖', label: 'AI Usage — My Usage', defaultLayout: { w: 3, h: 2 } },
  ai_usage_overview: { Component: AiUsageOverviewBlock, icon: '🛡️', label: 'AI Usage — All Users', defaultLayout: { w: 4, h: 3 } },
  recent_ai_actions: { Component: RecentAiActionsBlock, icon: '🕘', label: 'Recent AI Actions', defaultLayout: { w: 4, h: 3 } },
  text_block: { Component: TextBlock, icon: '📄', label: 'Text', defaultLayout: { w: 4, h: 2 } },
  link_button: { Component: LinkButtonBlock, icon: '🔘', label: 'Custom Link/Button', defaultLayout: { w: 2, h: 1 } },
  heading_divider: { Component: HeadingDividerBlock, icon: '➖', label: 'Heading/Divider', defaultLayout: { w: 4, h: 1 } },
}
