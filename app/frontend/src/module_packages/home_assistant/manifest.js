// Home Assistant's frontend manifest — discovered by src/lib/moduleRegistry.js's
// import.meta.glob. Mirrors the backend manifest's shape (same id, same
// icon-for-nav) but only carries what the frontend actually needs. `id`
// renamed from 'home' to 'home_assistant' 2026-08-24 (matches the backend
// manifest's id) — `to` deliberately kept as '/home', not renamed, since
// the URL a user actually navigates to/bookmarks is a different, more
// user-visible thing than the module's internal id (see docs/MEMORY.md).
export default {
  id: 'home_assistant',
  to: '/home',
  icon: '💡',
  label: 'Home Assistant',
  workspace: 'personal',
  loadPage: () => import('./frontend/Home.jsx'),
  block: {
    type: 'home_favourites',
    loadComponent: () => import('./frontend/HomeFavouritesBlock.jsx'),
    icon: '💡',
    label: 'Home Assistant Favourites',
    defaultLayout: { w: 18, h: 9 },
  },
}
