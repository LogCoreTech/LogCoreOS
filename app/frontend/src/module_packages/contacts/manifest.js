// Contacts' frontend manifest — discovered by src/lib/moduleRegistry.js's
// import.meta.glob. Mirrors the backend manifest's shape (same id, same
// icon-for-nav) but only carries what the frontend actually needs.
//
// custom_fields is deliberately NOT declared here, unlike the other 3
// contact-adjacent block types (linked_deals/contacts_list/linked_assets)
// — it genuinely reads from either contacts_service OR assets_service
// depending on which config field is set, the same "spans more than one
// module, owned by none" shape as nav_button/status_button. It stays a
// hardcoded core entry in components/dashboard/blockRegistry.js, matching
// its backend counterpart staying in dashboard_blocks/_custom_fields.py
// rather than moving into either module's own package.
//
// ContactPicker.jsx also stays core (components/contacts/ContactPicker.jsx)
// — 7 external files import it directly, including two from the
// already-converted dashboard module package, the same "widely shared,
// owned by none" reasoning AssetTreePicker.jsx got when Assets converted.
export default {
  id: 'contacts',
  to: '/contacts',
  icon: '👥',
  label: 'Contacts',
  recordParam: 'contact',
  loadPage: () => import('./frontend/Contacts.jsx'),
  blocks: [
    {
      type: 'linked_deals',
      loadComponent: () => import('./frontend/LinkedDealsBlock.jsx'),
      icon: '🤝',
      label: "Contact's Deals",
      defaultLayout: { w: 12, h: 9 },
      shape: 'list',
      configSchema: [{ key: 'contact_id', label: 'Contact', kind: 'contact' }],
    },
    {
      type: 'linked_assets',
      loadComponent: () => import('./frontend/LinkedAssetsBlock.jsx'),
      icon: '🔗',
      label: "Contact's Linked Assets",
      defaultLayout: { w: 9, h: 9 },
      shape: 'list',
      recordKind: 'asset',
      configSchema: [{ key: 'contact_id', label: 'Contact (shows the assets linked to them)', kind: 'contact' }],
    },
    {
      type: 'contacts_list',
      loadComponent: () => import('./frontend/ContactsListBlock.jsx'),
      icon: '👥',
      label: 'Contacts List',
      defaultLayout: { w: 12, h: 9 },
      shape: 'list',
      recordKind: 'contact',
    },
  ],
}
