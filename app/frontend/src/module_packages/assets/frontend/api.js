// Assets' API client — built on the shared request/get/post/patch/del
// helpers (and BASE, for the two hand-rolled multipart/blob fetches
// requestFile()/requestBlob() in core lib/api.js don't export) exported
// from the core lib/api.js, not a reimplementation of fetch/credentials/
// header logic per module. Mirrors automations/frontend/api.js's own
// hand-rolled-multipart precedent.
import { BASE, get, post, put, patch, del } from '../../../lib/api'

function getWorkspace() {
  return localStorage.getItem('lc_ws') || 'personal'
}

async function uploadFile(path, file) {
  const fd = new FormData()
  fd.append('file', file)
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'X-Workspace': getWorkspace() },
    body: fd,
  })
  if (res.status === 401) {
    localStorage.removeItem('lc_user')
    if (!window.location.pathname.startsWith('/login')) window.location.href = '/login'
    throw new Error('Session expired. Please sign in again.')
  }
  if (res.status === 204) return null
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Request failed')
  return data
}

// Fetch a protected binary (asset attachment) as a blob — <img src> can't
// send the X-Workspace header, so images render via URL.createObjectURL.
async function fetchBlob(path) {
  const res = await fetch(`${BASE}${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', 'X-Workspace': getWorkspace() },
  })
  if (!res.ok) throw new Error('File fetch failed')
  return res.blob()
}

export const assets = {
  list:           (opts = {}) => {
    const params = new URLSearchParams()
    if (opts.template) params.set('template', opts.template)
    if (opts.includeArchived) params.set('include_archived', 'true')
    const qs = params.toString()
    return get(`/assets${qs ? `?${qs}` : ''}`)
  },
  get:            (id)              => get(`/assets/${id}`),
  create:         (data)            => post('/assets', data),
  update:         (id, data)        => patch(`/assets/${id}`, data),
  remove:         (id)              => del(`/assets/${id}`),
  archive:        (id, cascade = false) => post(`/assets/${id}/archive${cascade ? '?cascade=true' : ''}`, {}),
  unarchive:      (id, cascade = false) => post(`/assets/${id}/unarchive${cascade ? '?cascade=true' : ''}`, {}),
  members:        ()               => get('/assets/members'),
  convertToPool:  (id)              => post(`/assets/${id}/convert`, { target: 'pool' }),
  attachTemplate: (id, templateId)  => post(`/assets/${id}/attach-template`, { template_id: templateId }),
  updateAccess:   (id, data)        => put(`/assets/${id}/access`, data),
  leave:          (id)              => post(`/assets/${id}/leave`, {}),
  respondShare:   (notifId, accept) => post('/assets/shares/respond', { notif_id: notifId, accept }),
  roles:          ()               => get('/assets/roles'),
  listTemplates:  ()                => get('/assets/templates'),
  createTemplate: (data)            => post('/assets/templates', data),
  updateTemplate: (id, data)        => patch(`/assets/templates/${id}`, data),
  removeTemplate: (id)              => del(`/assets/templates/${id}`),
  templateAccess: (id, data)        => put(`/assets/templates/${id}/access`, data),
  leaveTemplate:  (id)              => post(`/assets/templates/${id}/leave`, {}),
  insertExample:  (owner = 'me')    => post(`/assets/templates/example?owner=${owner}`, {}),
  uploadFile:     (id, file)        => uploadFile(`/assets/${id}/files`, file),
  fileBlob:       (id, fileId)      => fetchBlob(`/assets/${id}/files/${fileId}`),
  removeFile:     (id, fileId)      => del(`/assets/${id}/files/${fileId}`),
  addComment:     (id, text)        => post(`/assets/${id}/comments`, { text }),
  removeComment:  (id, commentId)   => del(`/assets/${id}/comments/${commentId}`),
  setCommentsHidden: (id, hidden)   => put(`/assets/${id}/comments/visibility`, { hidden }),
  muteState:      (id)              => get(`/assets/${id}/mute`),
  setMute:        (id, muted)       => put(`/assets/${id}/mute`, { muted }),
  byContact:      (contactId)       => get(`/assets/by-contact/${contactId}`),
}
