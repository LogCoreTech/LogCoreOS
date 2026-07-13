import { useEffect, useState } from 'react'
import { finance as financeApi } from '../../lib/api'
import { fmtMoney, toCents, centsToInput } from './money'

const ACCOUNT_TYPES = ['checking', 'savings', 'credit', 'cash', 'other']
const CAP_LABELS = [
  ['add_expense', 'Add expenses'],
  ['add_income', 'Add income'],
  ['edit_own', 'Edit own entries'],
  ['see_balances', 'See balances'],
  ['see_all_tx', "See everyone's entries"],
]

function capsToFlags(caps) {
  const c = caps || {}
  const add = c.add || ['expense']
  return {
    add_expense: add.includes('expense'),
    add_income: add.includes('income'),
    edit_own: c.edit_own !== false,
    see_balances: !!c.see_balances,
    see_all_tx: !!c.see_all_tx,
  }
}

function flagsToCaps(flags) {
  const add = []
  if (flags.add_expense) add.push('expense')
  if (flags.add_income) add.push('income')
  return { add, edit_own: flags.edit_own, see_balances: flags.see_balances, see_all_tx: flags.see_all_tx }
}

// Book-audience editor: personal books use share requests (accept handshake);
// pool books use contributor grants. One row = scope (book or one account) +
// target + access level + contribute caps. All enforcement is server-side.
function SharingSection({ book }) {
  const isPool = book._owner === 'household' || book._owner === 'team'
  const field = isPool ? 'contributors' : 'shared_with'
  const [members, setMembers] = useState([])
  const [roles, setRoles] = useState([])
  const [rows, setRows] = useState(() => {
    const out = []
    for (const e of book[field] || []) out.push(_row('book', e))
    for (const a of book.accounts || []) {
      for (const e of a[field] || []) out.push(_row(a.id, e))
    }
    return out
  })
  const [hidden, setHidden] = useState(book.hidden_from || [])
  const [hiddenInput, setHiddenInput] = useState('')
  const [msg, setMsg] = useState(null)
  const [busy, setBusy] = useState(false)

  function _row(scope, entry) {
    return {
      scope,
      target: entry?.target || '',
      access: entry?.access || 'read',
      flags: capsToFlags(entry?.caps),
      accepted: entry?.accepted,
    }
  }

  useEffect(() => {
    financeApi.members().then(m => setMembers(Array.isArray(m) ? m.map(x => x.name) : [])).catch(() => {})
    financeApi.roles().then(r => setRoles(Array.isArray(r) ? r : [])).catch(() => {})
  }, [])

  const targetOptions = [
    ...(isPool ? [] : []),
    'team', 'household',
    ...roles.map(r => `role:${r}`),
    ...members,
  ]

  async function save() {
    setBusy(true); setMsg(null)
    try {
      const byScope = {}
      for (const row of rows) {
        if (!row.target) continue
        const entry = { target: row.target, access: row.access }
        if (row.access === 'contribute') entry.caps = flagsToCaps(row.flags)
        byScope[row.scope] = byScope[row.scope] || []
        byScope[row.scope].push(entry)
      }
      // Book-level audience + hidden list
      await financeApi.updateBookAccess(book.id, {
        [field]: byScope.book || [],
        hidden_from: hidden,
      })
      // Account-level overrides — also clear accounts that previously had entries
      const hadAccountEntries = new Set(
        (book.accounts || []).filter(a => (a[field] || []).length > 0).map(a => a.id)
      )
      for (const a of book.accounts || []) {
        const entries = byScope[a.id]
        if (entries) await financeApi.updateAccountAccess(book.id, a.id, { [field]: entries })
        else if (hadAccountEntries.has(a.id)) await financeApi.updateAccountAccess(book.id, a.id, { [field]: [] })
      }
      setMsg({ ok: true, text: isPool ? 'Contributor grants saved.' : 'Shares saved — new people get an Accept/Decline request.' })
    } catch (err) {
      setMsg({ ok: false, text: err.message || 'Save failed' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <h4 className="text-xs font-semibold uppercase tracking-widest text-charcoal-500 dark:text-charcoal-400 mb-2">
        {isPool ? 'Contributors' : 'Sharing'}
      </h4>
      <p className="text-[11px] text-charcoal-400 dark:text-charcoal-500 mb-2">
        {isPool
          ? 'Pool books are visible to every workspace member. Contributor grants let a member add/edit entries without admin rights — no accept step.'
          : 'Sharing sends an Accept/Decline request. Contribute = pick exactly what they can do (defaults: submit expenses only, no balances, own entries only). A row scoped to one account overrides the whole-book row for that account.'}
      </p>

      <div className="space-y-2">
        {rows.map((row, idx) => (
          <div key={idx} className="border border-charcoal-200 dark:border-charcoal-700 rounded-lg p-2 space-y-1.5">
            <div className="flex gap-1.5 flex-wrap items-center">
              <select className="input w-32" value={row.scope}
                onChange={e => setRows(rows.map((r, i) => i === idx ? { ...r, scope: e.target.value } : r))}>
                <option value="book">Whole book</option>
                {(book.accounts || []).map(a => <option key={a.id} value={a.id}>{a.name} only</option>)}
              </select>
              <select className="input flex-1 min-w-[7rem]" value={row.target}
                onChange={e => setRows(rows.map((r, i) => i === idx ? { ...r, target: e.target.value } : r))}>
                <option value="">Who…</option>
                {targetOptions.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
              <select className="input w-28" value={row.access}
                onChange={e => setRows(rows.map((r, i) => i === idx ? { ...r, access: e.target.value } : r))}>
                <option value="read">read</option>
                <option value="contribute">contribute</option>
                <option value="edit">edit</option>
              </select>
              {!isPool && row.accepted !== undefined && (
                <span className="text-[10px] text-charcoal-400" title="Who has accepted this share">
                  {row.accepted?.length ? `✓ ${row.accepted.length}` : 'pending'}
                </span>
              )}
              <button onClick={() => setRows(rows.filter((_r, i) => i !== idx))}
                className="btn-ghost px-2 text-red-500">×</button>
            </div>
            {row.access === 'contribute' && (
              <div className="flex flex-wrap gap-x-3 gap-y-1">
                {CAP_LABELS.map(([key, label]) => (
                  <label key={key} className="flex items-center gap-1 text-[11px] text-charcoal-500 dark:text-charcoal-400">
                    <input type="checkbox" checked={row.flags[key]}
                      onChange={e => setRows(rows.map((r, i) =>
                        i === idx ? { ...r, flags: { ...r.flags, [key]: e.target.checked } } : r))} />
                    {label}
                  </label>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      <button onClick={() => setRows([...rows, _row('book', null)])} className="btn-ghost text-xs mt-2">
        ＋ {isPool ? 'Contributor' : 'Share'}
      </button>

      {/* Hidden from */}
      <div className="flex flex-wrap gap-1.5 items-center mt-2">
        <span className="text-[11px] text-charcoal-500 dark:text-charcoal-400">Hidden from:</span>
        {hidden.map(h => (
          <span key={h} className="badge bg-charcoal-100 text-charcoal-600 dark:bg-charcoal-700 dark:text-charcoal-300 inline-flex items-center gap-1">
            {h}
            <button onClick={() => setHidden(hidden.filter(x => x !== h))} className="hover:text-red-500 leading-none">×</button>
          </span>
        ))}
        <select className="input w-32 text-xs" value={hiddenInput}
          onChange={e => {
            const v = e.target.value
            if (v && !hidden.includes(v)) setHidden([...hidden, v])
            setHiddenInput('')
          }}>
          <option value="">＋ hide…</option>
          {[...roles.map(r => `role:${r}`), ...members].filter(t => !hidden.includes(t)).map(t => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </div>

      {msg && (
        <p className={`text-sm mt-2 ${msg.ok ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>{msg.text}</p>
      )}
      <button onClick={save} disabled={busy} className="btn-primary w-full mt-2 text-sm">
        {busy ? 'Saving…' : isPool ? 'Save contributors' : 'Save sharing'}
      </button>
    </div>
  )
}

export default function BookSettings({ book, onClose, onChanged, onDeletedBook }) {
  const [name, setName] = useState(book.name)
  const [icon, setIcon] = useState(book.icon || '💰')
  const [currency, setCurrency] = useState(book.currency || 'USD')
  const [categories, setCategories] = useState(book.categories || [])
  const [newCat, setNewCat] = useState('')
  const [newCatKind, setNewCatKind] = useState('expense')
  const [taxCats, setTaxCats] = useState(book.tax_categories || [])
  const [newTaxCat, setNewTaxCat] = useState('')
  const [invoicePrefix, setInvoicePrefix] = useState(book.invoice_prefix || 'INV')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  // Accounts operate instantly against the API; local copy mirrors server state
  const [accounts, setAccounts] = useState(book.accounts || [])
  const [newAcct, setNewAcct] = useState({ name: '', type: 'checking', opening: '' })
  // CSV import
  const [csvFile, setCsvFile] = useState(null)
  const [csvPreview, setCsvPreview] = useState(null)
  const [csvMap, setCsvMap] = useState({ date_col: '', amount_col: '', payee_col: '', notes_col: '', date_format: '', invert_amounts: false, account_id: '' })
  const [csvResult, setCsvResult] = useState(null)
  const [csvBusy, setCsvBusy] = useState(false)

  async function pickCsv(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setCsvFile(file); setCsvPreview(null); setCsvResult(null); setError('')
    try {
      const p = await financeApi.csvPreview(book.id, file)
      setCsvPreview(p)
      const lower = p.headers.map(h => h.toLowerCase())
      setCsvMap(m => ({
        ...m,
        date_col: p.headers[lower.findIndex(h => h.includes('date'))] || '',
        amount_col: p.headers[lower.findIndex(h => h.includes('amount'))] || '',
        payee_col: p.headers[lower.findIndex(h => h.includes('desc') || h.includes('payee') || h.includes('merchant'))] || '',
        account_id: accounts.find(a => !a.archived)?.id || '',
      }))
    } catch (err) {
      setError(err.message || 'Could not read that CSV')
      setCsvFile(null)
    }
  }

  async function importCsv() {
    if (!csvFile || !csvMap.date_col || !csvMap.amount_col || !csvMap.account_id) {
      setError('Pick the date column, amount column and target account.'); return
    }
    setCsvBusy(true); setError(''); setCsvResult(null)
    try {
      const r = await financeApi.csvCommit(book.id, csvFile, csvMap)
      setCsvResult(r)
    } catch (err) {
      setError(err.message || 'Import failed')
    } finally {
      setCsvBusy(false)
    }
  }

  async function saveBook() {
    setError(''); setBusy(true)
    try {
      await financeApi.updateBook(book.id, {
        name, icon, currency, categories,
        tax_categories: taxCats, invoice_prefix: invoicePrefix,
      })
      onChanged()
    } catch (err) {
      setError(err.message || 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  function addCategory() {
    const trimmed = newCat.trim()
    if (!trimmed) return
    if (categories.some(c => c.name.toLowerCase() === trimmed.toLowerCase())) {
      setError('That category already exists.'); return
    }
    setCategories([...categories, { name: trimmed, kind: newCatKind }])
    setNewCat(''); setError('')
  }

  async function addAccount() {
    const trimmed = newAcct.name.trim()
    if (!trimmed) return
    const opening = newAcct.opening ? toCents(newAcct.opening) : 0
    if (Number.isNaN(opening)) { setError('Opening balance must be a number.'); return }
    setError(''); setBusy(true)
    try {
      const created = await financeApi.addAccount(book.id, {
        name: trimmed, type: newAcct.type, opening_balance_cents: opening,
      })
      setAccounts([...accounts, created])
      setNewAcct({ name: '', type: 'checking', opening: '' })
    } catch (err) {
      setError(err.message || 'Could not add account')
    } finally {
      setBusy(false)
    }
  }

  async function toggleAccountArchived(acct) {
    try {
      const updated = await financeApi.updateAccount(book.id, acct.id, { archived: !acct.archived })
      setAccounts(accounts.map(a => (a.id === acct.id ? updated : a)))
    } catch (err) {
      setError(err.message || 'Update failed')
    }
  }

  async function removeAccount(acct) {
    if (!window.confirm(`Delete account "${acct.name}"?`)) return
    try {
      await financeApi.removeAccount(book.id, acct.id)
      setAccounts(accounts.filter(a => a.id !== acct.id))
    } catch (err) {
      setError(err.message || 'Delete failed') // 409 when it still has transactions
    }
  }

  async function archiveBook() {
    try {
      await financeApi.updateBook(book.id, { archived: !book.archived })
      onChanged()
    } catch (err) {
      setError(err.message || 'Archive failed')
    }
  }

  async function deleteBook() {
    if (!window.confirm(`Delete the book "${book.name}"? This cannot be undone.`)) return
    try {
      await financeApi.removeBook(book.id)
      onDeletedBook()
    } catch (err) {
      setError(err.message || 'Delete failed') // 409 while transactions exist
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-card max-w-lg w-full p-5 space-y-5 overflow-y-auto">
        <h3 className="font-semibold">Book settings</h3>

        {/* Book meta */}
        <div className="grid grid-cols-[1fr_4rem_5rem] gap-2">
          <div>
            <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Name</label>
            <input className="input" value={name} onChange={e => setName(e.target.value)} maxLength={80} />
          </div>
          <div>
            <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Icon</label>
            <input className="input text-center" value={icon} onChange={e => setIcon(e.target.value)} maxLength={8} />
          </div>
          <div>
            <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Currency</label>
            <input className="input uppercase" value={currency} onChange={e => setCurrency(e.target.value)} maxLength={3} />
          </div>
        </div>

        {/* Accounts */}
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-widest text-charcoal-500 dark:text-charcoal-400 mb-2">Accounts</h4>
          <div className="space-y-2">
            {accounts.map(a => (
              <div key={a.id} className={`flex items-center gap-2 text-sm ${a.archived ? 'opacity-50' : ''}`}>
                <span className="flex-1 min-w-0 truncate">{a.name}</span>
                <span className="badge bg-charcoal-100 dark:bg-charcoal-700 text-charcoal-600 dark:text-charcoal-300 capitalize">{a.type}</span>
                <span className="text-xs text-charcoal-500 dark:text-charcoal-400 shrink-0">
                  opens {fmtMoney(a.opening_balance_cents, currency)}
                </span>
                <button onClick={() => toggleAccountArchived(a)} className="btn-ghost text-xs px-2" title={a.archived ? 'Unarchive' : 'Archive'}>
                  {a.archived ? '↩' : '🗄'}
                </button>
                <button onClick={() => removeAccount(a)} className="btn-ghost text-xs px-2 text-red-500" title="Delete">×</button>
              </div>
            ))}
            {accounts.length === 0 && (
              <p className="text-xs text-charcoal-500 dark:text-charcoal-400">No accounts yet — add one to start logging transactions.</p>
            )}
          </div>
          <div className="flex gap-2 mt-2">
            <input className="input flex-1" placeholder="Account name" value={newAcct.name}
              onChange={e => setNewAcct({ ...newAcct, name: e.target.value })} maxLength={60} />
            <select className="input w-28" value={newAcct.type} onChange={e => setNewAcct({ ...newAcct, type: e.target.value })}>
              {ACCOUNT_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
            <input className="input w-24" placeholder="0.00" inputMode="decimal" value={newAcct.opening}
              onChange={e => setNewAcct({ ...newAcct, opening: e.target.value })} title="Opening balance" />
            <button onClick={addAccount} disabled={busy} className="btn-ghost shrink-0">＋</button>
          </div>
        </div>

        {/* Categories */}
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-widest text-charcoal-500 dark:text-charcoal-400 mb-2">Categories</h4>
          <div className="flex flex-wrap gap-1.5 mb-2">
            {categories.map(c => (
              <span key={c.name} className={`badge inline-flex items-center gap-1 ${
                c.kind === 'income'
                  ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
                  : 'bg-charcoal-100 text-charcoal-700 dark:bg-charcoal-700 dark:text-charcoal-300'
              }`}>
                {c.name}
                <button onClick={() => setCategories(categories.filter(x => x.name !== c.name))}
                  className="hover:text-red-500 leading-none" title="Remove (transactions become uncategorized)">×</button>
              </span>
            ))}
          </div>
          <div className="flex gap-2">
            <input className="input flex-1" placeholder="New category" value={newCat}
              onChange={e => setNewCat(e.target.value)} maxLength={40}
              onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addCategory() } }} />
            <select className="input w-28" value={newCatKind} onChange={e => setNewCatKind(e.target.value)}>
              <option value="expense">expense</option>
              <option value="income">income</option>
            </select>
            <button onClick={addCategory} className="btn-ghost shrink-0">＋</button>
          </div>
          <p className="text-[11px] text-charcoal-400 dark:text-charcoal-500 mt-1">
            Category changes apply when you hit Save. Removing one relabels its transactions to Uncategorized.
          </p>
        </div>

        {/* Tax buckets + invoicing */}
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-widest text-charcoal-500 dark:text-charcoal-400 mb-2">Tax & invoicing</h4>
          <div className="flex flex-wrap gap-1.5 mb-2">
            {taxCats.map(t => (
              <span key={t} className="badge bg-charcoal-100 text-charcoal-700 dark:bg-charcoal-700 dark:text-charcoal-300 inline-flex items-center gap-1">
                {t}
                <button onClick={() => setTaxCats(taxCats.filter(x => x !== t))} className="hover:text-red-500 leading-none">×</button>
              </span>
            ))}
            {taxCats.length === 0 && (
              <span className="text-xs text-charcoal-400 dark:text-charcoal-500">
                No tax buckets yet — e.g. "Schedule C: Supplies", "Travel".
              </span>
            )}
          </div>
          <div className="flex gap-2">
            <input className="input flex-1" placeholder="New tax bucket" value={newTaxCat}
              onChange={e => setNewTaxCat(e.target.value)} maxLength={60}
              onKeyDown={e => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  const trimmed = newTaxCat.trim()
                  if (trimmed && !taxCats.includes(trimmed)) setTaxCats([...taxCats, trimmed])
                  setNewTaxCat('')
                }
              }} />
            <button onClick={() => {
              const trimmed = newTaxCat.trim()
              if (trimmed && !taxCats.includes(trimmed)) setTaxCats([...taxCats, trimmed])
              setNewTaxCat('')
            }} className="btn-ghost shrink-0">＋</button>
            <input className="input w-24 uppercase" title="Invoice number prefix" value={invoicePrefix}
              onChange={e => setInvoicePrefix(e.target.value)} maxLength={10} />
          </div>
          <p className="text-[11px] text-charcoal-400 dark:text-charcoal-500 mt-1">
            Buckets appear in the transaction editor when "Deductible" is checked. The prefix numbers new invoices ({invoicePrefix || 'INV'}-{new Date().getFullYear()}-0001). Saved with the Save button.
          </p>
        </div>

        {/* CSV import */}
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-widest text-charcoal-500 dark:text-charcoal-400 mb-2">Import CSV</h4>
          <p className="text-[11px] text-charcoal-400 dark:text-charcoal-500 mb-2">
            Import a bank statement export. Re-importing the same file skips rows it already has.
          </p>
          <input type="file" accept=".csv,text/csv" onChange={pickCsv}
            className="text-xs text-charcoal-500 dark:text-charcoal-400" />
          {csvPreview && (
            <div className="mt-3 space-y-2">
              <p className="text-xs text-charcoal-500 dark:text-charcoal-400">
                {csvPreview.total_rows} rows · columns: {csvPreview.headers.join(', ')}
              </p>
              <div className="grid grid-cols-2 gap-2">
                <select className="input" value={csvMap.date_col} onChange={e => setCsvMap({ ...csvMap, date_col: e.target.value })}>
                  <option value="">Date column…</option>
                  {csvPreview.headers.map(h => <option key={h} value={h}>{h}</option>)}
                </select>
                <select className="input" value={csvMap.amount_col} onChange={e => setCsvMap({ ...csvMap, amount_col: e.target.value })}>
                  <option value="">Amount column…</option>
                  {csvPreview.headers.map(h => <option key={h} value={h}>{h}</option>)}
                </select>
                <select className="input" value={csvMap.payee_col} onChange={e => setCsvMap({ ...csvMap, payee_col: e.target.value })}>
                  <option value="">Payee column (optional)</option>
                  {csvPreview.headers.map(h => <option key={h} value={h}>{h}</option>)}
                </select>
                <select className="input" value={csvMap.account_id} onChange={e => setCsvMap({ ...csvMap, account_id: e.target.value })}>
                  <option value="">Into account…</option>
                  {accounts.filter(a => !a.archived).map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>
              </div>
              <label className="flex items-center gap-2 text-xs text-charcoal-500 dark:text-charcoal-400">
                <input type="checkbox" checked={csvMap.invert_amounts}
                  onChange={e => setCsvMap({ ...csvMap, invert_amounts: e.target.checked })} />
                Flip signs (my bank exports spending as positive numbers)
              </label>
              <button onClick={importCsv} disabled={csvBusy} className="btn-primary w-full">
                {csvBusy ? 'Importing…' : `Import ${csvPreview.total_rows} rows`}
              </button>
              {csvResult && (
                <p className="text-sm text-green-600 dark:text-green-400">
                  Imported {csvResult.created}, skipped {csvResult.skipped} already-known.
                  {csvResult.errors?.length ? ` ${csvResult.errors.length} rows had problems.` : ''}
                </p>
              )}
            </div>
          )}
        </div>

        {/* Sharing / contributors — owner or pool admin only (shared-edit users never manage audience) */}
        {(!book._owner || book._owner === 'household' || book._owner === 'team') && (
          <SharingSection book={book} />
        )}

        {/* Danger zone */}
        <div className="flex items-center gap-2 pt-1 border-t border-charcoal-200 dark:border-charcoal-700">
          <button onClick={archiveBook} className="btn-ghost text-xs">
            {book.archived ? 'Unarchive book' : 'Archive book'}
          </button>
          <button onClick={deleteBook} className="btn-ghost text-xs text-red-500">Delete book</button>
        </div>

        {error && <p className="text-sm text-red-500">{error}</p>}

        <div className="flex gap-2">
          <button onClick={onClose} className="btn-ghost flex-1">Close</button>
          <button onClick={saveBook} disabled={busy} className="btn-primary flex-1">{busy ? 'Saving…' : 'Save'}</button>
        </div>
      </div>
    </div>
  )
}
