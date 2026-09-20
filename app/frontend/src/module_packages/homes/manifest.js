// Homes' frontend manifest — discovered by src/lib/moduleRegistry.js's
// import.meta.glob. Mirrors the backend manifest's shape (same id, same
// icon-for-nav) but only carries what the frontend actually needs.
export default {
  id: 'homes',
  to: '/homes',
  icon: '🏘️',
  label: 'Homes',
  recordParam: 'homeId',
  loadPage: () => import('./frontend/Homes.jsx'),
  blocks: [
    {
      type: 'home_health',
      loadComponent: () => import('./frontend/HomeHealthBlock.jsx'),
      icon: '🏘️',
      label: 'Home Health',
      defaultLayout: { w: 9, h: 9 },
      configSchema: [{ key: 'home_id', label: 'Home', kind: 'home' }],
    },
  ],
}
