import { useEffect, useState } from 'react'
import { finance as financeApi } from '../../lib/api'
import { fmtMoney, toCents, centsToInput, todayStr } from './money'

const EMPTY_FORM = { name: '', amount: '', kind: 'expense', account_id: '', category: '', cadence: 'monthly', next_due: '', autopay: false }

export default function RecurringPanel({ book, canEdit }) {
  const [items, setItems] = useState([])
  const [planned, setPlanned] = useState([])
  const [form, setForm] = useState(null)          // null | {…EMPTY_FORM, id?}
  const [plannedForm, setPlannedForm] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const today = todayStr()

  function load() {
    financeApi.recurring(book.id).then(r => setItems(Array.isArray(r) ? r : [])).catch(() => {})
    financeApi.planned(book.id).then(r => setPlanned(Array.isArray(r) ? r : [])).catch(() => {})
  }
  useEffect(() => { load() }, [book.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const accounts = (book.accounts || []).filter(a => !a.archived)
  const accountName = Object.fromEntries((book.accounts || []).map(a => [a.id, a.name]))

  function openForm(item) {
    setError('')
    if (item) {
      setForm({
        id: item.id, name: item.name, amount: centsToInput(item.amount_cents),
        kind: item.amount_cents > 0 ? 'income' : 'expense',
        account_id: item.account_id, category: item.category || '',
        cadence: item.cadence, next_due: item.next_due, autopay: !!item.autopay,
      })
    } else {
      setForm({ ...EMPTY_FORM, account_id: accounts[0]?.id || '', next_due: today })
    }
  }

  async function saveForm(e) {
    e.preventDefault()
    const cents = toCents(form.amount)
    if (Number.isNaN(cents) || cents <= 0) { setError('Enter a valid amount.'); return }
    const payload = {
      name: form.name, amount_cents: form.kind === 'expense' ? -cents : cents,
      account_id: form.account_id, category: form.category, cadence: form.cadence,
      next_due: form.next_due, autopay: form.autopay,
    }
    setBusy(true); setError('')
    try {
      if (form.id) await financeApi.updateRecurring(book.id, form.id, payload)
      else await financeApi.addRecurring(book.id, payload)
      setForm(null); load()
    } catch (err) {
      setError(err.message || 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  async function removeItem(item) {
    if (!window.confirm(`Delete "${item.name}"?`)) return
    try { await financeApi.removeRecurring(book.id, item.id); load() } catch (err) { setError(err.message) }
  }

  async function toggleActive(item) {
    try { await financeApi.updateRecurring(book.id, item.id, { active: !item.active }); load() } catch (err) { setError(err.message) }
  }

  async function savePlanned(e) {
    e.preventDefault()
    const cents = toCents(plannedForm.amount)
    if (Number.isNaN(cents) || cents <= 0) { setError('Enter a valid amount.'); return }
    setBusy(true); setError('')
    try {
      await financeApi.addPlanned(book.id, {
        name: plannedForm.name, date: plannedForm.date,
        amount_cents: plannedForm.kind === 'expense' ? -cents : cents,
        account_id: plannedForm.account_id,
      })
      setPlannedForm(null); load()
    } catch (err) {
      setError(err.message || 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  async function togglePlannedDone(item) {
    try { await financeApi.updatePlanned(book.id, item.id, { done: !item.done }); load() } catch (err) { setError(err.message) }
  }

  async function removePlanned(item) {
    try { await financeApi.removePlanned(book.id, item.id); load() } catch (err) { setError(err.message) }
  }

  const missedCutoff = new Date(Date.now() - 3 * 86400000).toISOString().slice(0, 10)

  return (
    <div className="space-y-4">
      {/* Recurring bills */}
      <div className="card p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-sm uppercase tracking-wide text-charcoal-500 dark:text-charcoal-400">
            Recurring bills & income
          </h2>
          {canEdit && <button onClick={() => openForm(null)} className="btn-ghost text-xs">＋ Add</button>}
        </div>

        {items.length === 0 ? (
          <p className="text-sm text-charcoal-500 dark:text-charcoal-400">
            Nothing recurring yet — add rent, subscriptions, paychecks. LogCore matches incoming
            transactions to them, flags missed ones, and uses them for balance projections.
          </p>
        ) : (
          <div className="space-y-2">
            {items.map(item => {
              const missed = item.active && item.next_due < missedCutoff
              return (
                <div key={item.id} className={`flex items-center gap-2 text-sm ${item.active ? '' : 'opacity-50'}`}>
                  <div className="flex-1 min-w-0">
                    <p className="truncate">
                      {item.name}
                      {missed && <span className="text-red-500 text-xs font-medium ml-2">MISSED</span>}
                    </p>
                    <p className="text-xs text-charcoal-500 dark:text-charcoal-400">
                      {item.cadence} · next {item.next_due} · {accountName[item.account_id] || '?'}
                      {item.last_paid ? ` · last paid ${item.last_paid}` : ''}
                    </p>
                  </div>
                  <span className={`font-medium shrink-0 ${item.amount_cents > 0 ? 'text-green-600 dark:text-green-400' : ''}`}>
                    {fmtMoney(item.amount_cents, book.currency)}
                  </span>
                  {canEdit && (
                    <div className="flex shrink-0">
                      <button onClick={() => toggleActive(item)} className="btn-ghost text-xs px-1.5" title={item.active ? 'Pause' : 'Resume'}>
                        {item.active ? '⏸' : '▶'}
                      </button>
                      <button onClick={() => openForm(item)} className="btn-ghost text-xs px-1.5">✎</button>
                      <button onClick={() => removeItem(item)} className="btn-ghost text-xs px-1.5 text-red-500">×</button>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Planned one-offs */}
      <div className="card p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-sm uppercase tracking-wide text-charcoal-500 dark:text-charcoal-400">
            Planned one-offs
          </h2>
          {canEdit && (
            <button
              onClick={() => setPlannedForm({ name: '', amount: '', kind: 'expense', date: today, account_id: accounts[0]?.id || '' })}
              className="btn-ghost text-xs"
            >＋ Add</button>
          )}
        </div>
        {planned.length === 0 ? (
          <p className="text-sm text-charcoal-500 dark:text-charcoal-400">
            Expected one-time items (tax refund, car repair) — they feed the balance projection.
          </p>
        ) : (
          <div className="space-y-2">
            {planned.map(item => (
              <div key={item.id} className={`flex items-center gap-2 text-sm ${item.done ? 'opacity-50' : ''}`}>
                {canEdit && (
                  <button
                    onClick={() => togglePlannedDone(item)}
                    className={`shrink-0 w-4 h-4 rounded border-2 text-white text-[10px] flex items-center justify-center ${
                      item.done ? 'bg-orange-500 border-orange-500' : 'border-charcoal-300 dark:border-charcoal-600'
                    }`}
                  >{item.done && '✓'}</button>
                )}
                <span className={`flex-1 min-w-0 truncate ${item.done ? 'line-through' : ''}`}>{item.name}</span>
                <span className="text-xs text-charcoal-500 dark:text-charcoal-400 shrink-0">{item.date}</span>
                <span className={`font-medium shrink-0 ${item.amount_cents > 0 ? 'text-green-600 dark:text-green-400' : ''}`}>
                  {fmtMoney(item.amount_cents, book.currency)}
                </span>
                {canEdit && (
                  <button onClick={() => removePlanned(item)} className="btn-ghost text-xs px-1.5 text-red-500 shrink-0">×</button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {error && <p className="text-sm text-red-500">{error}</p>}

      {/* Recurring form modal */}
      {form && (
        <div className="modal-overlay">
          <div className="modal-card max-w-md w-full p-5">
            <h3 className="font-semibold mb-4">{form.id ? 'Edit recurring item' : 'New recurring item'}</h3>
            <form onSubmit={saveForm} className="space-y-3">
              <input className="input" placeholder="Name (Netflix, Rent, Paycheck…)" value={form.name}
                onChange={e => setForm({ ...form, name: e.target.value })} maxLength={80} required autoFocus />
              <div className="grid grid-cols-2 gap-3">
                <select className="input" value={form.kind} onChange={e => setForm({ ...form, kind: e.target.value })}>
                  <option value="expense">− Expense</option>
                  <option value="income">+ Income</option>
                </select>
                <input className="input" inputMode="decimal" placeholder="0.00" value={form.amount}
                  onChange={e => setForm({ ...form, amount: e.target.value })} required />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <select className="input" value={form.cadence} onChange={e => setForm({ ...form, cadence: e.target.value })}>
                  <option value="weekly">Weekly</option>
                  <option value="monthly">Monthly</option>
                  <option value="yearly">Yearly</option>
                </select>
                <input type="date" className="input" value={form.next_due}
                  onChange={e => setForm({ ...form, next_due: e.target.value })} required title="Next due date" />
              </div>
              <select className="input" value={form.account_id} onChange={e => setForm({ ...form, account_id: e.target.value })}>
                {accounts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
              <select className="input" value={form.category} onChange={e => setForm({ ...form, category: e.target.value })}>
                <option value="">Uncategorized</option>
                {(book.categories || []).filter(c => c.kind === form.kind).map(c => (
                  <option key={c.name} value={c.name}>{c.name}</option>
                ))}
              </select>
              {error && <p className="text-sm text-red-500">{error}</p>}
              <div className="flex gap-2 pt-1">
                <button type="button" onClick={() => setForm(null)} className="btn-ghost flex-1">Cancel</button>
                <button type="submit" disabled={busy} className="btn-primary flex-1">{busy ? 'Saving…' : 'Save'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Planned form modal */}
      {plannedForm && (
        <div className="modal-overlay">
          <div className="modal-card max-w-md w-full p-5">
            <h3 className="font-semibold mb-4">New planned item</h3>
            <form onSubmit={savePlanned} className="space-y-3">
              <input className="input" placeholder="Name (tax refund, car repair…)" value={plannedForm.name}
                onChange={e => setPlannedForm({ ...plannedForm, name: e.target.value })} maxLength={80} required autoFocus />
              <div className="grid grid-cols-2 gap-3">
                <select className="input" value={plannedForm.kind} onChange={e => setPlannedForm({ ...plannedForm, kind: e.target.value })}>
                  <option value="expense">− Expense</option>
                  <option value="income">+ Income</option>
                </select>
                <input className="input" inputMode="decimal" placeholder="0.00" value={plannedForm.amount}
                  onChange={e => setPlannedForm({ ...plannedForm, amount: e.target.value })} required />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <input type="date" className="input" value={plannedForm.date}
                  onChange={e => setPlannedForm({ ...plannedForm, date: e.target.value })} required />
                <select className="input" value={plannedForm.account_id} onChange={e => setPlannedForm({ ...plannedForm, account_id: e.target.value })}>
                  {accounts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>
              </div>
              {error && <p className="text-sm text-red-500">{error}</p>}
              <div className="flex gap-2 pt-1">
                <button type="button" onClick={() => setPlannedForm(null)} className="btn-ghost flex-1">Cancel</button>
                <button type="submit" disabled={busy} className="btn-primary flex-1">{busy ? 'Saving…' : 'Save'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
