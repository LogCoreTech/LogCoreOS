// Home Assistant's frontend manifest — discovered by src/lib/moduleRegistry.js's
// import.meta.glob. Mirrors the backend manifest's shape (same id, same
// icon-for-nav) but only carries what the frontend actually needs. `id`
// renamed from 'home' to 'home_assistant' 2026-08-24 (matches the backend
// manifest's id); `to` renamed the same day from '/home' to '/home-assistant'
// (hyphenated, matching this app's own multi-word-route convention — see
// '/settings/admin/mod-store', '/settings/admin/contact-fields' — not the
// id's own snake_case); block.type renamed from 'home_favourites' to
// 'home_assistant_favourites' (snake_case, matching every other block type's
// own convention — journal_entry, pool_tasks, contacts_list — a migration,
// migrations/runner.py's m018, carries this forward for anyone who'd already
// added the old block to a real dashboard).
export default {
  id: 'home_assistant',
  to: '/home-assistant',
  icon: '💡',
  label: 'Home Assistant',
  workspace: 'personal',
  loadPage: () => import('./frontend/Home.jsx'),
  // Array (2026-08-25 — generalized from a singular `block` key once
  // automations needed to own two block types), even for a one-block module.
  blocks: [
    {
      type: 'home_assistant_favourites',
      loadComponent: () => import('./frontend/HomeFavouritesBlock.jsx'),
      icon: '💡',
      label: 'Home Assistant Favourites',
      defaultLayout: { w: 18, h: 9 },
    },
  ],
}
