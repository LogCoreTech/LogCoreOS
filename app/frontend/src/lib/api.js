const BASE = '/api/v1'

function headers(extra = {}) {
  return { 'Content-Type': 'application/json', ...extra }
}

async function request(method, path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: headers(),
    credentials: 'include',  // httpOnly cookie sent automatically by browser
    body: body ? JSON.stringify(body) : undefined,
  })
  if (res.status === 401) {
    localStorage.removeItem('lc_user')
    window.location.href = '/login'
    return
  }
  if (res.status === 204) return null
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Request failed')
  return data
}

const get    = (path)       => request('GET',    path)
const post   = (path, body) => request('POST',   path, body)
const patch  = (path, body) => request('PATCH',  path, body)
const del    = (path)       => request('DELETE', path)

export const auth = {
  register: (email, password, name, session_minutes) =>
    post('/auth/register', { email, password, name, session_minutes }),
  login:         (email, password) => post('/auth/login',   { email, password }),
  logout:        ()                => post('/auth/logout',  {}),
  token:         (email, password) => post('/auth/token',   { email, password }),
  me:            ()                => get('/auth/me'),
  today:         ()                => get('/auth/today'),
  status:        ()                => get('/auth/status'),
  updateSession: (session_minutes) => patch('/auth/session', { session_minutes }),
  updateMe:      (data)            => patch('/auth/me', data),
}

export const tasks = {
  list:    ()                             => get('/tasks'),
  top3:    ()                             => get('/tasks/top3'),
  scored:  ()                             => get('/tasks/scored'),
  history: (limit = 50, offset = 0)       => get(`/tasks/history?limit=${limit}&offset=${offset}`),
  add:     (task)                         => post('/tasks', task),
  update:  (id, updates)                  => patch(`/tasks/${id}`, updates),
  remove:  (id)                           => del(`/tasks/${id}`),
}

export const priorities = {
  get:      ()      => get('/priorities'),
  override: (order) => post('/priorities/override', { order }),
}

export const chat = {
  send:       (message, history)          => post('/chat',              { message, history }),
  saveMemory: (history, target = 'short') => post('/chat/save-memory',  { history, target }),
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
  updateModules:     (userId, disabledModules)   => patch(`/auth/users/${userId}/modules`, { disabled_modules: disabledModules }),
  updateUser:        (userId, data)              => patch(`/auth/users/${userId}`, data),
  updateRole:        (userId, role)              => patch(`/auth/users/${userId}/role`, { role }),
  // Registration settings
  getSettings:       ()                          => get('/auth/admin/settings'),
  updateSettings:    (s)                         => patch('/auth/admin/settings', s),
  // AI provider settings
  getAiSettings:     ()                          => get('/auth/admin/ai-settings'),
  updateAiSettings:  (s)                         => patch('/auth/admin/ai-settings', s),
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
  list:   ()               => get('/shared/tasks'),
  add:    (task)           => post('/shared/tasks', task),
  update: (id, updates)    => patch(`/shared/tasks/${id}`, updates),
  remove: (id)             => del(`/shared/tasks/${id}`),
}

export const notes = {
  list:   ()                       => get('/notes'),
  get:    (name)                   => get(`/notes/${encodeURIComponent(name)}`),
  create: (name, content = '')     => post('/notes', { name, content }),
  update: (name, content)          => request('PUT', `/notes/${encodeURIComponent(name)}`, { content }),
  remove: (name)                   => del(`/notes/${encodeURIComponent(name)}`),
}

export const journal = {
  list:   ()                => get('/journal'),
  get:    (date)            => get(`/journal/${date}`),
  upsert: (date, content)   => request('PUT', `/journal/${date}`, { content }),
  remove: (date)            => del(`/journal/${date}`),
}

export const calendar = {
  tasks: () => get('/calendar/tasks'),
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
