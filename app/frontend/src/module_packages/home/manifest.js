// Home's frontend manifest — discovered by src/lib/moduleRegistry.js's
// import.meta.glob. Mirrors the backend manifest's shape (same id, same
// icon-for-nav) but only carries what the frontend actually needs.
export default {
  id: 'home',
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
