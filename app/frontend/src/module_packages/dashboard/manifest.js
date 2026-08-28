// Dashboards' frontend manifest — discovered by src/lib/moduleRegistry.js's
// import.meta.glob. Mirrors the backend manifest's shape (same id, same
// icon-for-nav) but only carries what the frontend actually needs.
//
// Dashboards is the third LOCKED module conversion, after Tasks and Chat —
// its backend manifest sets uninstallable=True, so ModStore.jsx always
// shows it "Always active," no uninstall button.
//
// `to: '/'` is real and load-bearing for ALL_MODULES (constants.js, the nav
// sidebar's Dashboard entry) and MODULE_ROUTES (deepLinks.js) — but
// deliberately carries NO `loadPage` field, unlike every other converted
// module. App.jsx keeps a hardcoded, unwrapped `<Route path="/" .../>` for
// this module (imported directly, not lazily) and filters MODULE_PACKAGES
// to skip generating a second, ModuleRoute-wrapped route for '/' — seeding
// a `loadPage` here that App.jsx would never call would just create an
// orphaned, never-fetched Vite chunk. See App.jsx's own comment for the
// full reasoning (a self-targeting redirect loop if this were wrapped in
// ModuleRoute the normal way).
export default {
  id: 'dashboard',
  to: '/',
  icon: '⊞',
  label: 'Dashboard',
  recordParam: 'id',
  blocks: [],
}
