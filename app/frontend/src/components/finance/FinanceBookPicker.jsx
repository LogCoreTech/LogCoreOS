import { useEffect, useState } from 'react'
import { finance as financeApi } from '../../module_packages/finance/frontend/api'

/**
 * Finance book selector for dashboard block config. A plain <select> rather
 * than a search picker — books are a small, bounded list per user, matching
 * the existing dropdown idiom already used for accounts/categories/assets in
 * TransactionModal.jsx. Falls back to a disabled input if Finance is
 * unavailable (403), matching the other pickers' graceful-degradation contract.
 *
 * Props: value (bookId|null), onChange(bookId|null), label, optional
 */
export default function FinanceBookPicker({ value, onChange, label, optional }) {
  const [available, setAvailable] = useState(true)
  const [books, setBooks] = useState([])

  useEffect(() => {
    financeApi.listBooks()
      .then(r => setBooks(Array.isArray(r) ? r : []))
      .catch(() => setAvailable(false))
  }, [])

  if (!available) {
    return (
      <div>
        {label && <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{label}</label>}
        <input className="input" disabled value="Finance unavailable" />
      </div>
    )
  }

  return (
    <div>
      {label && <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{label}</label>}
      <select
        className="input"
        value={value || ''}
        onChange={e => onChange(e.target.value || null)}
      >
        {optional && <option value="">— None —</option>}
        {!optional && !value && <option value="">Select a book…</option>}
        {books.map(b => (
          <option key={b.id} value={b.id}>{b.icon ? `${b.icon} ` : ''}{b.name}</option>
        ))}
      </select>
    </div>
  )
}
