const BASE = '/api'

function token() {
  return localStorage.getItem('lc_token')
}

function headers(extra = {}) {
  const h = { 'Content-Type': 'application/json', ...extra }
  const t = token()
  if (t) h['Authorization'] = `Bearer ${t}`
  return h
}

async function request(method, path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: headers(),
    body: body ? JSON.stringify(body) : undefined,
  })
  if (res.status === 401) {
    localStorage.removeItem('lc_token')
    localStorage.removeItem('lc_user')
    window.location.href = '/login'
    return
  }
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
  login:   (email, password) => post('/auth/login',   { email, password }),
  logout:  ()                => post('/auth/logout',  {}),
  me:      ()                => get('/auth/me'),
  today:   ()                => get('/auth/today'),
  updateSession: (session_minutes) => patch('/auth/session', { session_minutes }),
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
  send: (message, history) => post('/chat', { message, history }),
}

export const setup = {
  create: (data) => post('/setup', data),
}

export const brain = {
  list:     ()                    => get('/brain/files'),
  getFile:  (path)                => get(`/brain/files/${path}`),
  saveFile: (path, content)       => request('PUT', `/brain/files/${path}`, { content }),
}

export const admin = {
  users:             ()                          => get('/auth/users'),
  updateModules:     (userId, disabledModules)   => patch(`/auth/users/${userId}/modules`, { disabled_modules: disabledModules }),
}
