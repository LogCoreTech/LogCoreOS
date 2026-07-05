const BASE = '/api/v1'

function getWorkspace() {
  return localStorage.getItem('lc_ws') || 'personal'
}

function headers(extra = {}) {
  return { 'Content-Type': 'application/json', 'X-Workspace': getWorkspace(), ...extra }
}

async function request(method, path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: headers(),
    credentials: 'include',  // httpOnly cookie sent automatically by browser
    body: body ? JSON.stringify(body) : undefined,
  })
  if (res.status === 401) {
    if (!window.location.pathname.startsWith('/login')) {
      localStorage.removeItem('lc_user')
      window.location.href = '/login'
      throw new Error('Session expired. Please sign in again.')
    }
    // On the login page surface the real server error (e.g. "Invalid email or password")
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || 'Invalid credentials')
  }
  if (res.status === 204) return null
  const data = await res.json()
  if (!res.ok) {
    const detail = data.detail
    const msg = Array.isArray(detail)
      ? detail.map(e => e.msg || String(e)).join('; ')
      : (detail || 'Request failed')
    throw new Error(msg)
  }
  return data
}

const get    = (path)       => request('GET',    path)
const post   = (path, body) => request('POST',   path, body)
const patch  = (path, body) => request('PATCH',  path, body)
const del    = (path)       => request('DELETE', path)

async function requestFile(method, path, file) {
  const fd = new FormData()
  fd.append('file', file)
  const res = await fetch(`${BASE}${path}`, { method, credentials: 'include', body: fd })
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

export const auth = {
  register: (email, password, name, session_minutes) =>
    post('/auth/register', { email, password, name, session_minutes }),
  login:            (email, password) => post('/auth/login',   { email, password }),
  logout:           ()                => post('/auth/logout',  {}),
  token:            (email, password) => post('/auth/token',   { email, password }),
  me:               ()                => get('/auth/me'),
  today:            ()                => get('/auth/today'),
  status:           ()                => get('/auth/status'),
  updateSession:    (session_minutes) => patch('/auth/session', { session_minutes }),
  updateMe:         (data)            => patch('/auth/me', data),
  uploadBackground: (file)            => requestFile('POST', '/auth/me/background', file),
  deleteBackground: ()                => del('/auth/me/background'),
}

export const tasks = {
  list:     ()                             => get('/tasks'),
  top3:     ()                             => get('/tasks/top3'),
  scored:   ()                             => get('/tasks/scored'),
  assigned: ()                             => get('/tasks/assigned'),
  history:  (limit = 50, offset = 0)       => get(`/tasks/history?limit=${limit}&offset=${offset}`),
  add:      (task)                         => post('/tasks', task),
  update:   (id, updates)                  => patch(`/tasks/${id}`, updates),
  remove:   (id)                           => del(`/tasks/${id}`),
}

export const priorities = {
  get:          ()        => get('/priorities'),
  saveOverride: (order)   => post('/priorities/override', { order }),
  getPool:      ()        => get('/priorities/pool'),
  setPool:      (data)    => request('PUT', '/priorities/pool', data),
}

export const profile = {
  get:  ()     => get('/profile'),
  save: (data) => request('PUT', '/profile', data),
}

export const chat = {
  send:       (message, history, mode = 'plan', crossWorkspace = false) => post('/chat', { message, history, mode, cross_workspace: crossWorkspace }),
  saveMemory: (history, target = 'short') => post('/chat/save-memory',  { history, target }),
  saveChat:   (history, name = '', filename = '') => post('/chat/save', { history, name, filename }),
  listSaved:  ()                          => get('/chat/saved'),
  deleteSaved: (filename)                 => del(`/chat/saved/${encodeURIComponent(filename)}`),
  runs:       ()                          => get('/chat/runs'),
  getRun:     (id)                        => get(`/chat/runs/${id}`),
}

export const admin = {
  // User management
  users:             ()                          => get('/auth/users'),
  listUsers:         ()                          => get('/auth/admin/users'),
  createUser:        (u)                         => post('/auth/admin/users', u),
  updateUserRole:    (id, role)                  => patch(`/auth/admin/users/${id}`, { role }),
  deleteUser:        (id)                        => del(`/auth/admin/users/${id}`),
  updateModules:          (userId, disabledModules)          => patch(`/auth/users/${userId}/modules`, { disabled_modules: disabledModules }),
  updateWorkspaceModules: (userId, workspace, disabledModules) => patch(`/auth/admin/users/${userId}/workspace-modules`, { workspace, disabled_modules: disabledModules }),
  updateWorkspaces:       (userId, workspaces)               => patch(`/auth/admin/users/${userId}/workspaces`, { workspaces }),
  updatePoolEdit:         (userId, poolEdit)                 => patch(`/auth/admin/users/${userId}/pool-edit`, { pool_edit: poolEdit }),
  updateUser:        (userId, data)              => patch(`/auth/users/${userId}`, data),
  updateRole:        (userId, role)              => patch(`/auth/users/${userId}/role`, { role }),
  // Registration settings
  getSettings:       ()                          => get('/auth/admin/settings'),
  updateSettings:    (s)                         => patch('/auth/admin/settings', s),
  // AI provider settings
  getAiSettings:         ()    => get('/auth/admin/ai-settings'),
  updateAiSettings:      (s)   => patch('/auth/admin/ai-settings', s),
  // Web search settings
  getSearchSettings:     ()    => get('/auth/admin/search-settings'),
  updateSearchSettings:  (s)   => patch('/auth/admin/search-settings', s),
  // Hosting / tunnel settings
  getHostingSettings:    ()    => get('/auth/admin/hosting-settings'),
  updateHostingSettings: (s)   => patch('/auth/admin/hosting-settings', s),
  applyHostingSettings:  ()    => post('/auth/admin/hosting-settings/apply', {}),
}

export const setup = {
  status: ()       => get('/setup/status'),
  create: (data)   => post('/setup', data),
}

export const brain = {
  list:     ()                    => get('/brain/files'),
  getFile:  (path)                => get(`/brain/files/${path}`),
  saveFile: (path, content)       => request('PUT', `/brain/files/${path}`, { content }),
}

export const push = {
  vapidKey:    ()       => get('/push/vapid-key'),
  subscribe:   (sub)    => post('/push/subscribe', sub),
  unsubscribe: ()       => request('DELETE', '/push/subscribe'),
  test:        ()       => post('/push/test', {}),
}

export const shared = {
  list:               ()           => get('/shared/tasks'),
  add:                (task)       => post('/shared/tasks', task),
  update:             (id, upd)    => patch(`/shared/tasks/${id}`, upd),
  remove:             (id)         => del(`/shared/tasks/${id}`),
  members:            ()           => get('/shared/members'),
  sharedEvents:       ()           => get('/shared/events'),
  addSharedEvent:     (body)       => post('/shared/events', body),
  updateSharedEvent:  (id, body)   => patch(`/shared/events/${id}`, body),
  removeSharedEvent:  (id)         => del(`/shared/events/${id}`),
}

export const team = {
  list:             ()           => get('/team/tasks'),
  add:              (task)       => post('/team/tasks', task),
  update:           (id, upd)    => patch(`/team/tasks/${id}`, upd),
  remove:           (id)         => del(`/team/tasks/${id}`),
  members:          ()           => get('/team/members'),
  sharedEvents:     ()           => get('/team/events'),
  addSharedEvent:   (body)       => post('/team/events', body),
  updateSharedEvent:(id, body)   => patch(`/team/events/${id}`, body),
  removeSharedEvent:(id)         => del(`/team/events/${id}`),
}

function encodePath(path) {
  return path.split('/').map(encodeURIComponent).join('/')
}

export const notes = {
  list:         ()                            => get('/notes'),
  get:          (path)                        => get(`/notes/file/${encodePath(path)}`),
  create:       (path, content = '')          => post('/notes/file', { path, content }),
  update:       (path, content)               => request('PUT', `/notes/file/${encodePath(path)}`, { content }),
  remove:       (path)                        => del(`/notes/file/${encodePath(path)}`),
  createFolder: (path)                        => post('/notes/folder', { path }),
  removeFolder: (path)                        => del(`/notes/folder/${encodePath(path)}`),
  move:         (from_path, to_path, type)    => post('/notes/move', { from_path, to_path, type }),
}

export const journal = {
  list:   ()                => get('/journal'),
  get:    (date)            => get(`/journal/${date}`),
  upsert: (date, content)   => request('PUT', `/journal/${date}`, { content }),
  remove: (date)            => del(`/journal/${date}`),
}

export const calendar = {
  tasks:       ()           => get('/calendar/tasks'),
  events:      ()           => get('/calendar/events'),
  addEvent:    (body)       => post('/calendar/events', body),
  getEvent:    (id)         => get(`/calendar/events/${id}`),
  updateEvent: (id, body)   => patch(`/calendar/events/${id}`, body),
  removeEvent: (id)         => del(`/calendar/events/${id}`),
}

export const suggestions = {
  list:              ()    => get('/suggestions'),
  update:            (id, data) => request('PUT', `/suggestions/${id}`, data),
  run:               (id)  => post(`/suggestions/${id}/run`, {}),
  deleteCustom:      (id)  => del(`/suggestions/custom/${id}`),
  notifications:     ()    => get('/suggestions/notifications'),
  chatNotifications: ()    => get('/suggestions/notifications?delivery=chat'),
  markRead:          (id)  => post(`/suggestions/notifications/${id}/read`, {}),
  clearAll:          ()    => request('DELETE', '/suggestions/notifications'),
}

export const features = {
  get:         ()                     => get('/auth/admin/features'),
  createRole:  (name, modules)        => post('/auth/admin/features/roles', { name, modules }),
  updateRole:  (name, modules)        => patch(`/auth/admin/features/roles/${name}`, { modules }),
  deleteRole:  (name)                 => del(`/auth/admin/features/roles/${name}`),
  setUserRole: (userId, feature_role) => patch(`/auth/admin/features/users/${userId}/role`, { feature_role }),
}

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
}

export const infisical = {
  getStatus:  ()      => get('/auth/admin/infisical-status'),
  setToken:   (token) => patch('/auth/admin/infisical-token', { token }),
  clearToken: ()      => del('/auth/admin/infisical-token'),
}

export const home = {
  status:            ()                => get('/home/status'),
  saveConfig:        (cfg)             => post('/home/config', cfg),
  entities:          (domain)          => get(`/home/entities${domain ? `?domain=${domain}` : ''}`),
  entity:            (entity_id)       => get(`/home/entities/${entity_id}`),
  callService:       (entity_id, body) => post(`/home/entities/${entity_id}/call`, body),
  areas:             ()                => get('/home/areas'),
  scenes:            ()                => get('/home/scenes'),
  activateScene:     (entity_id)       => post(`/home/scenes/${entity_id}/activate`, {}),
  automations:       ()                => get('/home/automations'),
  triggerAutomation: (entity_id)       => post(`/home/automations/${entity_id}/trigger`, {}),
  getFavourites:     ()                => get('/home/favourites'),
  saveFavourites:    (entity_ids)      => request('PUT', '/home/favourites', { entity_ids }),
}

export const update = {
  status:        ()           => get('/update/status'),
  apply:         ()           => post('/update/apply', {}),
  log:           (lines = 100) => get(`/update/log?lines=${lines}`),
  patchSettings: (body)       => patch('/update/settings', body),
}

export const user = {
  async export() {
    const res = await fetch(`${BASE}/user/export`, { headers: headers(), credentials: 'include' })
    if (!res.ok) throw new Error('Export failed')
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = res.headers.get('Content-Disposition')?.match(/filename="(.+)"/)?.[1] || 'brain.zip'
    a.click()
    URL.revokeObjectURL(url)
  },
}
