import { useEffect, useState } from 'react'
import { finance as financeApi } from '../../lib/api'
import { fmtMoney, toCents, centsToInput, todayStr } from './money'
import ContactPicker from '../contacts/ContactPicker'

const STATUS_STYLE = {
  draft: 'bg-charcoal-100 text-charcoal-600 dark:bg-charcoal-700 dark:text-charcoal-300',
  sent: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
  paid: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
  void: 'bg-charcoal-100 text-charcoal-400 dark:bg-charcoal-800 dark:text-charcoal-500 line-through',
}

export default function InvoicesPanel({ book, canEdit }) {
  const [invoices, setInvoices] = useState([])
  const [clients, setClients] = useState([])
  const [ar, setAr] = useState([])
  const [invoiceModal, setInvoiceModal] = useState(null)   // null | {invoice: null|obj}
  const [printInvoice, setPrintInvoice] = useState(null)
  const [error, setError] = useState('')

  function load() {
    financeApi.invoices(book.id).then(r => setInvoices(Array.isArray(r) ? r : [])).catch(() => {})
    financeApi.clients(book.id).then(r => setClients(Array.isArray(r) ? r : [])).catch(() => {})
    financeApi.arSummary(book.id).then(r => setAr(Array.isArray(r) ? r : [])).catch(() => {})
  }
  useEffect(() => { load() }, [book.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const clientName = Object.fromEntries(clients.map(c => [c.id, c.name]))
  const behind = ar.filter(e => e.overdue_cents > 0)

  return (
    <div className="space-y-4">
      {/* Who's behind (AR) */}
      {ar.length > 0 && (
        <div className="card p-5">
          <h2 className="font-semibold text-sm uppercase tracking-wide text-charcoal-500 dark:text-charcoal-400 mb-3">
            Clients — who's paid, who's behind
          </h2>
          <div className="space-y-2">
            {ar.map(e => (
              <div key={e.client_id || 'none'} className="flex items-center gap-2 text-sm">
                <span className="flex-1 min-w-0 truncate">
                  {e.client_name}
                  {e.overdue_count > 0 && (
                    <span className="text-red-500 text-xs font-medium ml-2">
                      {e.overdue_count} OVERDUE
                    </span>
                  )}
                </span>
                <span className="text-xs text-charcoal-500 dark:text-charcoal-400 shrink-0">
                  paid {fmtMoney(e.paid_cents, book.currency)}
                  {e.last_payment ? ` (last ${e.last_payment})` : ''}
                </span>
                <span className={`font-medium shrink-0 ${e.outstanding_cents > 0 ? (e.overdue_cents > 0 ? 'text-red-500' : '') : 'text-green-600 dark:text-green-400'}`}>
                  {e.outstanding_cents > 0 ? `${fmtMoney(e.outstanding_cents, book.currency)} due` : 'settled'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Invoices */}
      <div className="card p-5 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <h2 className="font-semibold text-sm uppercase tracking-wide text-charcoal-500 dark:text-charcoal-400">
            Invoices
          </h2>
          {canEdit && (
            <button onClick={() => setInvoiceModal({ invoice: null })} className="btn-primary text-xs">
              ＋ Invoice
            </button>
          )}
        </div>

        {invoices.length === 0 ? (
          <p className="text-sm text-charcoal-500 dark:text-charcoal-400">
            No invoices yet.{canEdit ? ' Create one and pick a contact as the client.' : ''}
          </p>
        ) : (
          <div className="space-y-2">
            {invoices.map(invoice => (
              <button
                key={invoice.id}
                onClick={() => setInvoiceModal({ invoice })}
                className="w-full flex items-center gap-2 text-left text-sm hover:bg-charcoal-50 dark:hover:bg-charcoal-800/60 rounded-lg px-2 py-1.5 transition-colors"
              >
                <span className="font-mono text-xs text-charcoal-500 dark:text-charcoal-400 shrink-0">{invoice.number}</span>
                <span className="flex-1 min-w-0 truncate">{clientName[invoice.client_id] || '(no client)'}</span>
                {invoice.overdue && <span className="text-red-500 text-xs font-medium shrink-0">OVERDUE</span>}
                <span className={`badge shrink-0 ${STATUS_STYLE[invoice.status] || ''}`}>{invoice.status}</span>
                <span className="font-medium shrink-0">
                  {invoice.balance_cents > 0 && invoice.status !== 'draft'
                    ? `${fmtMoney(invoice.balance_cents, book.currency)} due`
                    : fmtMoney(invoice.total_cents, book.currency)}
                </span>
              </button>
            ))}
          </div>
        )}

      </div>

      {error && <p className="text-sm text-red-500">{error}</p>}

      {invoiceModal && (
        <InvoiceModal
          key={invoiceModal.invoice?.id || 'new'}
          book={book}
          invoice={invoiceModal.invoice}
          clients={clients}
          canEdit={canEdit}
          onClose={() => setInvoiceModal(null)}
          onChanged={() => { setInvoiceModal(null); load() }}
          onPrint={inv => setPrintInvoice(inv)}
        />
      )}
      {printInvoice && (
        <InvoicePrint
          book={book}
          invoice={printInvoice}
          client={clients.find(c => c.id === printInvoice.client_id)}
          onClose={() => setPrintInvoice(null)}
        />
      )}
    </div>
  )
}

function InvoiceModal({ book, invoice, clients, canEdit, onClose, onChanged, onPrint }) {
  const editing = !!invoice
  const [clientId, setClientId] = useState(invoice?.client_id || '')
  const [clientName, setClientName] = useState(clients.find(c => c.id === invoice?.client_id)?.name || '')

  // Pick or quick-create a CRM contact, then find-or-create the matching book
  // client so invoices + AR keep working while Contacts is the entry point.
  async function chooseClient(name, contactId) {
    setClientName(name)
    if (!name) { setClientId(''); return }
    const existing = clients.find(c => (contactId && c.contact_id === contactId) || c.name === name)
    if (existing) { setClientId(existing.id); return }
    try {
      const c = await financeApi.addClient(book.id, { name, contact_id: contactId || null })
      setClientId(c.id)
    } catch { /* leave clientId as-is */ }
  }

  const [issueDate, setIssueDate] = useState(invoice?.issue_date || todayStr())
  const [dueDate, setDueDate] = useState(invoice?.due_date || '')
  const [taxPct, setTaxPct] = useState(invoice?.tax_pct ?? 0)
  const [notes, setNotes] = useState(invoice?.notes || '')
  const [items, setItems] = useState(
    invoice?.line_items?.map(i => ({ description: i.description, qty: String(i.qty), unit: centsToInput(i.unit_cents) }))
    || [{ description: '', qty: '1', unit: '' }]
  )
  const [payAmount, setPayAmount] = useState('')
  const [payAccount, setPayAccount] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  function buildLineItems() {
    const out = []
    for (const item of items) {
      if (!item.description.trim() && !item.unit) continue
      const unit = toCents(item.unit)
      const qty = parseFloat(item.qty) || 1
      if (!item.description.trim() || Number.isNaN(unit)) {
        throw new Error('Each line item needs a description and a valid amount.')
      }
      out.push({ description: item.description.trim(), qty, unit_cents: unit })
    }
    if (out.length === 0) throw new Error('Add at least one line item.')
    return out
  }

  async function save(e) {
    e.preventDefault()
    setBusy(true); setError('')
    try {
      const payload = {
        client_id: clientId || null, issue_date: issueDate, due_date: dueDate,
        line_items: buildLineItems(), tax_pct: parseFloat(taxPct) || 0, notes,
      }
      if (editing) await financeApi.updateInvoice(book.id, invoice.id, payload)
      else await financeApi.createInvoice(book.id, payload)
      onChanged()
    } catch (err) {
      setError(err.message || 'Save failed'); setBusy(false)
    }
  }

  async function setStatus(status) {
    try {
      await financeApi.updateInvoice(book.id, invoice.id, { status })
      onChanged()
    } catch (err) { setError(err.message) }
  }

  async function recordPayment() {
    const cents = payAmount ? toCents(payAmount) : invoice.balance_cents
    if (Number.isNaN(cents) || cents <= 0) { setError('Enter a valid payment amount.'); return }
    setBusy(true); setError('')
    try {
      await financeApi.recordPayment(book.id, invoice.id, {
        amount_cents: cents,
        account_id: payAccount || null,
      })
      onChanged()
    } catch (err) {
      setError(err.message || 'Payment failed'); setBusy(false)
    }
  }

  async function remove() {
    if (!window.confirm(`Delete invoice ${invoice.number}?`)) return
    try {
      await financeApi.removeInvoice(book.id, invoice.id)
      onChanged()
    } catch (err) { setError(err.message) }
  }

  const accounts = (book.accounts || []).filter(a => !a.archived)
  const subtotal = items.reduce((sum, i) => {
    const unit = toCents(i.unit); const qty = parseFloat(i.qty) || 1
    return Number.isNaN(unit) ? sum : sum + Math.round(unit * qty)
  }, 0)
  const total = Math.round(subtotal * (1 + (parseFloat(taxPct) || 0) / 100))

  return (
    <div className="modal-overlay">
      <div className="modal-card max-w-lg w-full p-5 space-y-4 overflow-y-auto">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold">{editing ? `Invoice ${invoice.number}` : 'New invoice'}</h3>
          {editing && (
            <div className="flex items-center gap-2">
              {invoice.overdue && <span className="text-red-500 text-xs font-medium">OVERDUE</span>}
              <span className={`badge ${STATUS_STYLE[invoice.status] || ''}`}>{invoice.status}</span>
            </div>
          )}
        </div>

        <form onSubmit={save} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <ContactPicker
              label="Client (contact)"
              placeholder="Pick or add a contact…"
              value={{ name: clientName, contactId: null }}
              onChange={chooseClient}
            />
            <div>
              <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Tax %</label>
              <input className="input" inputMode="decimal" value={taxPct} onChange={e => setTaxPct(e.target.value)} />
            </div>
            <div>
              <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Issued</label>
              <input type="date" className="input" value={issueDate} onChange={e => setIssueDate(e.target.value)} required />
            </div>
            <div>
              <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Due</label>
              <input type="date" className="input" value={dueDate} onChange={e => setDueDate(e.target.value)} required />
            </div>
          </div>

          <div>
            <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Line items</label>
            <div className="space-y-1.5">
              {items.map((item, idx) => (
                <div key={idx} className="flex gap-1.5">
                  <input className="input flex-1" placeholder="Description" value={item.description}
                    onChange={e => setItems(items.map((it, i) => i === idx ? { ...it, description: e.target.value } : it))}
                    maxLength={200} />
                  <input className="input w-14" placeholder="Qty" inputMode="decimal" value={item.qty}
                    onChange={e => setItems(items.map((it, i) => i === idx ? { ...it, qty: e.target.value } : it))} />
                  <input className="input w-24" placeholder="Unit $" inputMode="decimal" value={item.unit}
                    onChange={e => setItems(items.map((it, i) => i === idx ? { ...it, unit: e.target.value } : it))} />
                  <button type="button" onClick={() => setItems(items.filter((_it, i) => i !== idx))}
                    disabled={items.length === 1} className="btn-ghost px-2 text-red-500 disabled:opacity-30">×</button>
                </div>
              ))}
            </div>
            <button type="button" onClick={() => setItems([...items, { description: '', qty: '1', unit: '' }])}
              className="btn-ghost text-xs mt-1.5">＋ Line</button>
          </div>

          <input className="input" placeholder="Notes (shown on the invoice)" value={notes}
            onChange={e => setNotes(e.target.value)} maxLength={2000} />

          <div className="flex items-center justify-between text-sm">
            <span className="text-charcoal-500 dark:text-charcoal-400">
              Subtotal {fmtMoney(subtotal, book.currency)}{parseFloat(taxPct) > 0 ? ` + ${taxPct}% tax` : ''}
            </span>
            <span className="font-semibold">{fmtMoney(total, book.currency)}</span>
          </div>

          {error && <p className="text-sm text-red-500">{error}</p>}

          {canEdit && (
            <div className="flex gap-2 pt-1">
              {editing && <button type="button" onClick={remove} className="btn-ghost text-red-500 text-xs">Delete</button>}
              <div className="flex-1" />
              <button type="button" onClick={onClose} className="btn-ghost">Close</button>
              <button type="submit" disabled={busy} className="btn-primary">{busy ? '…' : 'Save'}</button>
            </div>
          )}
        </form>

        {editing && (
          <div className="pt-3 border-t border-charcoal-200 dark:border-charcoal-700 space-y-3">
            {/* Lifecycle + print */}
            <div className="flex gap-1.5 flex-wrap">
              {canEdit && invoice.status === 'draft' && (
                <button onClick={() => setStatus('sent')} className="btn-ghost text-xs">Mark sent</button>
              )}
              {canEdit && invoice.status !== 'void' && invoice.status !== 'paid' && (
                <button onClick={() => setStatus('void')} className="btn-ghost text-xs">Void</button>
              )}
              <button onClick={() => onPrint(invoice)} className="btn-ghost text-xs">🖨 Print / PDF</button>
            </div>

            {/* Payments */}
            {invoice.payments?.length > 0 && (
              <div className="space-y-1">
                {invoice.payments.map(p => (
                  <div key={p.id} className="flex items-center justify-between text-xs text-charcoal-500 dark:text-charcoal-400">
                    <span>{p.date} {p.method && `· ${p.method}`}{p.tx_id ? ' · logged in ledger' : ''}</span>
                    <span className="flex items-center gap-2">
                      <span className="text-green-600 dark:text-green-400">{fmtMoney(p.amount_cents, book.currency)}</span>
                      {canEdit && (
                        <button onClick={async () => {
                          try { await financeApi.removePayment(book.id, invoice.id, p.id); onChanged() }
                          catch (err) { setError(err.message) }
                        }} className="text-red-500">×</button>
                      )}
                    </span>
                  </div>
                ))}
              </div>
            )}
            {canEdit && invoice.balance_cents > 0 && invoice.status !== 'void' && (
              <div className="flex gap-2">
                <input className="input w-28" inputMode="decimal"
                  placeholder={centsToInput(invoice.balance_cents)}
                  value={payAmount} onChange={e => setPayAmount(e.target.value)} title="Payment amount (blank = full balance)" />
                <select className="input flex-1" value={payAccount} onChange={e => setPayAccount(e.target.value)}>
                  <option value="">Don't log a transaction</option>
                  {accounts.map(a => <option key={a.id} value={a.id}>Log income → {a.name}</option>)}
                </select>
                <button onClick={recordPayment} disabled={busy} className="btn-primary shrink-0 text-sm">
                  Record payment
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// Printable invoice — client-side print CSS, no server dependency.
function InvoicePrint({ book, invoice, client, onClose }) {
  useEffect(() => {
    const timer = setTimeout(() => window.print(), 300)
    return () => clearTimeout(timer)
  }, [])

  return (
    <div className="fixed inset-0 z-[100] bg-white text-black overflow-y-auto print:static" id="invoice-print">
      <style>{`
        @media print {
          body * { visibility: hidden; }
          #invoice-print, #invoice-print * { visibility: visible; }
          #invoice-print { position: absolute; inset: 0; }
        }
      `}</style>
      <div className="max-w-2xl mx-auto p-10">
        <div className="flex justify-between items-start mb-10">
          <div>
            <h1 className="text-3xl font-bold">INVOICE</h1>
            <p className="text-sm mt-1">{invoice.number}</p>
          </div>
          <div className="text-right text-sm">
            <p className="font-semibold">{book.name}</p>
            <p>Issued {invoice.issue_date}</p>
            <p>Due {invoice.due_date}</p>
          </div>
        </div>

        {client && (
          <div className="mb-8 text-sm">
            <p className="text-xs uppercase tracking-wide mb-1" style={{ color: '#666' }}>Bill to</p>
            <p className="font-semibold">{client.name}</p>
            {client.email && <p>{client.email}</p>}
            {client.phone && <p>{client.phone}</p>}
          </div>
        )}

        <table className="w-full text-sm mb-8" style={{ borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #000' }}>
              <th className="text-left py-2">Description</th>
              <th className="text-right py-2">Qty</th>
              <th className="text-right py-2">Unit</th>
              <th className="text-right py-2">Amount</th>
            </tr>
          </thead>
          <tbody>
            {invoice.line_items.map((item, i) => (
              <tr key={i} style={{ borderBottom: '1px solid #ddd' }}>
                <td className="py-2">{item.description}</td>
                <td className="text-right py-2">{item.qty}</td>
                <td className="text-right py-2">{fmtMoney(item.unit_cents, book.currency)}</td>
                <td className="text-right py-2">{fmtMoney(Math.round(item.qty * item.unit_cents), book.currency)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="flex justify-end mb-8">
          <div className="w-64 text-sm space-y-1">
            <div className="flex justify-between"><span>Subtotal</span><span>{fmtMoney(invoice.subtotal_cents, book.currency)}</span></div>
            {invoice.tax_pct > 0 && (
              <div className="flex justify-between"><span>Tax ({invoice.tax_pct}%)</span><span>{fmtMoney(invoice.total_cents - invoice.subtotal_cents, book.currency)}</span></div>
            )}
            <div className="flex justify-between font-bold text-base" style={{ borderTop: '2px solid #000', paddingTop: '4px' }}>
              <span>Total</span><span>{fmtMoney(invoice.total_cents, book.currency)}</span>
            </div>
            {invoice.paid_cents > 0 && (
              <>
                <div className="flex justify-between"><span>Paid</span><span>-{fmtMoney(invoice.paid_cents, book.currency)}</span></div>
                <div className="flex justify-between font-bold"><span>Balance due</span><span>{fmtMoney(invoice.balance_cents, book.currency)}</span></div>
              </>
            )}
          </div>
        </div>

        {invoice.notes && <p className="text-sm" style={{ color: '#444' }}>{invoice.notes}</p>}

        <div className="mt-10 print:hidden flex gap-2">
          <button onClick={() => window.print()} className="btn-primary">Print</button>
          <button onClick={onClose} className="btn-ghost">Close</button>
        </div>
      </div>
    </div>
  )
}
