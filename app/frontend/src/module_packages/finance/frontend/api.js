// Finance's API client — built on the shared request/get/post/patch/del
// helpers (and BASE, for the hand-rolled multipart/blob/header-override/
// CSV-download fetches requestFile()/requestBlob()/headers() in core
// lib/api.js don't export) exported from the core lib/api.js, not a
// reimplementation of fetch/credentials/header logic per module. Mirrors
// automations'/assets'/contacts' own hand-rolled-multipart precedent.
import { BASE, get, post, put, patch, del } from '../../../lib/api'

function getWorkspace() {
  return localStorage.getItem('lc_ws') || 'personal'
}

function headers(extra = {}) {
  return { 'Content-Type': 'application/json', 'X-Workspace': getWorkspace(), ...extra }
}

// listBooksForWorkspace needs to override X-Workspace explicitly (admin pool
// pages read the pool's own fixed workspace regardless of the admin's own
// active toggle) — get() has no way to pass extra headers, so this is a
// small local GET with the same session-expiry handling uploadFile()/
// fetchBlob() below already duplicate for the same reason.
async function getForWorkspace(path, workspace) {
  const res = await fetch(`${BASE}${path}`, { credentials: 'include', headers: headers({ 'X-Workspace': workspace }) })
  if (res.status === 401) {
    localStorage.removeItem('lc_user')
    if (!window.location.pathname.startsWith('/login')) window.location.href = '/login'
    throw new Error('Session expired. Please sign in again.')
  }
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Request failed')
  return data
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

// Fetch a protected binary (a transaction receipt) as a blob — <img src>
// can't send the X-Workspace header, so images render via
// URL.createObjectURL of this blob.
async function fetchBlob(path) {
  const res = await fetch(`${BASE}${path}`, { credentials: 'include', headers: headers() })
  if (!res.ok) throw new Error('File fetch failed')
  return res.blob()
}

export const finance = {
  listBooks:    (includeArchived = false) => get(`/finance/books${includeArchived ? '?include_archived=true' : ''}`),
  // Admin pool pages (Household/Team) need the pool's own books regardless of
  // the viewing admin's own personal/business workspace toggle — household
  // pool books always live in "personal", team's always in "business".
  listBooksForWorkspace: (workspace) => getForWorkspace('/finance/books', workspace),
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
  uploadReceipt: (bookId, txId, file)      => uploadFile(`/finance/books/${bookId}/transactions/${txId}/receipts`, file),
  receiptBlob:   (bookId, txId, receiptId) => fetchBlob(`/finance/books/${bookId}/transactions/${txId}/receipts/${receiptId}`),
  removeReceipt: (bookId, txId, receiptId) => del(`/finance/books/${bookId}/transactions/${txId}/receipts/${receiptId}`),
  // Planning: budgets, recurring, planned, projection
  budgets:           (bookId)           => get(`/finance/books/${bookId}/budgets`),
  setBudgets:        (bookId, budgets)  => put(`/finance/books/${bookId}/budgets`, { budgets }),
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
  updateBookAccess:    (bookId, data)            => put(`/finance/books/${bookId}/access`, data),
  updateAccountAccess: (bookId, accountId, data) => put(`/finance/books/${bookId}/accounts/${accountId}/access`, data),
  respondShare:        (notifId, accept)         => post('/finance/shares/respond', { notif_id: notifId, accept }),
  leaveBook:           (bookId)                  => post(`/finance/books/${bookId}/leave`, {}),
  members:             ()                        => get('/finance/members'),
  roles:               ()                        => get('/finance/roles'),
  // SimpleFIN bank sync (connections are admin-managed; members request + map)
  sfStatus:      ()        => get('/finance/simplefin/status'),
  sfAccounts:    ()        => get('/finance/simplefin/accounts'),
  sfRequest:     ()        => post('/finance/simplefin/request', {}),
  sfSetMapping:  (entries) => put('/finance/simplefin/mapping', { entries }),
  sfConnections: ()        => get('/finance/simplefin/connections'),
  sfPoolSummary: (pool)    => get(`/finance/simplefin/pool-summary?pool=${pool}`),
  sfClaim:       (userId, setupToken) => post('/finance/simplefin/claim', { user_id: userId, setup_token: setupToken }),
  sfReveal:      (userId)  => post('/finance/simplefin/reveal', { user_id: userId }),
  sfDisconnect:  (userId)  => del(`/finance/simplefin/${userId}`),
  sfSync:        (userId)  => post('/finance/simplefin/sync', { user_id: userId }),
  // Pool-owned SimpleFIN connection (joint/family account, not tied to any one member)
  sfPoolStatus:      (pool)               => get(`/finance/simplefin/pool/${pool}/status`),
  sfPoolAccounts:    (pool)               => get(`/finance/simplefin/pool/${pool}/accounts`),
  sfPoolSetMapping:  (pool, entries)      => put(`/finance/simplefin/pool/${pool}/mapping`, { entries }),
  sfPoolClaim:       (pool, setupToken)   => post(`/finance/simplefin/pool/${pool}/claim`, { setup_token: setupToken }),
  sfPoolReveal:      (pool)               => post(`/finance/simplefin/pool/${pool}/reveal`, {}),
  sfPoolDisconnect:  (pool)               => del(`/finance/simplefin/pool/${pool}`),
  sfPoolSync:        (pool)               => post(`/finance/simplefin/pool/${pool}/sync`, {}),
  // Payee → category rules + CSV import
  rules:      (bookId)         => get(`/finance/books/${bookId}/rules`),
  removeRule: (bookId, ruleId) => del(`/finance/books/${bookId}/rules/${ruleId}`),
  csvPreview: (bookId, file)   => uploadFile(`/finance/books/${bookId}/import/csv`, file),
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
