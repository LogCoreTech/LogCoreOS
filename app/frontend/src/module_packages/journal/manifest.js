// Journal's frontend manifest — discovered by src/lib/moduleRegistry.js's
// import.meta.glob. Mirrors the backend manifest's shape (same id, same
// icon-for-nav) but only carries what the frontend actually needs. `blocks`
// is always an array (2026-08-25 — generalized from a singular `block` key
// once automations needed to own two block types), even for a one-block
// module like this one.
export default {
  id: 'journal',
  to: '/journal',
  icon: '📖',
  label: 'Journal',
  workspace: 'personal',
  loadPage: () => import('./frontend/Journal.jsx'),
  blocks: [
    {
      type: 'journal_entry',
      loadComponent: () => import('./frontend/JournalEntryBlock.jsx'),
      icon: '📔',
      label: 'Journal Entry',
      defaultLayout: { w: 12, h: 9 },
      configSchema: [{ key: 'date', label: 'Date', kind: 'date' }],
    },
  ],
}
