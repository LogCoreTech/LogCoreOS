import { useState } from 'react'
import { finance as financeApi } from '../../lib/api'
import { toCents, centsToInput, todayStr } from './money'
import ContactPicker from '../contacts/ContactPicker'

export default function TransactionModal({ book, tx, allowedKinds, onClose, onSaved, onDeleted }) {
  const editing = !!tx
  const kinds = allowedKinds?.length ? allowedKinds : ['expense', 'income']
  const accounts = (book?.accounts || []).filter(a => !a.archived || (tx && tx.account_id === a.id))
  const [kind, setKind] = useState(
    tx ? (tx.amount_cents > 0 ? 'income' : 'expense') : (kinds.includes('expense') ? 'expense' : kinds[0])
  )
  const [amount, setAmount] = useState(tx ? centsToInput(tx.amount_cents) : '')
  const [date, setDate] = useState(tx?.date || todayStr())
  const [accountId, setAccountId] = useState(tx?.account_id || accounts[0]?.id || '')
  const [category, setCategory] = useState(tx?.category ?? '')
  const [payee, setPayee] = useState(tx?.payee || '')
  const [payeeContactId, setPayeeContactId] = useState(tx?.payee_contact_id || null)
  const [notes, setNotes] = useState(tx?.notes || '')
  const [deductible, setDeductible] = useState(!!tx?.deductible)
  const [taxCategory, setTaxCategory] = useState(tx?.tax_category || '')
  const [receipts, setReceipts] = useState(tx?.attachments || [])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const taxCategories = book?.tax_categories || []

  const categories = (book?.categories || []).filter(c => c.kind === kind)
  const categoryValid = category === '' || categories.some(c => c.name === category)

  async function submit(e) {
    e.preventDefault()
    setError('')
    const cents = toCents(amount)
    if (Number.isNaN(cents) || cents <= 0) { setError('Enter a valid amount above zero.'); return }
    if (!accountId) { setError('Pick an account — add one in book settings first.'); return }
    const payload = {
      date,
      amount_cents: kind === 'expense' ? -cents : cents,
      account_id: accountId,
      category: categoryValid ? category : '',
      payee,
      payee_contact_id: payeeContactId,
      notes,
      deductible,
      tax_category: deductible && taxCategory ? taxCategory : null,
    }
    setBusy(true)
    try {
      if (editing) await financeApi.updateTransaction(book.id, tx.id, payload)
      else await financeApi.addTransaction(book.id, payload)
      onSaved()
    } catch (err) {
      setError(err.message || 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    if (!window.confirm('Delete this transaction?')) return
    setBusy(true)
    try {
      await financeApi.removeTransaction(book.id, tx.id)
      onDeleted()
    } catch (err) {
      setError(err.message || 'Delete failed')
      setBusy(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-card max-w-md w-full p-5">
        <h3 className="font-semibold mb-4">{editing ? 'Edit transaction' : 'Add transaction'}</h3>
        <form onSubmit={submit} className="space-y-3">
          {/* Expense / Income toggle (contribute caps can limit the options) */}
          <div className="flex gap-1 bg-charcoal-100 dark:bg-charcoal-800 rounded-lg p-1">
            {kinds.map(k => (
              <button
                key={k} type="button" onClick={() => { setKind(k); setCategory('') }}
                className={`flex-1 py-1 rounded-md text-xs font-medium capitalize transition-colors ${
                  kind === k
                    ? 'bg-white dark:bg-charcoal-600 text-charcoal-900 dark:text-gray-100 shadow-sm'
                    : 'text-charcoal-500 dark:text-charcoal-400'
                }`}
              >
                {k === 'expense' ? '− Expense' : '+ Income'}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Amount</label>
              <input
                className="input" inputMode="decimal" placeholder="0.00"
                value={amount} onChange={e => setAmount(e.target.value)} autoFocus={!editing}
              />
            </div>
            <div>
              <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Date</label>
              <input type="date" className="input" value={date} onChange={e => setDate(e.target.value)} required />
            </div>
          </div>

          <div>
            <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Account</label>
            <select className="input" value={accountId} onChange={e => setAccountId(e.target.value)}>
              {accounts.length === 0 && <option value="">No accounts yet</option>}
              {accounts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </div>

          <div>
            <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Category</label>
            <select className="input" value={categoryValid ? category : ''} onChange={e => setCategory(e.target.value)}>
              <option value="">Uncategorized</option>
              {categories.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
            </select>
          </div>

          <ContactPicker
            label={kind === 'expense' ? 'Paid to' : 'Pay from'}
            placeholder={kind === 'expense' ? 'Who was paid' : 'Who paid you'}
            value={{ name: payee, contactId: payeeContactId }}
            onChange={(name, contactId) => { setPayee(name); setPayeeContactId(contactId) }}
          />

          <div>
            <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Notes</label>
            <input className="input" value={notes} onChange={e => setNotes(e.target.value)} maxLength={2000} />
          </div>

          {/* Tax flags (expenses) */}
          {kind === 'expense' && (
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-2 text-sm shrink-0">
                <input type="checkbox" checked={deductible} onChange={e => setDeductible(e.target.checked)} />
                Deductible
              </label>
              {deductible && (
                <select className="input flex-1" value={taxCategory} onChange={e => setTaxCategory(e.target.value)}>
                  <option value="">Tax bucket…</option>
                  {taxCategories.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              )}
            </div>
          )}

          {/* Receipts (existing transactions only) */}
          {editing && (
            <div>
              <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Receipts</label>
              <div className="space-y-1 mt-1">
                {receipts.map(r => (
                  <div key={r.id} className="flex items-center gap-2 text-xs">
                    <button
                      type="button"
                      onClick={async () => {
                        try {
                          const blob = await financeApi.receiptBlob(book.id, tx.id, r.id)
                          window.open(URL.createObjectURL(blob), '_blank')
                        } catch { /* noop */ }
                      }}
                      className="flex-1 min-w-0 truncate text-left text-orange-500 hover:underline"
                    >
                      📎 {r.filename}
                    </button>
                    <button
                      type="button"
                      onClick={async () => {
                        try {
                          await financeApi.removeReceipt(book.id, tx.id, r.id)
                          setReceipts(receipts.filter(x => x.id !== r.id))
                        } catch (err) { setError(err.message) }
                      }}
                      className="text-red-500 shrink-0"
                    >×</button>
                  </div>
                ))}
                <input
                  type="file" accept="image/jpeg,image/png,image/webp,image/avif,application/pdf"
                  className="text-xs text-charcoal-500 dark:text-charcoal-400"
                  onChange={async e => {
                    const file = e.target.files?.[0]
                    if (!file) return
                    try {
                      const meta = await financeApi.uploadReceipt(book.id, tx.id, file)
                      setReceipts([...receipts, meta])
                      e.target.value = ''
                    } catch (err) { setError(err.message) }
                  }}
                />
              </div>
            </div>
          )}

          {error && <p className="text-sm text-red-500">{error}</p>}

          <div className="flex gap-2 pt-1">
            {editing && (
              <button type="button" onClick={remove} disabled={busy} className="btn-ghost text-red-500">
                Delete
              </button>
            )}
            <div className="flex-1" />
            <button type="button" onClick={onClose} disabled={busy} className="btn-ghost">Cancel</button>
            <button type="submit" disabled={busy} className="btn-primary">{busy ? 'Saving…' : 'Save'}</button>
          </div>
        </form>
      </div>
    </div>
  )
}
