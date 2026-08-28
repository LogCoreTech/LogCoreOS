// Assets' frontend manifest — discovered by src/lib/moduleRegistry.js's
// import.meta.glob. Mirrors the backend manifest's shape (same id, same
// icon-for-nav) but only carries what the frontend actually needs.
//
// The `collection` block type folds in what used to be
// dashboard_blocks/_collections.py's separately-filed resolver (see the
// backend manifest's own comment on dashboard_block.py) — its docstring had
// anticipated future generalization to other record types, but today it's
// 100% Assets-data-dependent, so it converts with the rest of this module
// rather than staying an ungated core file for a hypothetical future need.
export default {
  id: 'assets',
  to: '/assets',
  icon: '🗂️',
  label: 'Assets',
  recordParam: 'asset',
  loadPage: () => import('./frontend/Assets.jsx'),
  blocks: [
    {
      type: 'documents',
      loadComponent: () => import('./frontend/DocumentsBlock.jsx'),
      icon: '📎',
      label: 'Asset Documents/Files',
      defaultLayout: { w: 9, h: 9 },
      configSchema: [{ key: 'asset_id', label: 'Asset', kind: 'asset' }],
    },
    {
      type: 'linked_tasks',
      loadComponent: () => import('./frontend/LinkedTasksBlock.jsx'),
      icon: '✅',
      label: "Asset's Linked Tasks",
      defaultLayout: { w: 12, h: 9 },
      shape: 'list',
      recordKind: 'task',
      configSchema: [{ key: 'asset_id', label: 'Asset', kind: 'asset' }],
    },
    {
      type: 'linked_contact',
      loadComponent: () => import('./frontend/LinkedContactBlock.jsx'),
      icon: '👤',
      label: "Asset's Linked Contact",
      defaultLayout: { w: 9, h: 6 },
      configSchema: [{ key: 'asset_id', label: 'Asset (shows its linked contact)', kind: 'asset' }],
    },
    {
      type: 'my_assets_summary',
      loadComponent: () => import('./frontend/MyAssetsSummaryBlock.jsx'),
      icon: '🗃️',
      label: 'My Assets Summary',
      defaultLayout: { w: 12, h: 9 },
      shape: 'list',
    },
    {
      type: 'collection',
      loadComponent: () => import('./frontend/CollectionBlock.jsx'),
      icon: '📋',
      label: 'Collection (List/Board)',
      defaultLayout: { w: 18, h: 12 },
      recordKind: 'asset',
      configSchema: [
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
    },
  ],
}
