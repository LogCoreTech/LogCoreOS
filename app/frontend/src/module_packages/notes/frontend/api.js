import { get, post, put, del } from '../../../lib/api'

// Small local copy of lib/api.js's own encodePath — that file keeps its
// original for assets (not yet converted); duplicating one three-line pure
// helper here is the same trade-off Household/Team made keeping their own
// small priorityDot/Empty copies rather than sharing a one-off across
// packages.
function encodePath(path) {
  return path.split('/').map(encodeURIComponent).join('/')
}

export const notes = {
  list:         (includeArchived = false)  => get(`/notes${includeArchived ? '?include_archived=true' : ''}`),
  setArchived:  (path, archived = true)    => post('/notes/archive', { path, archived }),
  setTags:      (path, tags)               => put('/notes/tags', { path, tags }),
  get:          (path)                     => get(`/notes/file/${encodePath(path)}`),
  create:       (path, content = '')       => post('/notes/file', { path, content }),
  update:       (path, content)            => put(`/notes/file/${encodePath(path)}`, { content }),
  remove:       (path)                     => del(`/notes/file/${encodePath(path)}`),
  createFolder: (path)                     => post('/notes/folder', { path }),
  removeFolder: (path)                     => del(`/notes/folder/${encodePath(path)}`),
  move:         (from_path, to_path, type) => post('/notes/move', { from_path, to_path, type }),
  updateAccess: (data)                     => put('/notes/access', data),
  respondShare: (notifId, accept)          => post('/notes/shares/respond', { notif_id: notifId, accept }),
  leave:        (path)                     => post('/notes/leave', { path }),
  members:      ()                         => get('/notes/members'),
  roles:        ()                         => get('/notes/roles'),
}
