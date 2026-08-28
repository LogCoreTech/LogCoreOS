// Finance's frontend manifest — discovered by src/lib/moduleRegistry.js's
// import.meta.glob. Mirrors the backend manifest's shape (same id, same
// icon-for-nav) but only carries what the frontend actually needs.
//
// money.js and FinanceBookPicker.jsx both stay core (components/finance/),
// NOT moved here — money.js is a plain cents-formatting utility with 3
// external importers including an already-converted sibling module
// (AssetView.jsx), and FinanceBookPicker.jsx is only ever reached through
// core dashboard block-config infrastructure (ModuleAndRecordPicker.jsx/
// BlockPicker.jsx's own `finance` kind-map entry), never by Finance's own
// page — the same "widely shared, owned by none" reasoning
// ContactPicker.jsx/AssetTreePicker.jsx already got when Contacts/Assets
// converted.
export default {
  id: 'finance',
  to: '/finance',
  icon: '💵',
  label: 'Finance',
  recordParam: 'book',
  loadPage: () => import('./frontend/Finance.jsx'),
  blocks: [
    {
      type: 'finance_activity',
      loadComponent: () => import('./frontend/FinanceActivityBlock.jsx'),
      icon: '💰',
      label: 'Finance Activity',
      defaultLayout: { w: 12, h: 9 },
      shape: 'list',
      configSchema: [
        { key: 'asset_id', label: 'Asset', kind: 'asset', optional: true },
        { key: 'contact_id', label: 'Contact', kind: 'contact', optional: true },
        { key: 'book_id', label: 'Finance Book', kind: 'financeBook', optional: true },
      ],
    },
    {
      type: 'finance_book_report',
      loadComponent: () => import('./frontend/FinanceBookReportBlock.jsx'),
      icon: '📊',
      label: 'Finance Book Report',
      defaultLayout: { w: 9, h: 9 },
      configSchema: [{ key: 'book_id', label: 'Finance Book', kind: 'financeBook' }],
    },
  ],
}
