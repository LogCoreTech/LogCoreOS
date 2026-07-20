import { useEffect, useState } from 'react'
import HelpButton from '../components/HelpButton'
import { useSearchParams } from 'react-router-dom'
import { finance as financeApi, assets as assetsApi } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useWorkspace } from '../lib/workspace'
import TransactionModal from '../components/finance/TransactionModal'
import BookSettings from '../components/finance/BookSettings'
import SimpleFinPanel from '../components/finance/SimpleFinPanel'
import BudgetsPanel from '../components/finance/BudgetsPanel'
import RecurringPanel from '../components/finance/RecurringPanel'
import InvoicesPanel from '../components/finance/InvoicesPanel'
import ReportsPanel from '../components/finance/ReportsPanel'
import { fmtMoney, monthStr } from '../components/finance/money'

export default function Finance() {
  const { user } = useAuth()
  const { workspace } = useWorkspace()
  const [searchParams, setSearchParams] = useSearchParams()
  const [books, setBooks] = useState([])
  const [activeId, setActiveId] = useState(searchParams.get('book') || null)
  const [view, setView] = useState(searchParams.get('view') || 'overview')
  const [loading, setLoading] = useState(true)
  const [showNewBook, setShowNewBook] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [showBank, setShowBank] = useState(false)
  const [txModal, setTxModal] = useState(null) // null | {tx: null|obj}
  const [showArchived, setShowArchived] = useState(false)
  const [assetList, setAssetList] = useState([]) // for the tx linked-asset picker; [] if assets module off
  const [invoicePrefill, setInvoicePrefill] = useState(null) // {contactId, amountCents, title, dealId} from a deal

  useEffect(() => {
    assetsApi.list().then(r => setAssetList(Array.isArray(r) ? r : [])).catch(() => setAssetList([]))
  }, [workspace])

  const isAdmin = user?.role === 'admin'
  const active = books.find(b => b.id === activeId) || books[0] || null
  const canEdit = active?._access === 'edit'
  const isContribute = active?._access === 'contribute'
  const caps = active?._caps || {}
  const canAddTx = canEdit || (isContribute && (caps.add || []).length > 0)
  const isSharedToMe = active?._owner && active._owner !== 'household' && active._owner !== 'team'

  async function leaveBook() {
    if (!window.confirm(`Leave "${active.name}"? The owner keeps the book; you lose access.`)) return
    try {
      await financeApi.leaveBook(active.id)
      setActiveId(null)
      load(false)
    } catch { /* surfaced by reload */ }
  }

  async function load(keepActive = true) {
    setLoading(true)
    try {
      const list = await financeApi.listBooks(showArchived)
      const arr = Array.isArray(list) ? list : []
      setBooks(arr)
      if (!keepActive || !arr.some(b => b.id === activeId)) {
        setActiveId(arr.find(b => !b.archived)?.id || arr[0]?.id || null)
      }
    } catch {
      setBooks([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(true) }, [workspace, showArchived]) // eslint-disable-line react-hooks/exhaustive-deps
  // Consume deep-link params (?book=&view=) — also fires when a bell action
  // navigates here while the page is already mounted.
  useEffect(() => {
    const bookParam = searchParams.get('book')
    const viewParam = searchParams.get('view')
    const clientContact = searchParams.get('client_contact')
    if (!bookParam && !viewParam && !clientContact) return
    if (bookParam) setActiveId(bookParam)
    if (viewParam) setView(viewParam)
    // Deal → invoice deep-prefill (from Contacts). No book param on purpose —
    // the user picks which book to invoice from, then confirms in the modal.
    if (clientContact && searchParams.get('deal_id')) {
      setInvoicePrefill({
        contactId: clientContact,
        amountCents: parseInt(searchParams.get('amount') || '0', 10) || 0,
        title: searchParams.get('title') || '',
        dealId: searchParams.get('deal_id'),
      })
    }
    setSearchParams({}, { replace: true })
  }, [searchParams]) // eslint-disable-line react-hooks/exhaustive-deps

  function selectBook(id) {
    setActiveId(id)
    setView('overview')
  }

  async function unarchiveBook() {
    try {
      await financeApi.updateBook(active.id, { archived: false })
      load(true)
    } catch { /* surfaced by reload */ }
  }

  return (
    <div key={workspace} className="w-full max-w-3xl mx-auto space-y-5 overflow-x-hidden">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <span className="flex items-center gap-2">
          <h1 className="text-2xl font-bold">Finance</h1>
          <HelpButton section="finance" />
          <button onClick={() => setShowNewBook(true)} className="btn-primary text-sm whitespace-nowrap md:hidden">＋ New book</button>
        </span>
        <div className="flex gap-2 shrink-0">
          <button onClick={() => setShowBank(true)} className="btn-ghost text-sm whitespace-nowrap">🏦 Bank</button>
          {active && isSharedToMe && (
            <button onClick={leaveBook} className="btn-ghost text-sm text-red-500">Leave</button>
          )}
          {active?.archived && canEdit && (
            <button onClick={unarchiveBook} className="btn-ghost text-sm">Unarchive</button>
          )}
          {active && canEdit && !active.archived && (
            <button onClick={() => setShowSettings(true)} className="btn-ghost text-sm">⚙ Settings</button>
          )}
          <button
            onClick={() => setShowArchived(s => !s)}
            className="btn-ghost text-sm whitespace-nowrap"
            title={showArchived ? 'Hide archived books' : 'Show archived books'}
          >
            {showArchived ? 'Hide archived' : 'Show archived'}
          </button>
          <button onClick={() => setShowNewBook(true)} className="btn-primary whitespace-nowrap hidden md:inline-block">＋ New book</button>
        </div>
      </div>

      {/* Book chips */}
      {books.length > 0 && (
        <div className="flex gap-2 flex-wrap">
          {books.map(b => (
            <button
              key={b.id}
              onClick={() => selectBook(b.id)}
              className={`px-3 py-1.5 rounded-full text-sm border transition-colors ${
                active?.id === b.id
                  ? 'border-orange-500 bg-orange-500/10 text-orange-600 dark:text-orange-400'
                  : 'border-charcoal-200 dark:border-charcoal-700 text-charcoal-600 dark:text-charcoal-300'
              } ${b.archived ? 'opacity-50' : ''}`}
            >
              {b.icon} {b.name}
              {b.archived && ' 🗄'}
              {b._owner === 'household' && ' 🏠'}
              {b._owner === 'team' && ' 🧑‍🤝‍🧑'}
            </button>
          ))}
        </div>
      )}

      {loading ? (
        <div className="space-y-3">{[1, 2].map(i => <div key={i} className="h-24 card animate-pulse" />)}</div>
      ) : !active ? (
        <div className="card p-8 text-center text-charcoal-500 dark:text-charcoal-400">
          <p className="text-4xl mb-2">💵</p>
          <p className="mb-1">No books yet.</p>
          <p className="text-sm">Create a book to start tracking money — every book has its own accounts, categories and reports.</p>
        </div>
      ) : (
        <>
          {/* View tabs */}
          <div className="flex gap-1 bg-charcoal-100 dark:bg-charcoal-800 rounded-lg p-1">
            {['overview', 'transactions', 'budgets', 'recurring', 'invoices', 'reports'].map(v => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={`flex-1 py-1 rounded-md text-xs font-medium capitalize transition-colors ${
                  view === v
                    ? 'bg-white dark:bg-charcoal-600 text-charcoal-900 dark:text-gray-100 shadow-sm'
                    : 'text-charcoal-500 dark:text-charcoal-400'
                }`}
              >
                {v}
              </button>
            ))}
          </div>

          {view === 'overview' && (
            <OverviewView book={active} canEdit={canEdit} onAddTx={() => setTxModal({ tx: null })} onAddAccount={() => setShowSettings(true)} />
          )}
          {view === 'transactions' && (
            <TransactionsView
              book={active}
              canEdit={canEdit}
              canAdd={canAddTx}
              contribute={isContribute ? { caps, userName: user?.name } : null}
              onAdd={() => setTxModal({ tx: null })}
              onEdit={tx => setTxModal({ tx })}
            />
          )}
          {view === 'budgets' && <BudgetsPanel key={active.id} book={active} canEdit={canEdit} />}
          {view === 'recurring' && <RecurringPanel key={active.id} book={active} canEdit={canEdit} />}
          {view === 'invoices' && (
            <InvoicesPanel
              key={active.id}
              book={active}
              canEdit={canEdit}
              assets={assetList}
              prefill={invoicePrefill}
              onPrefillConsumed={() => setInvoicePrefill(null)}
            />
          )}
          {view === 'reports' && <ReportsPanel key={active.id} book={active} />}
        </>
      )}

      {showNewBook && (
        <NewBookModal
          workspace={workspace}
          isAdmin={isAdmin}
          onClose={() => setShowNewBook(false)}
          onCreated={book => { setShowNewBook(false); setActiveId(book.id); load() }}
        />
      )}
      {showBank && (
        <SimpleFinPanel
          books={books}
          isAdmin={isAdmin}
          workspace={workspace}
          onClose={() => { setShowBank(false); load() }}
        />
      )}
      {showSettings && active && (
        <BookSettings
          book={active}
          onClose={() => setShowSettings(false)}
          onChanged={() => { setShowSettings(false); load() }}
          onDeletedBook={() => { setShowSettings(false); setActiveId(null); load(false) }}
        />
      )}
      {txModal && active && (
        <TransactionModal
          key={txModal.tx?.id || 'new'}
          book={active}
          tx={txModal.tx}
          allowedKinds={canEdit ? ['expense', 'income'] : (caps.add || [])}
          assets={assetList}
          onClose={() => setTxModal(null)}
          onSaved={() => { setTxModal(null); load() }}
          onDeleted={() => { setTxModal(null); load() }}
        />
      )}
    </div>
  )
}

function plusDays(days) {
  const d = new Date(Date.now() + days * 86400000)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function OverviewView({ book, canEdit, onAddTx, onAddAccount }) {
  const [report, setReport] = useState(null)
  const [projAccount, setProjAccount] = useState('')
  const [projDate, setProjDate] = useState(plusDays(30))
  const [projection, setProjection] = useState(null)

  useEffect(() => {
    let alive = true
    financeApi.monthlyReport(book.id, monthStr())
      .then(r => { if (alive) setReport(r) })
      .catch(() => { if (alive) setReport(null) })
    return () => { alive = false }
  }, [book.id])

  const projTarget = projAccount || (book.accounts || []).find(a => !a.archived)?.id || ''
  useEffect(() => {
    if (!projTarget || !projDate) { setProjection(null); return }
    let alive = true
    financeApi.projection(book.id, projTarget, projDate)
      .then(p => { if (alive) setProjection(p) })
      .catch(() => { if (alive) setProjection(null) })
    return () => { alive = false }
  }, [book.id, projTarget, projDate])

  const accounts = (book.accounts || []).filter(a => !a.archived)
  const topExpenses = (report?.categories || [])
    .filter(c => c.expense_cents < 0)
    .slice(0, 5)

  return (
    <div className="space-y-4">
      {/* Balance summary */}
      <div className="card p-5">
        <div className="flex items-center justify-between mb-3 gap-2">
          <h2 className="font-semibold text-sm uppercase tracking-wide text-charcoal-500 dark:text-charcoal-400">
            {book._owner === 'household' ? 'Household balance' : book._owner === 'team' ? 'Team balance' : 'Balance'}
          </h2>
          <div className="flex items-center gap-2">
            {canEdit && <button onClick={onAddAccount} className="btn-ghost text-xs">＋ Account</button>}
            <span className="text-xl font-bold">{fmtMoney(book.total_cents, book.currency)}</span>
          </div>
        </div>
        {accounts.length === 0 ? (
          <p className="text-sm text-charcoal-500 dark:text-charcoal-400">
            No accounts yet.{canEdit && ' Add a bank or cash account with ＋ Account above.'}
            {book._owner && canEdit && ' Bank-linked accounts on shared books are admin-managed.'}
          </p>
        ) : !book.balances ? (
          <p className="text-sm text-charcoal-500 dark:text-charcoal-400">
            Balances aren't visible with your access — you can still submit entries.
          </p>
        ) : (
          <div className="space-y-2">
            {accounts.map(a => (
              <div key={a.id} className="flex items-center justify-between text-sm">
                <span className="flex items-center gap-2 min-w-0">
                  <span className="truncate">{a.name}</span>
                  <span className="badge bg-charcoal-100 dark:bg-charcoal-700 text-charcoal-600 dark:text-charcoal-300 capitalize">{a.type}</span>
                </span>
                <span className="font-medium shrink-0">{fmtMoney(book.balances?.[a.id], book.currency)}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* This month */}
      <div className="card p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold text-sm uppercase tracking-wide text-charcoal-500 dark:text-charcoal-400">This month</h2>
          {canEdit && <button onClick={onAddTx} className="btn-ghost text-xs">＋ Add transaction</button>}
        </div>
        {!report ? (
          <p className="text-sm text-charcoal-500 dark:text-charcoal-400">No data yet.</p>
        ) : (
          <>
            <div className="grid grid-cols-3 gap-3 text-center mb-4">
              <div>
                <p className="text-xs text-charcoal-500 dark:text-charcoal-400">Income</p>
                <p className="font-semibold text-green-600 dark:text-green-400">{fmtMoney(report.income_cents, book.currency)}</p>
              </div>
              <div>
                <p className="text-xs text-charcoal-500 dark:text-charcoal-400">Expenses</p>
                <p className="font-semibold text-red-500 dark:text-red-400">{fmtMoney(report.expense_cents, book.currency)}</p>
              </div>
              <div>
                <p className="text-xs text-charcoal-500 dark:text-charcoal-400">Net</p>
                <p className={`font-semibold ${report.net_cents >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-500 dark:text-red-400'}`}>
                  {fmtMoney(report.net_cents, book.currency)}
                </p>
              </div>
            </div>
            {topExpenses.length > 0 && (
              <div className="space-y-1.5">
                {topExpenses.map(c => (
                  <div key={c.category || '(uncategorized)'} className="flex items-center justify-between text-sm">
                    <span className="text-charcoal-600 dark:text-charcoal-300">{c.category || 'Uncategorized'}</span>
                    <span>{fmtMoney(c.expense_cents, book.currency)}</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {/* Projected balance (hidden when balances are capped away server-side) */}
      {accounts.length > 0 && book.balances && (
        <div className="card p-5">
          <h2 className="font-semibold text-sm uppercase tracking-wide text-charcoal-500 dark:text-charcoal-400 mb-3">
            Projected balance
          </h2>
          <div className="flex gap-2 flex-wrap items-center mb-3">
            <select className="input w-40" value={projTarget} onChange={e => setProjAccount(e.target.value)}>
              {accounts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
            <span className="text-sm text-charcoal-500 dark:text-charcoal-400">on</span>
            <input type="date" className="input w-40" value={projDate} onChange={e => setProjDate(e.target.value)} />
          </div>
          {!projection ? (
            <p className="text-sm text-charcoal-500 dark:text-charcoal-400">
              Projection = today's balance + recurring bills/income + planned items up to that date.
            </p>
          ) : (
            <>
              <div className="flex items-baseline justify-between mb-2">
                <span className="text-sm text-charcoal-500 dark:text-charcoal-400">
                  {fmtMoney(projection.current_cents, book.currency)} today →
                </span>
                <span className={`text-xl font-bold ${projection.projected_cents < 0 ? 'text-red-500' : ''}`}>
                  {fmtMoney(projection.projected_cents, book.currency)}
                </span>
              </div>
              {projection.items.length === 0 ? (
                <p className="text-xs text-charcoal-400 dark:text-charcoal-500">
                  Nothing scheduled before then — add recurring bills or planned items to shape the forecast.
                </p>
              ) : (
                <div className="space-y-1">
                  {projection.items.map((i, idx) => (
                    <div key={idx} className="flex items-center justify-between text-xs text-charcoal-500 dark:text-charcoal-400">
                      <span>{i.date} · {i.name}{i.source === 'planned' ? ' (planned)' : ''}</span>
                      <span className={i.amount_cents > 0 ? 'text-green-600 dark:text-green-400' : ''}>
                        {fmtMoney(i.amount_cents, book.currency)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}

function TransactionsView({ book, canEdit, canAdd, contribute, onAdd, onEdit }) {
  const rowEditable = tx =>
    canEdit ||
    (contribute && contribute.caps?.edit_own && tx.created_by === contribute.userName)
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [q, setQ] = useState('')
  const [account, setAccount] = useState('')
  const [category, setCategory] = useState('__all')
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const LIMIT = 100

  useEffect(() => {
    let alive = true
    setLoading(true)
    const opts = { limit: LIMIT, offset }
    if (q) opts.q = q
    if (account) opts.account = account
    if (category !== '__all') opts.category = category
    financeApi.transactions(book.id, opts)
      .then(r => {
        if (!alive) return
        if (offset === 0) setItems(r.items)
        else setItems(prev => [...prev, ...r.items])
        setTotal(r.total)
      })
      .catch(() => { if (alive) { setItems([]); setTotal(0) } })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [book.id, q, account, category, offset])

  useEffect(() => { setOffset(0) }, [book.id, q, account, category])

  const accountName = Object.fromEntries((book.accounts || []).map(a => [a.id, a.name]))

  return (
    <div className="space-y-3">
      <div className="flex gap-2 flex-wrap items-center">
        <input
          className="input flex-1 min-w-[8rem]" placeholder="Search payee or notes…"
          value={q} onChange={e => setQ(e.target.value)}
        />
        <select className="input w-32" value={account} onChange={e => setAccount(e.target.value)}>
          <option value="">All accounts</option>
          {(book.accounts || []).map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <select className="input w-36" value={category} onChange={e => setCategory(e.target.value)}>
          <option value="__all">All categories</option>
          <option value="">Uncategorized</option>
          {(book.categories || []).map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
        </select>
        {canAdd && <button onClick={onAdd} className="btn-primary shrink-0">＋ Add</button>}
      </div>

      {contribute && !contribute.caps?.see_all_tx && (
        <p className="text-[11px] text-charcoal-400 dark:text-charcoal-500">
          Shared with you for submitting entries — you see only your own.
        </p>
      )}

      {loading && items.length === 0 ? (
        <div className="space-y-2">{[1, 2, 3].map(i => <div key={i} className="h-12 card animate-pulse" />)}</div>
      ) : items.length === 0 ? (
        <div className="card p-8 text-center text-charcoal-500 dark:text-charcoal-400">
          <p>No transactions{q || account || category !== '__all' ? ' match these filters' : ' yet'}.</p>
        </div>
      ) : (
        <div className="card divide-y divide-charcoal-100 dark:divide-charcoal-700/60">
          {items.map(tx => (
            <button
              key={tx.id}
              onClick={() => rowEditable(tx) && onEdit(tx)}
              disabled={!rowEditable(tx)}
              className="w-full flex items-center gap-3 px-4 py-2.5 text-left disabled:cursor-default hover:bg-charcoal-50 dark:hover:bg-charcoal-800/60 transition-colors"
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm truncate">{tx.payee || tx.notes || (tx.amount_cents > 0 ? 'Income' : 'Expense')}</p>
                <p className="text-xs text-charcoal-500 dark:text-charcoal-400">
                  {tx.date} · {accountName[tx.account_id] || 'Unknown account'}
                  {tx.category ? ` · ${tx.category}` : ''}
                </p>
              </div>
              <span className={`font-medium text-sm shrink-0 ${tx.amount_cents > 0 ? 'text-green-600 dark:text-green-400' : ''}`}>
                {fmtMoney(tx.amount_cents, book.currency)}
              </span>
            </button>
          ))}
        </div>
      )}

      {items.length < total && (
        <button onClick={() => setOffset(offset + LIMIT)} className="btn-ghost w-full text-sm">
          Load more ({total - items.length} left)
        </button>
      )}
    </div>
  )
}

function NewBookModal({ workspace, isAdmin, onClose, onCreated }) {
  const [name, setName] = useState('')
  const [icon, setIcon] = useState('💰')
  const [pool, setPool] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const poolLabel = workspace === 'business' ? 'team' : 'household'

  async function submit(e) {
    e.preventDefault()
    setError(''); setBusy(true)
    try {
      const book = await financeApi.createBook({ name, icon, pool })
      onCreated(book)
    } catch (err) {
      setError(err.message || 'Could not create book')
      setBusy(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-card max-w-sm w-full p-5">
        <h3 className="font-semibold mb-4">New book</h3>
        <form onSubmit={submit} className="space-y-3">
          <div className="grid grid-cols-[1fr_4rem] gap-2">
            <div>
              <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Name</label>
              <input className="input" value={name} onChange={e => setName(e.target.value)} maxLength={80} autoFocus
                placeholder={workspace === 'business' ? 'LLC books' : 'Family budget'} required />
            </div>
            <div>
              <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Icon</label>
              <input className="input text-center" value={icon} onChange={e => setIcon(e.target.value)} maxLength={8} />
            </div>
          </div>
          {isAdmin && (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={pool} onChange={e => setPool(e.target.checked)} />
              Shared {poolLabel} book (visible to every {poolLabel} member)
            </label>
          )}
          <p className="text-[11px] text-charcoal-400 dark:text-charcoal-500">
            {pool
              ? `Lives in the ${poolLabel} pool — members can view it; admins manage it.`
              : 'Private to you — nobody else can see it, not even admins.'}
          </p>
          {error && <p className="text-sm text-red-500">{error}</p>}
          <div className="flex gap-2 pt-1">
            <button type="button" onClick={onClose} disabled={busy} className="btn-ghost flex-1">Cancel</button>
            <button type="submit" disabled={busy || !name.trim()} className="btn-primary flex-1">
              {busy ? 'Creating…' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
