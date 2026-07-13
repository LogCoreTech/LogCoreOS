import { useEffect, useState } from 'react'
import { finance as financeApi } from '../../lib/api'
import { fmtMoney, toCents, centsToInput, monthStr } from './money'

export default function BudgetsPanel({ book, canEdit }) {
  const [status, setStatus] = useState([])
  const [editing, setEditing] = useState(false)
  const [limits, setLimits] = useState({}) // category -> dollars string
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const month = monthStr()

  function load() {
    financeApi.budgetStatus(book.id, month).then(s => setStatus(Array.isArray(s) ? s : [])).catch(() => {})
  }
  useEffect(() => { load() }, [book.id]) // eslint-disable-line react-hooks/exhaustive-deps

  function startEdit() {
    const initial = {}
    for (const s of status) initial[s.category] = centsToInput(s.monthly_limit_cents)
    setLimits(initial)
    setEditing(true)
  }

  async function save() {
    const budgets = []
    for (const [category, value] of Object.entries(limits)) {
      if (!value) continue
      const cents = toCents(value)
      if (Number.isNaN(cents) || cents <= 0) { setError(`Invalid limit for ${category}`); return }
      budgets.push({ category, monthly_limit_cents: cents })
    }
    setBusy(true); setError('')
    try {
      await financeApi.setBudgets(book.id, budgets)
      setEditing(false)
      load()
    } catch (err) {
      setError(err.message || 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  const expenseCategories = (book.categories || []).filter(c => c.kind === 'expense')

  return (
    <div className="card p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-sm uppercase tracking-wide text-charcoal-500 dark:text-charcoal-400">
          Budgets — {month}
        </h2>
        {canEdit && !editing && (
          <button onClick={startEdit} className="btn-ghost text-xs">✎ Set limits</button>
        )}
      </div>

      {editing ? (
        <div className="space-y-2">
          <p className="text-xs text-charcoal-500 dark:text-charcoal-400">
            Monthly limit per category — leave blank for no budget. Alerts fire at {book.budget_warn_pct || 80}% and 100%.
          </p>
          {expenseCategories.map(c => (
            <div key={c.name} className="flex items-center gap-2">
              <span className="text-sm flex-1">{c.name}</span>
              <input
                className="input w-28" inputMode="decimal" placeholder="—"
                value={limits[c.name] || ''}
                onChange={e => setLimits({ ...limits, [c.name]: e.target.value })}
              />
            </div>
          ))}
          {error && <p className="text-sm text-red-500">{error}</p>}
          <div className="flex gap-2 pt-1">
            <button onClick={() => setEditing(false)} className="btn-ghost flex-1">Cancel</button>
            <button onClick={save} disabled={busy} className="btn-primary flex-1">{busy ? 'Saving…' : 'Save'}</button>
          </div>
        </div>
      ) : status.length === 0 ? (
        <p className="text-sm text-charcoal-500 dark:text-charcoal-400">
          No budgets yet.{canEdit && ' Set a monthly limit per category and LogCore alerts you before you blow past it.'}
        </p>
      ) : (
        <div className="space-y-3">
          {status.map(s => {
            const pct = Math.min(s.pct, 100)
            const bar = s.pct >= 100 ? 'bg-red-500' : s.pct >= (book.budget_warn_pct || 80) ? 'bg-yellow-500' : 'bg-green-500'
            return (
              <div key={s.category}>
                <div className="flex items-center justify-between text-sm mb-1">
                  <span>{s.category}</span>
                  <span className={s.pct >= 100 ? 'text-red-500 font-medium' : 'text-charcoal-500 dark:text-charcoal-400'}>
                    {fmtMoney(s.spent_cents, book.currency)} / {fmtMoney(s.monthly_limit_cents, book.currency)} · {s.pct}%
                  </span>
                </div>
                <div className="h-2 rounded-full bg-charcoal-100 dark:bg-charcoal-700 overflow-hidden">
                  <div className={`h-full rounded-full ${bar}`} style={{ width: `${pct}%` }} />
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
