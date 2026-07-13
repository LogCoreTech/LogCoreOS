import { useEffect, useState } from 'react'
import { finance as financeApi } from '../../lib/api'
import { fmtMoney } from './money'

// Bank sync panel — connections are admin-managed: members REQUEST a
// connection (admins get notified and enter the SimpleFIN setup token in
// Admin → Bank Connections), then map connected bank accounts onto their
// own books here. Pool books are only offered to admins.
export default function SimpleFinPanel({ books, isAdmin, workspace, onClose }) {
  const [status, setStatus] = useState(null)
  const [bankAccounts, setBankAccounts] = useState(null)
  const [selections, setSelections] = useState({}) // sf_account_id -> "store|bookId|accountId" | ''
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    financeApi.sfStatus().then(s => {
      setStatus(s)
      if (s.connected) {
        const initial = {}
        for (const e of s.account_map || []) {
          initial[e.simplefin_account_id] =
            `${e.target.store}|${e.target.book_id}|${e.target.account_id}`
        }
        setSelections(initial)
        financeApi.sfAccounts().then(setBankAccounts).catch(err => setError(err.message))
      }
    }).catch(err => setError(err.message))
  }, [])

  // Books this user may feed from a bank: own (edit) always; pools admin-only
  const targetBooks = (books || []).filter(b =>
    b._access === 'edit' && (isAdmin || !b._owner)
  )

  function targetOptions() {
    const opts = []
    for (const b of targetBooks) {
      const store = b._owner === 'household' ? 'household' : b._owner === 'team' ? 'team' : 'self'
      for (const a of (b.accounts || []).filter(a => !a.archived)) {
        opts.push({
          value: `${store}|${b.id}|${a.id}`,
          label: `${b.icon} ${b.name} → ${a.name}`,
        })
      }
    }
    return opts
  }

  async function requestConnection() {
    setBusy(true); setError('')
    try {
      const r = await financeApi.sfRequest()
      setMsg(`Request sent — ${r.notified_admins} admin${r.notified_admins === 1 ? '' : 's'} notified.`)
    } catch (err) {
      setError(err.message || 'Request failed')
    } finally {
      setBusy(false)
    }
  }

  async function saveMapping() {
    setBusy(true); setError(''); setMsg('')
    try {
      const byId = Object.fromEntries((bankAccounts || []).map(a => [a.id, a]))
      const entries = Object.entries(selections)
        .filter(([, v]) => v)
        .map(([sfId, v]) => {
          const [store, bookId, accountId] = v.split('|')
          return {
            simplefin_account_id: sfId,
            bank_name: byId[sfId]?.org || '',
            account_name: byId[sfId]?.name || '',
            target: { store, workspace, book_id: bookId, account_id: accountId },
            enabled: true,
          }
        })
      const s = await financeApi.sfSetMapping(entries)
      setStatus(s)
      setMsg('Mapping saved. Transactions arrive on the next sync (admins can trigger one now).')
    } catch (err) {
      setError(err.message || 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  const options = targetOptions()

  return (
    <div className="modal-overlay">
      <div className="modal-card max-w-lg w-full p-5 space-y-4 overflow-y-auto">
        <h3 className="font-semibold">🏦 Bank sync</h3>

        {!status ? (
          <div className="h-16 animate-pulse bg-charcoal-100 dark:bg-charcoal-800 rounded-lg" />
        ) : !status.connected ? (
          <>
            <p className="text-sm text-charcoal-600 dark:text-charcoal-300">
              LogCore pulls spending data through <span className="font-medium">SimpleFIN</span> —
              a read-only bridge. Your bank password is never entered here and never stored;
              the connection can only <em>read</em> balances and transactions, never move money.
            </p>
            <ol className="text-sm text-charcoal-600 dark:text-charcoal-300 list-decimal ml-5 space-y-1">
              <li>Sign up at <span className="font-mono">bridge.simplefin.org</span> and connect your bank there.</li>
              <li>Request a connection below — an admin will add your setup token.</li>
              <li>Come back here to map your bank accounts onto your books.</li>
            </ol>
            {msg ? (
              <p className="text-sm text-green-600 dark:text-green-400">{msg}</p>
            ) : (
              <button onClick={requestConnection} disabled={busy} className="btn-primary w-full">
                {busy ? 'Sending…' : 'Request bank connection'}
              </button>
            )}
          </>
        ) : (
          <>
            <div className="flex items-center gap-2 text-sm">
              <div className="w-2 h-2 rounded-full bg-green-500" />
              <span>Connected</span>
              {status.last_sync && (
                <span className="text-xs text-charcoal-500 dark:text-charcoal-400">
                  · last sync {new Date(status.last_sync).toLocaleString()}
                </span>
              )}
            </div>
            {status.last_error && (
              <p className="text-xs text-red-500">Last sync problem: {status.last_error}</p>
            )}

            {!bankAccounts ? (
              <div className="h-16 animate-pulse bg-charcoal-100 dark:bg-charcoal-800 rounded-lg" />
            ) : bankAccounts.length === 0 ? (
              <p className="text-sm text-charcoal-500 dark:text-charcoal-400">
                No bank accounts found on the connection yet.
              </p>
            ) : (
              <div className="space-y-3">
                <p className="text-xs text-charcoal-500 dark:text-charcoal-400">
                  Point each bank account at a book account. Unmapped accounts are ignored.
                </p>
                {bankAccounts.map(a => (
                  <div key={a.id} className="flex items-center gap-2">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm truncate">{a.org ? `${a.org} — ` : ''}{a.name}</p>
                      <p className="text-xs text-charcoal-500 dark:text-charcoal-400">
                        Bank balance {fmtMoney(a.balance_cents, a.currency)}
                      </p>
                    </div>
                    <select
                      className="input w-52 shrink-0"
                      value={selections[a.id] || ''}
                      onChange={e => setSelections({ ...selections, [a.id]: e.target.value })}
                    >
                      <option value="">— not synced —</option>
                      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </select>
                  </div>
                ))}
                {options.length === 0 && (
                  <p className="text-xs text-red-500">
                    No book accounts to map onto — create a book with at least one account first.
                  </p>
                )}
              </div>
            )}
            {msg && <p className="text-sm text-green-600 dark:text-green-400">{msg}</p>}
          </>
        )}

        {error && <p className="text-sm text-red-500">{error}</p>}

        <div className="flex gap-2">
          <button onClick={onClose} className="btn-ghost flex-1">Close</button>
          {status?.connected && bankAccounts?.length > 0 && (
            <button onClick={saveMapping} disabled={busy} className="btn-primary flex-1">
              {busy ? 'Saving…' : 'Save mapping'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
