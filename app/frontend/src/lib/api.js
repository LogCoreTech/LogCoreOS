const BASE = '/api'

async function request(method, path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
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

const get  = (path)        => request('GET',    path)
const post = (path, body)  => request('POST',   path, body)
const patch = (path, body) => request('PATCH',  path, body)
const del  = (path)        => request('DELETE', path)

export const auth = {
  register: (email, password, name) => post('/auth/register', { email, password, name }),
  login:    (email, password)       => post('/auth/login',    { email, password }),
  logout:   ()                      => post('/auth/logout'),
  me:       ()                      => get('/auth/me'),
}

export const tasks = {
  list:    ()                    => get('/tasks'),
  top3:    ()                    => get('/tasks/top3'),
  scored:  ()                    => get('/tasks/scored'),
  history: ()                    => get('/tasks/history'),
  add:     (task)                => post('/tasks', task),
  update:  (id, updates)         => patch(`/tasks/${id}`, updates),
  remove:  (id)                  => del(`/tasks/${id}`),
}

export const priorities = {
  get:      ()      => get('/priorities'),
  override: (order) => post('/priorities/override', { order }),
}

export const chat = {
  send:       (message, history) => post('/chat', { message, history }),
  saveMemory: (history, target = 'short') => post('/chat/save-memory', { history, target }),
  runs:       ()                 => get('/chat/runs'),
  getRun:     (id)               => get(`/chat/runs/${id}`),
}

export const admin = {
  getAiSettings:        ()          => get('/auth/admin/ai-settings'),
  updateAiSettings:     (s)         => patch('/auth/admin/ai-settings', s),
  listUsers:            ()          => get('/auth/admin/users'),
  createUser:           (u)         => post('/auth/admin/users', u),
  updateUserRole:       (id, role)  => patch(`/auth/admin/users/${id}`, { role }),
  deleteUser:           (id)        => del(`/auth/admin/users/${id}`),
  getSettings:          ()          => get('/auth/admin/settings'),
  updateSettings:       (s)         => patch('/auth/admin/settings', s),
}

export const setup = {
  create: (data) => post('/setup', data),
}
