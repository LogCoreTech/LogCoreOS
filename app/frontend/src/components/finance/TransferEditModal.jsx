import { useState } from 'react'
import { finance as financeApi } from '../../lib/api'
import { toCents, centsToInput, fmtMoney } from './money'

// Edits or deletes both legs of a Transfer together. `book`/`workspace` are
// the side the row was clicked from; the peer side comes denormalized on the
// leg itself (transfer_peer_*) — no cross-book lookup needed to render this.
export default function TransferEditModal({ book, workspace, tx, onClose, onSaved, onDeleted }) {
  const isFromLeg = tx.amount_cents < 0
  const fromLabel = isFromLeg ? `${book.name} — this account` : `${tx.transfer_peer_book_name} — ${tx.transfer_peer_account_name}`
  const toLabel = isFromLeg ? `${tx.transfer_peer_book_name} — ${tx.transfer_peer_account_name}` : `${book.name} — this account`

  const [amount, setAmount] = useState(centsToInput(Math.abs(tx.amount_cents)))
  const [date, setDate] = useState(tx.date)
  const [notes, setNotes] = useState(tx.notes || '')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  function legIds() {
    return isFromLeg
      ? {
          from_book_id: book.id, from_workspace: workspace,
          to_book_id: tx.transfer_peer_book_id, to_workspace: tx.transfer_peer_workspace,
        }
      : {
          from_book_id: tx.transfer_peer_book_id, from_workspace: tx.transfer_peer_workspace,
          to_book_id: book.id, to_workspace: workspace,
        }
  }

  async function submit(e) {
    e.preventDefault()
    const cents = toCents(amount)
    if (Number.isNaN(cents) || cents <= 0) { setError('Enter a valid amount above zero.'); return }
    setError('')
    setBusy(true)
    try {
      await financeApi.updateTransfer(tx.transfer_pair_id, {
        ...legIds(),
        amount_cents: cents,
        date,
        notes,
      })
      onSaved()
    } catch (err) {
      setError(err.message || 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    if (!window.confirm('Delete this transfer? Both sides will be removed.')) return
    setBusy(true)
    try {
      await financeApi.removeTransfer(tx.transfer_pair_id, legIds())
      onDeleted()
    } catch (err) {
      setError(err.message || 'Delete failed')
      setBusy(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-card max-w-md w-full p-5">
        <h3 className="font-semibold mb-4">⇄ Edit transfer</h3>

        <div className="text-sm space-y-1 mb-4 p-3 rounded-lg bg-charcoal-50 dark:bg-charcoal-800">
          <p><span className="text-charcoal-500 dark:text-charcoal-400">From:</span> {fromLabel}</p>
          <p><span className="text-charcoal-500 dark:text-charcoal-400">To:</span> {toLabel}</p>
          <p className="text-xs text-charcoal-400 dark:text-charcoal-500">
            Currently {fmtMoney(Math.abs(tx.amount_cents), book.currency)} — to move this transfer to different books or accounts, delete it and create a new one.
          </p>
        </div>

        <form onSubmit={submit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Amount</label>
              <input
                className="input" inputMode="decimal" placeholder="0.00" autoFocus
                value={amount} onChange={e => setAmount(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Date</label>
              <input type="date" className="input" value={date} onChange={e => setDate(e.target.value)} required />
            </div>
          </div>

          <div>
            <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Notes</label>
            <input className="input" value={notes} onChange={e => setNotes(e.target.value)} maxLength={2000} />
          </div>

          {error && <p className="text-sm text-red-500">{error}</p>}

          <div className="flex gap-2 pt-1">
            <button type="button" onClick={remove} disabled={busy} className="btn-ghost text-red-500">Delete</button>
            <div className="flex-1" />
            <button type="button" onClick={onClose} disabled={busy} className="btn-ghost">Cancel</button>
            <button type="submit" disabled={busy} className="btn-primary">{busy ? 'Saving…' : 'Save'}</button>
          </div>
        </form>
      </div>
    </div>
  )
}
