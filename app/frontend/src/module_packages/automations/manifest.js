// Automations' frontend manifest — discovered by src/lib/moduleRegistry.js's
// import.meta.glob. Mirrors the backend manifest's shape (same id) but only
// carries what the frontend actually needs. `label` is the one forward-facing
// rename here ("n8n Automation") — id/to/route stay "automations" per the
// owner's explicit instruction to leave every internal name alone this time,
// unlike Home Assistant's full internal rename. Owns two block types
// (workflow_status, inbox_summary) — the first module to need more than one,
// which is why `blocks` is an array here and, since 2026-08-25, for every
// converted module.
//
// `navLabel` (optional, falls back to `label` everywhere it's not read) is
// a second, deliberately shorter name — Layout.jsx's mobile bottom nav bar
// is a single fixed-height flex row of ~5 items; "n8n Automation" wrapping
// to two lines there stretched the whole row taller than the other items
// (owner report, 2026-08-25). Every other surface (Mod Store, Help, the
// page's own heading, the "All Modules" drawer's roomier grid) still shows
// the full "n8n Automation" — this is the one place that needs the short
// form, not a general rename.
export default {
  id: 'automations',
  to: '/automations',
  icon: '⚙️',
  label: 'n8n Automation',
  navLabel: 'Automations',
  loadPage: () => import('./frontend/Automations.jsx'),
  blocks: [
    {
      type: 'workflow_status',
      loadComponent: () => import('./frontend/WorkflowStatusBlock.jsx'),
      icon: '⚙️',
      label: 'Automation Workflow Status',
      defaultLayout: { w: 9, h: 6 },
      configSchema: [{ key: 'workflow_id', label: 'Workflow', kind: 'workflow' }],
    },
    {
      type: 'inbox_summary',
      loadComponent: () => import('./frontend/InboxSummaryBlock.jsx'),
      icon: '📥',
      label: 'Automation Inbox Summary',
      defaultLayout: { w: 9, h: 6 },
      shape: 'list',
    },
  ],
}
