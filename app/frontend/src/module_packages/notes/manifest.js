// Notes' frontend manifest — discovered by src/lib/moduleRegistry.js's
// import.meta.glob. Mirrors the backend manifest's shape (same id, same
// icon-for-nav) but only carries what the frontend actually needs.
// `recordParam: 'path'` matches the pre-conversion `_CORE_RECORD_PARAM.notes`
// entry it replaces — Layout.jsx's notification-bell notes_share navTarget
// and any future ?path=<note> deep link both read it via deepLinks.js's
// generalized RECORD_PARAM merge, same treatment MODULE_ROUTES already
// gets from `to`.
export default {
  id: 'notes',
  to: '/notes',
  icon: '📝',
  label: 'Notes',
  recordParam: 'path',
  loadPage: () => import('./frontend/Notes.jsx'),
  blocks: [
    {
      type: 'note_embed',
      loadComponent: () => import('./frontend/NoteEmbedBlock.jsx'),
      icon: '📝',
      label: 'Note Embed',
      defaultLayout: { w: 12, h: 9 },
      recordKind: 'note',
      configSchema: [{ key: 'path', label: 'Note', kind: 'note' }],
    },
  ],
}
