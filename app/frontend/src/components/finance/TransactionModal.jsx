import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { finance as financeApi } from '../../lib/api'
import { contacts as contactsApi } from '../../module_packages/contacts/frontend/api'
import { toCents, centsToInput, todayStr } from './money'
import ContactPicker from '../contacts/ContactPicker'

const KIND_LABELS = { expense: '− Expense', income: '+ Income', transfer: '⇄ Transfer' }

// Transfers are create-only here — editing/deleting an existing transfer leg
// routes to TransferEditModal instead (both legs move together), so `tx` is
// never a transfer leg by the time it reaches this component.
export default function TransactionModal({ book, tx, allowedKinds, assets, allBooks, userWorkspaces, workspace, onClose, onSaved, onDeleted }) {
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
  const [assetId, setAssetId] = useState(tx?.asset_id || '')
  const [notes, setNotes] = useState(tx?.notes || '')
  const [deductible, setDeductible] = useState(!!tx?.deductible)
  const [taxCategory, setTaxCategory] = useState(tx?.tax_category || '')
  const [receipts, setReceipts] = useState(tx?.attachments || [])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const taxCategories = book?.tax_categories || []
  const navigate = useNavigate()
  const [sourceDeal, setSourceDeal] = useState(null) // resolved when the tx carries a deal_id
  const amountRef = useRef(null)

  // The Amount field autofocuses on a genuinely new Expense/Income entry (a
  // deliberate "start typing immediately" convenience) — but for Transfer,
  // the books/accounts need picking first, and `autoFocus` is a mount-time-
  // only DOM attribute: it doesn't re-fire on a later kind switch, so a new
  // transaction that opens as Expense (the default) then gets switched to
  // Transfer left the field — and the on-screen numeric keyboard — focused
  // the whole time, covering the picker fields the user actually needed
  // (reported 2026-08-15, "auto pops up a numbers keyboard like it's
  // auto-clicking a field"). Explicitly blur on switching to Transfer.
  useEffect(() => {
    if (kind === 'transfer') amountRef.current?.blur()
  }, [kind])

  // Transfer-only state — a second workspace's books are fetched lazily,
  // only once "Transfer" is actually picked, since most transactions never
  // need it. Own-workspace books are already loaded (allBooks).
  const otherWorkspace = userWorkspaces?.includes('personal') && userWorkspaces?.includes('business')
    ? (workspace === 'business' ? 'personal' : 'business')
    : null
  const [otherWorkspaceBooks, setOtherWorkspaceBooks] = useState([])
  const [toBookId, setToBookId] = useState('')
  const [toAccountId, setToAccountId] = useState('')

  useEffect(() => {
    if (kind !== 'transfer' || !otherWorkspace || otherWorkspaceBooks.length > 0) return
    financeApi.listBooksForWorkspace(otherWorkspace)
      .then(r => setOtherWorkspaceBooks(Array.isArray(r) ? r.filter(b => !b.archived && b._access === 'edit') : []))
      .catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind])

  const transferBookOptions = [
    ...(allBooks || []).filter(b => !b.archived && (b._access === 'edit' || !b._access)).map(b => ({ ...b, _ws: workspace })),
    ...otherWorkspaceBooks.map(b => ({ ...b, _ws: otherWorkspace })),
  ]
  const toBook = transferBookOptions.find(b => b.id === toBookId)
  const toAccounts = (toBook?.accounts || []).filter(a => !a.archived)
  const currencyMismatch = kind === 'transfer' && toBook && book?.currency && toBook.currency !== book.currency

  useEffect(() => {
    if (kind !== 'transfer') return
    if (!toBookId && transferBookOptions.length > 0) setToBookId(transferBookOptions[0].id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, transferBookOptions.length])

  useEffect(() => {
    setToAccountId(toAccounts[0]?.id || '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [toBookId])

  useEffect(() => {
    if (!tx?.deal_id) return
    let alive = true
    contactsApi.getDeal(tx.deal_id)
      .then(d => { if (alive && d?.id) setSourceDeal(d) })
      .catch(() => {})
    return () => { alive = false }
  }, [tx?.deal_id])

  const categories = (book?.categories || []).filter(c => c.kind === kind)
  const categoryValid = category === '' || categories.some(c => c.name === category)

  async function submit(e) {
    e.preventDefault()
    setError('')
    const cents = toCents(amount)
    if (Number.isNaN(cents) || cents <= 0) { setError('Enter a valid amount above zero.'); return }

    if (kind === 'transfer') {
      if (!accountId) { setError('Pick a "from" account — add one in book settings first.'); return }
      if (!toBookId || !toAccountId) { setError('Pick a "to" book and account.'); return }
      if (book.id === toBookId && accountId === toAccountId) { setError('Pick two different accounts.'); return }
      if (currencyMismatch) { setError('Both books must use the same currency.'); return }
      setBusy(true)
      try {
        await financeApi.createTransfer({
          from_book_id: book.id,
          from_workspace: workspace,
          from_account_id: accountId,
          to_book_id: toBookId,
          to_workspace: toBook._ws,
          to_account_id: toAccountId,
          amount_cents: cents,
          date,
          notes,
        })
        onSaved()
      } catch (err) {
        setError(err.message || 'Transfer failed')
      } finally {
        setBusy(false)
      }
      return
    }

    if (!accountId) { setError('Pick an account — add one in book settings first.'); return }
    const payload = {
      date,
      amount_cents: kind === 'expense' ? -cents : cents,
      account_id: accountId,
      category: categoryValid ? category : '',
      payee,
      payee_contact_id: payeeContactId,
      asset_id: assetId || null,
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

        {/* Source chips — where this transaction came from */}
        {editing && (tx.invoice_id || sourceDeal) && (
          <div className="text-xs flex gap-2 flex-wrap -mt-2 mb-3">
            {tx.invoice_id && (
              <button
                type="button"
                onClick={() => { onClose(); navigate(`/finance?book=${book.id}&view=invoices`) }}
                className="badge bg-charcoal-100 dark:bg-charcoal-700 hover:underline"
              >🧾 From invoice</button>
            )}
            {sourceDeal && (
              <button
                type="button"
                onClick={() => navigate(`/contacts?contact=${sourceDeal._contact_id}`)}
                className="badge bg-charcoal-100 dark:bg-charcoal-700 hover:underline"
              >Deal: {sourceDeal.title}</button>
            )}
          </div>
        )}

        <form onSubmit={submit} className="space-y-3">
          {/* Expense / Income / Transfer toggle (contribute caps can limit the options) */}
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
                {KIND_LABELS[k] || k}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Amount</label>
              <input
                ref={amountRef}
                className="input" inputMode="decimal" placeholder="0.00"
                value={amount} onChange={e => setAmount(e.target.value)} autoFocus={!editing && kind !== 'transfer'}
              />
            </div>
            <div>
              <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Date</label>
              <input type="date" className="input" value={date} onChange={e => setDate(e.target.value)} required />
            </div>
          </div>

          <div>
            <label className="text-xs text-charcoal-500 dark:text-charcoal-400">{kind === 'transfer' ? 'From account' : 'Account'}</label>
            <select className="input" value={accountId} onChange={e => setAccountId(e.target.value)}>
              {accounts.length === 0 && <option value="">No accounts yet</option>}
              {accounts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </div>

          {/* Transfer target — a different book (possibly a different workspace)
              or a second account in this same book; picking this book back
              degenerates into an ordinary same-book transfer, no special-casing. */}
          {kind === 'transfer' && (
            <>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-charcoal-500 dark:text-charcoal-400">To book</label>
                  <select className="input" value={toBookId} onChange={e => setToBookId(e.target.value)}>
                    {transferBookOptions.length === 0 && <option value="">No books available</option>}
                    {transferBookOptions.map(b => (
                      <option key={`${b._ws}:${b.id}`} value={b.id}>
                        {b.name}{b._ws !== workspace ? ` (${b._ws === 'business' ? 'Business' : 'Personal'})` : ''}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-charcoal-500 dark:text-charcoal-400">To account</label>
                  <select className="input" value={toAccountId} onChange={e => setToAccountId(e.target.value)}>
                    {toAccounts.length === 0 && <option value="">No accounts yet</option>}
                    {toAccounts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                  </select>
                </div>
              </div>
              {currencyMismatch && (
                <p className="text-sm text-red-500">
                  {book.currency} → {toBook.currency}: both books must use the same currency.
                </p>
              )}
            </>
          )}

          {kind !== 'transfer' && (
            <div>
              <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Category</label>
              <select className="input" value={categoryValid ? category : ''} onChange={e => setCategory(e.target.value)}>
                <option value="">Uncategorized</option>
                {categories.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
              </select>
            </div>
          )}

          {kind !== 'transfer' && (
            <ContactPicker
              label={kind === 'expense' ? 'Paid to' : 'Pay from'}
              placeholder={kind === 'expense' ? 'Who was paid' : 'Who paid you'}
              value={{ name: payee, contactId: payeeContactId }}
              onChange={(name, contactId) => { setPayee(name); setPayeeContactId(contactId) }}
            />
          )}

          {/* Linked asset — only shown when an assets list is provided (assets module on) */}
          {kind !== 'transfer' && assets && assets.length > 0 && (
            <div>
              <label className="text-xs text-charcoal-500 dark:text-charcoal-400">
                Linked asset <span className="text-charcoal-400">(optional)</span>
              </label>
              <select className="input" value={assetId} onChange={e => setAssetId(e.target.value)}>
                <option value="">None</option>
                {assetId && !assets.some(a => a.id === assetId) && (
                  <option value={assetId}>(linked asset)</option>
                )}
                {assets.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </div>
          )}

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
