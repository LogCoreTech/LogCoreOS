// Contacts' API client — built on the shared request/get/post/patch/del
// helpers (and BASE, for the hand-rolled multipart/blob/CSV-download
// fetches requestFile()/requestBlob()/headers() in core lib/api.js don't
// export) exported from the core lib/api.js, not a reimplementation of
// fetch/credentials/header logic per module. Mirrors automations'/assets'
// own hand-rolled-multipart precedent.
import { BASE, get, post, put, patch, del } from '../../../lib/api'

function getWorkspace() {
  return localStorage.getItem('lc_ws') || 'personal'
}

function headers(extra = {}) {
  return { 'Content-Type': 'application/json', 'X-Workspace': getWorkspace(), ...extra }
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

// Fetch a protected binary (contact photo) as a blob — <img src> can't send
// the X-Workspace header, so images render via URL.createObjectURL of this blob.
async function fetchBlob(path) {
  const res = await fetch(`${BASE}${path}`, { credentials: 'include', headers: headers() })
  if (!res.ok) throw new Error('File fetch failed')
  return res.blob()
}

export const contacts = {
  list:         (includeArchived = false) => get(`/contacts${includeArchived ? '?include_archived=true' : ''}`),
  availableForLinking: ()            => get('/contacts/available-for-linking'),
  me:           ()                  => get('/contacts/me'),
  updateMe:     (data)               => patch('/contacts/me', data),
  linkAffiliation:   (id, otherId)  => post(`/contacts/${id}/affiliations/${otherId}`, {}),
  unlinkAffiliation: (id, otherId)  => del(`/contacts/${id}/affiliations/${otherId}`),
  uploadPhoto:  (id, file)          => uploadFile(`/contacts/${id}/photo`, file),
  photoBlob:    (id)                => fetchBlob(`/contacts/${id}/photo`),
  removePhoto:  (id)                => del(`/contacts/${id}/photo`),
  get:          (id)                => get(`/contacts/${id}`),
  create:       (data)              => post('/contacts', data),
  update:       (id, data)          => patch(`/contacts/${id}`, data),
  remove:       (id)                => del(`/contacts/${id}`),
  archive:      (id)                => post(`/contacts/${id}/archive`, {}),
  unarchive:    (id)                => post(`/contacts/${id}/unarchive`, {}),
  convert:      (id)                => post(`/contacts/${id}/convert`, {}),
  convertBulk:  (contactIds = null) => post('/contacts/convert-bulk', { contact_ids: contactIds }),
  interactions: (id)                => get(`/contacts/${id}/interactions`),
  addInteraction:    (id, data)     => post(`/contacts/${id}/interactions`, data),
  updateInteraction: (id, iid, data) => patch(`/contacts/${id}/interactions/${iid}`, data),
  removeInteraction: (id, iid)      => del(`/contacts/${id}/interactions/${iid}`),
  deals:        (id)                => get(`/contacts/${id}/deals`),
  addDeal:      (id, data)          => post(`/contacts/${id}/deals`, data),
  updateDeal:   (id, did, data)     => patch(`/contacts/${id}/deals/${did}`, data),
  removeDeal:   (id, did)           => del(`/contacts/${id}/deals/${did}`),
  linkAsset:    (id, did, assetId)  => post(`/contacts/${id}/deals/${did}/assets`, { asset_id: assetId }),
  unlinkAsset:  (id, did, assetId)  => del(`/contacts/${id}/deals/${did}/assets/${assetId}`),
  getDeal:      (dealId)            => get(`/contacts/deals/${dealId}`),
  finance:      (id)                => get(`/contacts/${id}/finance`),
  pipeline:     ()                  => get('/contacts/pipeline'),
  setPipeline:  (stages)            => put('/contacts/pipeline', { stages }),
  fields:       ()                  => get('/contacts/fields'),
  setFields:    (fields)            => put('/contacts/fields', { fields }),
  updateAccess: (id, data)          => put(`/contacts/${id}/access`, data),
  respondShare: (notifId, accept)   => post('/contacts/shares/respond', { notif_id: notifId, accept }),
  leave:        (id)                => post(`/contacts/${id}/leave`, {}),
  members:      ()                  => get('/contacts/members'),
  roles:        ()                  => get('/contacts/roles'),
  csvPreview:   (file)              => uploadFile('/contacts/import/csv', file),
  csvCommit:    (rows)              => post('/contacts/import/csv/commit', { rows }),
  exportCsv:    async () => {
    const res = await fetch(`${BASE}/contacts/export/csv`, { credentials: 'include', headers: headers() })
    if (!res.ok) throw new Error('Export failed')
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'contacts.csv'
    a.click()
    URL.revokeObjectURL(url)
  },
}
