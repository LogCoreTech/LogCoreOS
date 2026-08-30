// Exported (not just used internally below) so a converted module's own
// frontend/api.js can build a hand-rolled fetch (e.g. a multipart upload
// requestFile() doesn't support the exact shape of) on the same base path,
// instead of hardcoding '/api/v1' a second time.
export const BASE = '/api/v1'

function getWorkspace() {
  return localStorage.getItem('lc_ws') || 'personal'
}

function headers(extra = {}) {
  return { 'Content-Type': 'application/json', 'X-Workspace': getWorkspace(), ...extra }
}

// Re-check the session with a raw /me call (no recursion through request()).
// A single stray 401 from a data call or background poll used to hard-log-out
// the user; now we only clear the session when /me itself confirms it's dead.
let _sessionCheck = null
function sessionStillValid() {
  if (!_sessionCheck) {
    _sessionCheck = fetch(`${BASE}/auth/me`, { headers: headers(), credentials: 'include' })
      .then(r => r.status !== 401)          // 401 = genuinely expired
      .catch(() => true)                    // network blip → assume valid, don't kick
      .finally(() => { _sessionCheck = null })
  }
  return _sessionCheck
}

async function request(method, path, body, extraHeaders) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: headers(extraHeaders),
    credentials: 'include',  // httpOnly cookie sent automatically by browser
    body: body ? JSON.stringify(body) : undefined,
  })
  if (res.status === 401) {
    if (window.location.pathname.startsWith('/login')) {
      // On the login page surface the real server error (e.g. "Invalid email or password")
      const data = await res.json().catch(() => ({}))
      throw new Error(data.detail || 'Invalid credentials')
    }
    // Verify before nuking the session — a lone 401 is often transient.
    if (path === '/auth/me' || !(await sessionStillValid())) {
      localStorage.removeItem('lc_user')
      window.location.href = '/login'
      throw new Error('Session expired. Please sign in again.')
    }
    throw new Error('Request failed — please try again.')
  }
  if (res.status === 204) return null
  // A non-JSON body (a proxy's own error page, a bare-text 500 from
  // somewhere outside this app's own JSON error handling) must not surface
  // as an opaque JSON.parse failure — Safari in particular throws its own
  // "The string did not match the expected pattern." for invalid JSON,
  // which reads as a mystery error with zero indication anything server-side
  // went wrong (found via a real push-notification bug, 2026-08-15).
  let data
  try {
    data = await res.json()
  } catch {
    throw new Error(res.ok ? 'Unexpected response from server.' : `Request failed (${res.status}).`)
  }
  if (!res.ok) {
    const detail = data.detail
    const msg = Array.isArray(detail)
      ? detail.map(e => e.msg || String(e)).join('; ')
      : (detail || 'Request failed')
    throw new Error(msg)
  }
  return data
}

// Exported (not just used internally below) so a converted module's own
// frontend/api.js — e.g. module_packages/journal/frontend/api.js — can build
// its client on the same session-handling/error-normalization logic instead
// of duplicating fetch/credentials/header code per module.
export const get    = (path)       => request('GET',    path)
export const post   = (path, body) => request('POST',   path, body)
export const put    = (path, body) => request('PUT',    path, body)
export const patch  = (path, body) => request('PATCH',  path, body)
export const del    = (path)       => request('DELETE', path)

async function requestFile(method, path, file) {
  const fd = new FormData()
  fd.append('file', file)
  // No Content-Type header — the browser sets the multipart boundary itself
  const res = await fetch(`${BASE}${path}`, {
    method,
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

export const auth = {
  register: (email, password, name, session_minutes) =>
    post('/auth/register', { email, password, name, session_minutes }),
  login:            (email, password) => post('/auth/login',   { email, password }),
  logout:           ()                => post('/auth/logout',  {}),
  token:            (email, password) => post('/auth/token',   { email, password }),
  me:               ()                => get('/auth/me'),
  today:            ()                => get('/auth/today'),
  status:           ()                => get('/auth/status'),
  updateMe:         (data)            => patch('/auth/me', data),
  rotateChannel:    ()                => post('/auth/me/rotate-channel', {}),
  uploadBackground: (file)            => requestFile('POST', '/auth/me/background', file),
  deleteBackground: ()                => del('/auth/me/background'),
}

export const help = {
  content:       ()     => get('/help/content'),
  whatsNew:      ()     => get('/help/whats-new'),
  getOnboarding: ()     => get('/help/onboarding'),
  setOnboarding: (data) => put('/help/onboarding', data),
}

export const priorities = {
  get:          ()        => get('/priorities'),
  saveOverride: (order)   => post('/priorities/override', { order }),
  getPool:      ()        => get('/priorities/pool'),
  setPool:      (data)    => request('PUT', '/priorities/pool', data),
}

// Shared tag vocabulary for Goals + Tasks (2026-08-29) — see
// services/tags_service.py's own docstring for why this stays core.
export const tags = {
  list: (pool = false) => get(`/tags?pool=${pool}`),
}

// App-wide search fan-out (2026-08-29) — see services/search_service.py's
// own docstring for why this stays core, same shape as `tags` above.
export const search = {
  query: (q, tags = []) => {
    const params = new URLSearchParams()
    if (q) params.set('q', q)
    for (const t of tags) params.append('tags', t)
    return get(`/search?${params.toString()}`)
  },
}

export const admin = {
  // User management
  users:             ()                          => get('/auth/users'),
  listUsers:         ()                          => get('/auth/admin/users'),
  createUser:        (u)                         => post('/auth/admin/users', u),
  updateUserRole:    (id, role)                  => patch(`/auth/admin/users/${id}`, { role }),
  deleteUser:        (id)                        => del(`/auth/admin/users/${id}`),
  deletionPreview:   (id)                        => get(`/auth/admin/users/${id}/deletion-preview`),
  deletionExecute:   (id, decisions)              => post(`/auth/admin/users/${id}/deletion-execute`, { decisions }),
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
  // Automation token (n8n -> LogCore write API) — core-owned since admins
  // must keep token access regardless of whether Assets (or any other
  // module the token authenticates writes into) is installed.
  automationToken:       ()    => get('/auth/admin/automation-token'),
  rotateAutomationToken: ()    => post('/auth/admin/automation-token/rotate', {}),
}

export const aiUsage = {
  overview:         (month)            => get(`/ai-usage/overview${month ? `?month=${month}` : ''}`),
  users:            (month)            => get(`/ai-usage/users${month ? `?month=${month}` : ''}`),
  getDefaults:      ()                 => get('/ai-usage/defaults'),
  updateDefaults:   (body)             => patch('/ai-usage/defaults', body),
  updateUserLimits: (userId, body)     => patch(`/ai-usage/users/${userId}/limits`, body),
  me:               ()                 => get('/ai-usage/me'),
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

// App-wide online/offline presence (2026-08-17) — Layout.jsx pings this on
// an interval while any page is open and visible. Distinct from
// chat.presence above, which is a per-conversation "I'm looking at this
// exact chat" signal for suppressing a redundant notification, not a
// general online/offline status.
export const presence = {
  ping: () => post('/presence/ping'),
}

export const push = {
  vapidKey:    ()       => get('/push/vapid-key'),
  subscribe:   (sub)    => post('/push/subscribe', sub),
  unsubscribe: ()       => request('DELETE', '/push/subscribe'),
  test:        ()       => post('/push/test', {}),
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
  roleUsers:   (name)                 => get(`/auth/admin/features/roles/${name}/users`),
  setUserRole: (userId, feature_role) => patch(`/auth/admin/features/users/${userId}/role`, { feature_role }),
}

export const infisical = {
  getStatus:  ()      => get('/auth/admin/infisical-status'),
  setToken:   (token) => patch('/auth/admin/infisical-token', { token }),
  clearToken: ()      => del('/auth/admin/infisical-token'),
}

export const update = {
  status:        ()           => get('/update/status'),
  check:         ()           => post('/update/check', {}),
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

export const modStore = {
  catalog:    ()             => get('/mod-store/catalog'),
  installed:  ()             => get('/mod-store/installed'),
  active:     ()             => get('/mod-store/active'),
  install:    (id)           => post(`/mod-store/install/${id}`, {}),
  uninstall:  (id)           => post(`/mod-store/uninstall/${id}`, {}),
  // Bypasses the generic request() helper deliberately: a 409 here means
  // "other users are online, confirm before proceeding" — an expected,
  // structured response ({message, online_users}) the caller should branch
  // on, not a string error. request()'s generic error handling only knows
  // how to stringify an array or plain-string `detail`; an object detail
  // would collapse to the useless "[object Object]".
  async restart(force = false) {
    const res = await fetch(`${BASE}/mod-store/restart`, {
      method: 'POST',
      headers: headers(),
      credentials: 'include',
      body: JSON.stringify({ force }),
    })
    const data = await res.json().catch(() => ({}))
    if (res.status === 409) {
      return {
        ok: false,
        conflict: true,
        onlineUsers: data.detail?.online_users || [],
        message: data.detail?.message || 'Other users are currently online.',
      }
    }
    if (!res.ok) {
      throw new Error(data.detail || 'Restart failed — check server logs.')
    }
    return { ok: true, conflict: false, ...data }
  },
}
