// Automations' API client — built on the shared request/get/post/patch/del
// helpers (and BASE, for the one hand-rolled multipart upload requestFile()
// doesn't support the shape of) exported from the core lib/api.js, not a
// reimplementation of fetch/credentials/header logic per module.
import { BASE, get, post, patch, del } from '../../../lib/api'

export const automations = {
  list:          (scope = 'all') => get(`/automations?scope=${scope}`),
  importFile:    async (file, name, scope, tags) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('name', name || '')
    fd.append('scope', scope || 'personal')
    fd.append('tags', JSON.stringify(tags || []))
    const res = await fetch(`${BASE}/automations/import`, { method: 'POST', credentials: 'include', body: fd })
    if (res.status === 401) {
      localStorage.removeItem('lc_user')
      if (!window.location.pathname.startsWith('/login')) window.location.href = '/login'
      throw new Error('Session expired.')
    }
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Import failed')
    return data
  },
  remove:        (id)  => del(`/automations/${id}`),
  activate:      (id)  => post(`/automations/${id}/activate`, {}),
  deactivate:    (id)  => post(`/automations/${id}/deactivate`, {}),
  run:           (id)  => post(`/automations/${id}/run`, {}),
  logs:          (id, limit = 10) => get(`/automations/${id}/logs?limit=${limit}`),
  n8nStatus:     ()    => get('/automations/n8n/status'),
  saveN8nConfig: (cfg) => post('/automations/n8n/config', cfg),
  syncSecrets:   ()    => post('/automations/n8n/sync-secrets', {}),
  syncWorkflows: ()    => post('/automations/n8n/sync-workflows', {}),
  // Automation Inbox (workspace-scoped via X-Workspace header)
  inbox:         ()                  => get('/automations/inbox'),
  createInbox:   (data)              => post('/automations/inboxes', data),
  updateInbox:   (id, data)          => patch(`/automations/inboxes/${id}`, data),
  removeInbox:   (id)                => del(`/automations/inboxes/${id}`),
  setItemStatus: (id, status, note)  => post(`/automations/inbox/items/${id}/status`, { status, note: note || null }),
  removeItem:    (id)                => del(`/automations/inbox/items/${id}`),
}
