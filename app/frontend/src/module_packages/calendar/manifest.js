// Calendar's frontend manifest — discovered by src/lib/moduleRegistry.js's
// import.meta.glob. Mirrors the backend manifest's shape (same id, same
// icon-for-nav) but only carries what the frontend actually needs.
// Deliberately narrow move, same shape as Automations: id/to/route stay
// "calendar" — no rename requested. `recordParam` is new (2026-08-25,
// the first converting module with an actual `?event=<id>` deep-link
// handler) — read by deepLinks.js's RECORD_PARAM merge, the same treatment
// MODULE_ROUTES already gets from this file's `to`.
export default {
  id: 'calendar',
  to: '/calendar',
  icon: '📅',
  label: 'Calendar',
  recordParam: 'event',
  loadPage: () => import('./frontend/Calendar.jsx'),
  blocks: [
    {
      type: 'upcoming_events',
      loadComponent: () => import('./frontend/UpcomingEventsBlock.jsx'),
      icon: '📆',
      label: 'Upcoming Events',
      defaultLayout: { w: 12, h: 9 },
      shape: 'list',
      recordKind: 'event',
    },
    {
      type: 'single_event',
      loadComponent: () => import('./frontend/SingleEventBlock.jsx'),
      icon: '📌',
      label: 'Single Event',
      defaultLayout: { w: 9, h: 6 },
      recordKind: 'event',
      configSchema: [{ key: 'event_id', label: 'Event', kind: 'event' }],
    },
  ],
}
