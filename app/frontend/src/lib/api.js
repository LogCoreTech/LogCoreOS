const BASE = '/api/v1'

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

// Fetch a protected binary (e.g. asset attachment) as a blob — <img src> can't send
// the X-Workspace header, so images render via URL.createObjectURL of this blob.
async function requestBlob(path) {
  const res = await fetch(`${BASE}${path}`, { credentials: 'include', headers: headers() })
  if (!res.ok) throw new Error('File fetch failed')
  return res.blob()
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

export const tasks = {
  list:     ()                             => get('/tasks'),
  top3:     ()                             => get('/tasks/top3'),
  scored:   ()                             => get('/tasks/scored'),
  assigned: ()                             => get('/tasks/assigned'),
  history:  (limit = 50, offset = 0)       => get(`/tasks/history?limit=${limit}&offset=${offset}`),
  add:      (task)                         => post('/tasks', task),
  update:   (id, updates)                  => patch(`/tasks/${id}`, updates),
  remove:   (id)                           => del(`/tasks/${id}`),
  cleanupGoals: ()                         => post('/tasks/goals/cleanup', {}),
}

export const priorities = {
  get:          ()        => get('/priorities'),
  saveOverride: (order)   => post('/priorities/override', { order }),
  getPool:      ()        => get('/priorities/pool'),
  setPool:      (data)    => request('PUT', '/priorities/pool', data),
}

export const chat = {
  send:       (chatId, message, history, mode = 'approve', crossWorkspace = false, acceptOverage = false) => post('/chat', { chat_id: chatId, message, history, mode, cross_workspace: crossWorkspace, accept_overage: acceptOverage }),
  // Replays/answers a paused turn (approve/decline a pending write, or answer a
  // question) instead of sending a new message — see docs/MEMORY.md 2026-08-09.
  resume:     (chatId, runId, decision, history, crossWorkspace = false, answer = null) => post('/chat', { chat_id: chatId, history, cross_workspace: crossWorkspace, resume: { run_id: runId, decision, answer } }),
  saveMemory: (history, target = 'short') => post('/chat/save-memory',  { history, target }),
  saveChat:   (history, name = '', filename = '') => post('/chat/save', { history, name, filename }),
  listSaved:  ()                          => get('/chat/saved'),
  deleteSaved: (filename)                 => del(`/chat/saved/${encodeURIComponent(filename)}`),
  // One entry per conversation (status + unread), backing the "Chats" list —
  // see docs/MEMORY.md 2026-08-15 for why this replaced /saved as the
  // sidebar's source.
  sessions:    ()                         => get('/chat/sessions'),
  markSessionRead: (chatId)               => post(`/chat/sessions/${encodeURIComponent(chatId)}/read`),
  // The live pending_write/pending_question/pending_plan card for a
  // conversation (run_id/mode/steps), if it currently has one — re-attached
  // onto the last message when reopening a session whose own status is
  // awaiting_approval/awaiting_answer, since the saved .md archive itself
  // has no structured step data (2026-08-15).
  pending:    (chatId)                    => get(`/chat/pending/${encodeURIComponent(chatId)}`),
  // Tells the server "I'm still looking at this conversation" so a
  // completion/approval notification isn't also sent while it's already
  // visible live — see docs/MEMORY.md 2026-08-15.
  presence:   (chatId)                    => post('/chat/presence', { chat_id: chatId }),
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
  updateAccess:   (id, data)        => request('PUT', `/assets/${id}/access`, data),
  leave:          (id)              => post(`/assets/${id}/leave`, {}),
  respondShare:   (notifId, accept) => post('/assets/shares/respond', { notif_id: notifId, accept }),
  roles:          ()               => get('/assets/roles'),
  listTemplates:  ()                => get('/assets/templates'),
  createTemplate: (data)            => post('/assets/templates', data),
  updateTemplate: (id, data)        => patch(`/assets/templates/${id}`, data),
  removeTemplate: (id)              => del(`/assets/templates/${id}`),
  templateAccess: (id, data)        => request('PUT', `/assets/templates/${id}/access`, data),
  leaveTemplate:  (id)              => post(`/assets/templates/${id}/leave`, {}),
  insertExample:  (owner = 'me')    => post(`/assets/templates/example?owner=${owner}`, {}),
  uploadFile:     (id, file)        => requestFile('POST', `/assets/${id}/files`, file),
  fileBlob:       (id, fileId)      => requestBlob(`/assets/${id}/files/${fileId}`),
  removeFile:     (id, fileId)      => del(`/assets/${id}/files/${fileId}`),
  addComment:     (id, text)        => post(`/assets/${id}/comments`, { text }),
  removeComment:  (id, commentId)   => del(`/assets/${id}/comments/${commentId}`),
  setCommentsHidden: (id, hidden)   => request('PUT', `/assets/${id}/comments/visibility`, { hidden }),
  muteState:      (id)              => get(`/assets/${id}/mute`),
  setMute:        (id, muted)       => request('PUT', `/assets/${id}/mute`, { muted }),
  byContact:      (contactId)       => get(`/assets/by-contact/${contactId}`),
  automationToken:       ()         => get('/assets/automation/token'),
  rotateAutomationToken: ()         => post('/assets/automation/token/rotate', {}),
}

export const finance = {
  listBooks:    (includeArchived = false) => get(`/finance/books${includeArchived ? '?include_archived=true' : ''}`),
  // Admin pool pages (Household/Team) need the pool's own books regardless of
  // the viewing admin's own personal/business workspace toggle — household
  // pool books always live in "personal", team's always in "business".
  listBooksForWorkspace: (workspace) => request('GET', '/finance/books', undefined, { 'X-Workspace': workspace }),
  getPrefs:     ()                        => get('/finance/prefs'),
  setLastBook:  (bookId)                  => put('/finance/prefs', { last_book_id: bookId }),
  createBook:   (data)                    => post('/finance/books', data),
  getBook:      (id)                      => get(`/finance/books/${id}`),
  updateBook:   (id, data)                => patch(`/finance/books/${id}`, data),
  removeBook:   (id)                      => del(`/finance/books/${id}`),
  addAccount:   (bookId, data)            => post(`/finance/books/${bookId}/accounts`, data),
  updateAccount:(bookId, id, data)        => patch(`/finance/books/${bookId}/accounts/${id}`, data),
  removeAccount:(bookId, id)              => del(`/finance/books/${bookId}/accounts/${id}`),
  transactions: (bookId, opts = {}) => {
    const params = new URLSearchParams()
    if (opts.from) params.set('from', opts.from)
    if (opts.to) params.set('to', opts.to)
    if (opts.account) params.set('account', opts.account)
    if (opts.category !== undefined && opts.category !== null) params.set('category', opts.category)
    if (opts.q) params.set('q', opts.q)
    if (opts.limit) params.set('limit', opts.limit)
    if (opts.offset) params.set('offset', opts.offset)
    const qs = params.toString()
    return get(`/finance/books/${bookId}/transactions${qs ? `?${qs}` : ''}`)
  },
  addTransaction:    (bookId, data)     => post(`/finance/books/${bookId}/transactions`, data),
  updateTransaction: (bookId, id, data) => patch(`/finance/books/${bookId}/transactions/${id}`, data),
  removeTransaction: (bookId, id)       => del(`/finance/books/${bookId}/transactions/${id}`),
  monthlyReport:     (bookId, month)    => get(`/finance/books/${bookId}/reports/monthly?month=${month}`),
  netWorth:          ()                 => get('/finance/networth'),
  assetTransactions: (assetId)          => get(`/finance/assets/${assetId}/transactions`),
  dealInvoices:      (dealId)           => get(`/finance/deals/${dealId}/invoices`),
  pnl: (bookId, opts) => {
    const params = new URLSearchParams({ year: opts.year, period: opts.period || 'year' })
    if (opts.quarter) params.set('quarter', opts.quarter)
    if (opts.month) params.set('month', opts.month)
    return get(`/finance/books/${bookId}/reports/pnl?${params}`)
  },
  taxSummary: (bookId, year) => get(`/finance/books/${bookId}/reports/tax?year=${year}`),
  taxCsv: async (bookId, year) => {
    const res = await fetch(`${BASE}/finance/books/${bookId}/reports/tax?year=${year}&format=csv`, {
      credentials: 'include', headers: headers(),
    })
    if (!res.ok) throw new Error('Export failed')
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `tax_${year}.csv`
    a.click()
    URL.revokeObjectURL(url)
  },
  // Clients + invoices + payments (accounts receivable)
  clients:       (bookId)            => get(`/finance/books/${bookId}/clients`),
  addClient:     (bookId, data)      => post(`/finance/books/${bookId}/clients`, data),
  updateClient:  (bookId, id, data)  => patch(`/finance/books/${bookId}/clients/${id}`, data),
  removeClient:  (bookId, id)        => del(`/finance/books/${bookId}/clients/${id}`),
  arSummary:     (bookId)            => get(`/finance/books/${bookId}/clients/ar`),
  invoices:      (bookId)            => get(`/finance/books/${bookId}/invoices`),
  createInvoice: (bookId, data)      => post(`/finance/books/${bookId}/invoices`, data),
  updateInvoice: (bookId, id, data)  => patch(`/finance/books/${bookId}/invoices/${id}`, data),
  removeInvoice: (bookId, id)        => del(`/finance/books/${bookId}/invoices/${id}`),
  recordPayment: (bookId, invId, data) => post(`/finance/books/${bookId}/invoices/${invId}/payments`, data),
  removePayment: (bookId, invId, payId) => del(`/finance/books/${bookId}/invoices/${invId}/payments/${payId}`),
  // Receipts on transactions
  uploadReceipt: (bookId, txId, file)      => requestFile('POST', `/finance/books/${bookId}/transactions/${txId}/receipts`, file),
  receiptBlob:   (bookId, txId, receiptId) => requestBlob(`/finance/books/${bookId}/transactions/${txId}/receipts/${receiptId}`),
  removeReceipt: (bookId, txId, receiptId) => del(`/finance/books/${bookId}/transactions/${txId}/receipts/${receiptId}`),
  // Planning: budgets, recurring, planned, projection
  budgets:           (bookId)           => get(`/finance/books/${bookId}/budgets`),
  setBudgets:        (bookId, budgets)  => request('PUT', `/finance/books/${bookId}/budgets`, { budgets }),
  budgetStatus:      (bookId, month)    => get(`/finance/books/${bookId}/budgets/status?month=${month}`),
  recurring:         (bookId)           => get(`/finance/books/${bookId}/recurring`),
  upcomingRecurring: (bookId, days = 30) => get(`/finance/books/${bookId}/recurring/upcoming?days=${days}`),
  addRecurring:      (bookId, data)     => post(`/finance/books/${bookId}/recurring`, data),
  updateRecurring:   (bookId, id, data) => patch(`/finance/books/${bookId}/recurring/${id}`, data),
  removeRecurring:   (bookId, id)       => del(`/finance/books/${bookId}/recurring/${id}`),
  planned:           (bookId)           => get(`/finance/books/${bookId}/planned`),
  addPlanned:        (bookId, data)     => post(`/finance/books/${bookId}/planned`, data),
  updatePlanned:     (bookId, id, data) => patch(`/finance/books/${bookId}/planned/${id}`, data),
  removePlanned:     (bookId, id)       => del(`/finance/books/${bookId}/planned/${id}`),
  projection:        (bookId, accountId, date) => get(`/finance/books/${bookId}/accounts/${accountId}/projection?date=${date}`),
  // Transfers — a linked pair of transactions moving money between two
  // accounts (same book or cross-book, same or cross-workspace). Doesn't
  // depend on the ambient X-Workspace header — from_workspace/to_workspace
  // are always sent explicitly since either side could be in either workspace.
  createTransfer: (data)                       => post('/finance/transfers', data),
  updateTransfer: (transferPairId, data)       => patch(`/finance/transfers/${transferPairId}`, data),
  removeTransfer: (transferPairId, params)     => del(`/finance/transfers/${transferPairId}?${new URLSearchParams(params)}`),
  // Sharing (book audience + per-account overrides + handshake)
  updateBookAccess:    (bookId, data)            => request('PUT', `/finance/books/${bookId}/access`, data),
  updateAccountAccess: (bookId, accountId, data) => request('PUT', `/finance/books/${bookId}/accounts/${accountId}/access`, data),
  respondShare:        (notifId, accept)         => post('/finance/shares/respond', { notif_id: notifId, accept }),
  leaveBook:           (bookId)                  => post(`/finance/books/${bookId}/leave`, {}),
  members:             ()                        => get('/finance/members'),
  roles:               ()                        => get('/finance/roles'),
  // SimpleFIN bank sync (connections are admin-managed; members request + map)
  sfStatus:      ()        => get('/finance/simplefin/status'),
  sfAccounts:    ()        => get('/finance/simplefin/accounts'),
  sfRequest:     ()        => post('/finance/simplefin/request', {}),
  sfSetMapping:  (entries) => request('PUT', '/finance/simplefin/mapping', { entries }),
  sfConnections: ()        => get('/finance/simplefin/connections'),
  sfPoolSummary: (pool)    => get(`/finance/simplefin/pool-summary?pool=${pool}`),
  sfClaim:       (userId, setupToken) => post('/finance/simplefin/claim', { user_id: userId, setup_token: setupToken }),
  sfReveal:      (userId)  => post('/finance/simplefin/reveal', { user_id: userId }),
  sfDisconnect:  (userId)  => del(`/finance/simplefin/${userId}`),
  sfSync:        (userId)  => post('/finance/simplefin/sync', { user_id: userId }),
  // Pool-owned SimpleFIN connection (joint/family account, not tied to any one member)
  sfPoolStatus:      (pool)               => get(`/finance/simplefin/pool/${pool}/status`),
  sfPoolAccounts:    (pool)               => get(`/finance/simplefin/pool/${pool}/accounts`),
  sfPoolSetMapping:  (pool, entries)      => request('PUT', `/finance/simplefin/pool/${pool}/mapping`, { entries }),
  sfPoolClaim:       (pool, setupToken)   => post(`/finance/simplefin/pool/${pool}/claim`, { setup_token: setupToken }),
  sfPoolReveal:      (pool)               => post(`/finance/simplefin/pool/${pool}/reveal`, {}),
  sfPoolDisconnect:  (pool)               => del(`/finance/simplefin/pool/${pool}`),
  sfPoolSync:        (pool)               => post(`/finance/simplefin/pool/${pool}/sync`, {}),
  // Payee → category rules + CSV import
  rules:      (bookId)         => get(`/finance/books/${bookId}/rules`),
  removeRule: (bookId, ruleId) => del(`/finance/books/${bookId}/rules/${ruleId}`),
  csvPreview: (bookId, file)   => requestFile('POST', `/finance/books/${bookId}/import/csv`, file),
  csvCommit:  async (bookId, file, mapping) => {
    const fd = new FormData()
    fd.append('file', file)
    for (const [k, v] of Object.entries(mapping)) {
      if (v !== undefined && v !== null) fd.append(k, v)
    }
    const res = await fetch(`${BASE}/finance/books/${bookId}/import/csv/commit`, {
      method: 'POST', credentials: 'include', headers: { 'X-Workspace': getWorkspace() }, body: fd,
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Import failed')
    return data
  },
}

export const contacts = {
  list:         (includeArchived = false) => get(`/contacts${includeArchived ? '?include_archived=true' : ''}`),
  availableForLinking: ()            => get('/contacts/available-for-linking'),
  me:           ()                  => get('/contacts/me'),
  updateMe:     (data)               => request('PATCH', '/contacts/me', data),
  linkAffiliation:   (id, otherId)  => post(`/contacts/${id}/affiliations/${otherId}`, {}),
  unlinkAffiliation: (id, otherId)  => del(`/contacts/${id}/affiliations/${otherId}`),
  uploadPhoto:  (id, file)          => requestFile('POST', `/contacts/${id}/photo`, file),
  photoBlob:    (id)                => requestBlob(`/contacts/${id}/photo`),
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
  setPipeline:  (stages)            => request('PUT', '/contacts/pipeline', { stages }),
  fields:       ()                  => get('/contacts/fields'),
  setFields:    (fields)            => request('PUT', '/contacts/fields', { fields }),
  updateAccess: (id, data)          => request('PUT', `/contacts/${id}/access`, data),
  respondShare: (notifId, accept)   => post('/contacts/shares/respond', { notif_id: notifId, accept }),
  leave:        (id)                => post(`/contacts/${id}/leave`, {}),
  members:      ()                  => get('/contacts/members'),
  roles:        ()                  => get('/contacts/roles'),
  csvPreview:   (file)              => requestFile('POST', '/contacts/import/csv', file),
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

export const notes = {
  list:         (includeArchived = false)     => get(`/notes${includeArchived ? '?include_archived=true' : ''}`),
  setArchived:  (path, archived = true)       => post('/notes/archive', { path, archived }),
  get:          (path)                        => get(`/notes/file/${encodePath(path)}`),
  create:       (path, content = '')          => post('/notes/file', { path, content }),
  update:       (path, content)               => request('PUT', `/notes/file/${encodePath(path)}`, { content }),
  remove:       (path)                        => del(`/notes/file/${encodePath(path)}`),
  createFolder: (path)                        => post('/notes/folder', { path }),
  removeFolder: (path)                        => del(`/notes/folder/${encodePath(path)}`),
  move:         (from_path, to_path, type)    => post('/notes/move', { from_path, to_path, type }),
  updateAccess: (data)                        => request('PUT', '/notes/access', data),
  respondShare: (notifId, accept)            => post('/notes/shares/respond', { notif_id: notifId, accept }),
  leave:        (path)                        => post('/notes/leave', { path }),
  members:      ()                            => get('/notes/members'),
  roles:        ()                            => get('/notes/roles'),
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
  roleUsers:   (name)                 => get(`/auth/admin/features/roles/${name}/users`),
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
  // Automation Inbox (workspace-scoped via X-Workspace header)
  inbox:         ()                  => get('/automations/inbox'),
  createInbox:   (data)              => post('/automations/inboxes', data),
  updateInbox:   (id, data)          => patch(`/automations/inboxes/${id}`, data),
  removeInbox:   (id)                => del(`/automations/inboxes/${id}`),
  setItemStatus: (id, status, note)  => post(`/automations/inbox/items/${id}/status`, { status, note: note || null }),
  removeItem:    (id)                => del(`/automations/inbox/items/${id}`),
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

export const dashboards = {
  list:          ()                       => get('/dashboards'),
  get:           (id)                     => get(`/dashboards/${id}`),
  render:        (id)                     => get(`/dashboards/${id}/render`),
  create:        (name, icon, pool = false, templateId = null, subjectId = null) =>
    post('/dashboards', { name, icon, pool, template_id: templateId, subject_id: subjectId }),
  update:        (id, data)               => patch(`/dashboards/${id}`, data),
  remove:        (id)                     => del(`/dashboards/${id}`),
  catalog:       ()                       => get('/dashboards/catalog'),
  members:       ()                       => get('/dashboards/members'),
  roles:         ()                       => get('/dashboards/roles'),
  updateAccess:  (id, data)               => request('PUT', `/dashboards/${id}/access`, data),
  setShareUnderlyingData: (id, value)     => request('PUT', `/dashboards/${id}/share-underlying-data`, { value }),
  setSubject:    (id, subjectId)          => request('PUT', `/dashboards/${id}/subject`, { subject_id: subjectId }),
  detachTemplate: (id)                    => post(`/dashboards/${id}/detach-template`, {}),
  leave:         (id)                     => post(`/dashboards/${id}/leave`, {}),
  respondShare:  (owner, dashboardId, accept) => post('/dashboards/shares/respond', { owner, dashboard_id: dashboardId, accept }),
  references:    (module, recordId)       => get(`/dashboards/references/${module}/${recordId}`),
}

export const dashboardTemplates = {
  list:           ()               => get('/dashboards/templates'),
  create:         (data)           => post('/dashboards/templates', data),
  update:         (id, data)       => patch(`/dashboards/templates/${id}`, data),
  remove:         (id)             => del(`/dashboards/templates/${id}`),
  access:         (id, data)       => request('PUT', `/dashboards/templates/${id}/access`, data),
  leave:          (id)             => post(`/dashboards/templates/${id}/leave`, {}),
  respondShare:   (owner, templateId, accept) =>
    post('/dashboards/templates/shares/respond', { owner, template_id: templateId, accept }),
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
