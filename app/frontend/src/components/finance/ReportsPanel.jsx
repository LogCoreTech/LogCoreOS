import { useEffect, useState } from 'react'
import { finance as financeApi } from '../../lib/api'
import { fmtMoney } from './money'

export default function ReportsPanel({ book }) {
  const year = new Date().getFullYear()
  const [period, setPeriod] = useState('year')
  const [quarter, setQuarter] = useState(Math.floor(new Date().getMonth() / 3) + 1)
  const [month, setMonth] = useState(new Date().getMonth() + 1)
  const [pnlYear, setPnlYear] = useState(year)
  const [pnl, setPnl] = useState(null)
  const [taxYear, setTaxYear] = useState(year)
  const [tax, setTax] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    const opts = { year: pnlYear, period }
    if (period === 'quarter') opts.quarter = quarter
    if (period === 'month') opts.month = month
    financeApi.pnl(book.id, opts)
      .then(r => { if (alive) { setPnl(r); setError('') } })
      .catch(err => { if (alive) setError(err.message) })
    return () => { alive = false }
  }, [book.id, pnlYear, period, quarter, month])

  useEffect(() => {
    let alive = true
    financeApi.taxSummary(book.id, taxYear)
      .then(r => { if (alive) setTax(r) })
      .catch(() => { if (alive) setTax(null) })
    return () => { alive = false }
  }, [book.id, taxYear])

  const years = [year, year - 1, year - 2]

  return (
    <div className="space-y-4">
      {/* P&L */}
      <div className="card p-5 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <h2 className="font-semibold text-sm uppercase tracking-wide text-charcoal-500 dark:text-charcoal-400">
            Income statement
          </h2>
          <div className="flex gap-1.5">
            <select className="input w-24" value={pnlYear} onChange={e => setPnlYear(Number(e.target.value))}>
              {years.map(y => <option key={y} value={y}>{y}</option>)}
            </select>
            <select className="input w-24" value={period} onChange={e => setPeriod(e.target.value)}>
              <option value="year">Year</option>
              <option value="quarter">Quarter</option>
              <option value="month">Month</option>
            </select>
            {period === 'quarter' && (
              <select className="input w-20" value={quarter} onChange={e => setQuarter(Number(e.target.value))}>
                {[1, 2, 3, 4].map(q => <option key={q} value={q}>Q{q}</option>)}
              </select>
            )}
            {period === 'month' && (
              <select className="input w-20" value={month} onChange={e => setMonth(Number(e.target.value))}>
                {Array.from({ length: 12 }, (_v, i) => i + 1).map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            )}
          </div>
        </div>

        {!pnl ? (
          <p className="text-sm text-charcoal-500 dark:text-charcoal-400">{error || 'Loading…'}</p>
        ) : (
          <>
            <div className="grid grid-cols-3 gap-3 text-center">
              <div>
                <p className="text-xs text-charcoal-500 dark:text-charcoal-400">Income</p>
                <p className="font-semibold text-green-600 dark:text-green-400">{fmtMoney(pnl.income_cents, book.currency)}</p>
              </div>
              <div>
                <p className="text-xs text-charcoal-500 dark:text-charcoal-400">Expenses</p>
                <p className="font-semibold text-red-500 dark:text-red-400">{fmtMoney(pnl.expense_cents, book.currency)}</p>
              </div>
              <div>
                <p className="text-xs text-charcoal-500 dark:text-charcoal-400">Net ({pnl.period})</p>
                <p className={`font-semibold ${pnl.net_cents >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-500 dark:text-red-400'}`}>
                  {fmtMoney(pnl.net_cents, book.currency)}
                </p>
              </div>
            </div>
            <div className="grid md:grid-cols-2 gap-4">
              {pnl.income_by_category.length > 0 && (
                <div>
                  <p className="text-xs font-semibold uppercase tracking-widest text-charcoal-500 dark:text-charcoal-400 mb-1.5">Income</p>
                  {pnl.income_by_category.map(e => (
                    <div key={e.category || 'un'} className="flex justify-between text-sm py-0.5">
                      <span className="text-charcoal-600 dark:text-charcoal-300">{e.category || 'Uncategorized'}</span>
                      <span>{fmtMoney(e.amount_cents, book.currency)}</span>
                    </div>
                  ))}
                </div>
              )}
              {pnl.expense_by_category.length > 0 && (
                <div>
                  <p className="text-xs font-semibold uppercase tracking-widest text-charcoal-500 dark:text-charcoal-400 mb-1.5">Expenses</p>
                  {pnl.expense_by_category.map(e => (
                    <div key={e.category || 'un'} className="flex justify-between text-sm py-0.5">
                      <span className="text-charcoal-600 dark:text-charcoal-300">{e.category || 'Uncategorized'}</span>
                      <span>{fmtMoney(e.amount_cents, book.currency)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {/* Tax summary */}
      <div className="card p-5 space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="font-semibold text-sm uppercase tracking-wide text-charcoal-500 dark:text-charcoal-400">
            Deductible expenses
          </h2>
          <div className="flex gap-1.5">
            <select className="input w-24" value={taxYear} onChange={e => setTaxYear(Number(e.target.value))}>
              {years.map(y => <option key={y} value={y}>{y}</option>)}
            </select>
            <button
              onClick={() => financeApi.taxCsv(book.id, taxYear).catch(() => {})}
              className="btn-ghost text-xs"
              disabled={!tax || tax.count === 0}
            >
              ⬇ CSV for the accountant
            </button>
          </div>
        </div>
        {!tax || tax.count === 0 ? (
          <p className="text-sm text-charcoal-500 dark:text-charcoal-400">
            No deductible transactions in {taxYear}. Flag them in the transaction editor (deductible + tax category).
          </p>
        ) : (
          <>
            <div className="flex justify-between text-sm font-medium">
              <span>{tax.count} deductible transactions</span>
              <span>{fmtMoney(tax.total_cents, book.currency)}</span>
            </div>
            <div className="space-y-1">
              {tax.buckets.map(b => (
                <div key={b.tax_category} className="flex justify-between text-sm text-charcoal-600 dark:text-charcoal-300">
                  <span>{b.tax_category} ({b.count})</span>
                  <span>{fmtMoney(b.amount_cents, book.currency)}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
