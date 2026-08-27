// Chat's frontend manifest — discovered by src/lib/moduleRegistry.js's
// import.meta.glob. Mirrors the backend manifest's shape (same id, same
// icon-for-nav) but only carries what the frontend actually needs.
//
// Chat is the second LOCKED module conversion, after Tasks — its backend
// manifest sets uninstallable=True, so ModStore.jsx always shows it "Always
// active," no uninstall button. `recordParam: 'chat_id'` is real (unlike
// Automations, which declares none) — Layout.jsx's notification-bell
// `open_chat` navTarget case reads it via deepLinks.js's RECORD_PARAM merge,
// the same treatment MODULE_ROUTES already gets from `to`. No `blocks`
// array — Chat owns no dashboard block type, the first converted module
// (out of 8) to declare none at all.
export default {
  id: 'chat',
  to: '/chat',
  icon: '◈',
  label: 'AI Chat',
  recordParam: 'chat_id',
  loadPage: () => import('./frontend/Chat.jsx'),
  blocks: [],
}
