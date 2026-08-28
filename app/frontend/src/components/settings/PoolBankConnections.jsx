import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { finance as financeApi } from '../../module_packages/finance/frontend/api'
import { fmtMoney } from '../finance/money'

const POOL_WORKSPACE = { household: 'personal', team: 'business' }

// Team and Household each render their own independent instance of this —
// intentionally not a combined/shared summary between the two pools.
export default function PoolBankConnections({ pool, accountLabel }) {
  const [rows, setRows] = useState(null) // null = loading
  const workspace = POOL_WORKSPACE[pool]

  const [status, setStatus] = useState(null) // null = loading
  const [bankAccounts, setBankAccounts] = useState(null)
  const [books, setBooks] = useState(null)
  const [selections, setSelections] = useState({}) // sf_account_id -> "bookId|accountId"
  const [tokenInput, setTokenInput] = useState('')
  const [showTokenInput, setShowTokenInput] = useState(false)
  const [revealed, setRevealed] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')

  async function loadStatus() {
    const s = await financeApi.sfPoolStatus(pool)
    setStatus(s)
    if (s.connected) {
      const initial = {}
      for (const e of s.account_map || []) {
        initial[e.simplefin_account_id] = `${e.target.book_id}|${e.target.account_id}`
      }
      setSelections(initial)
      const [accounts, allBooks] = await Promise.all([
        financeApi.sfPoolAccounts(pool).catch(err => { setError(err.message); return [] }),
        financeApi.listBooksForWorkspace(workspace).catch(() => []),
      ])
      setBankAccounts(accounts)
      setBooks((allBooks || []).filter(b => b._owner === pool))
    }
  }

  useEffect(() => {
    financeApi.sfPoolSummary(pool).then(r => setRows(Array.isArray(r) ? r : [])).catch(() => setRows([]))
    loadStatus().catch(err => setError(err.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pool])

  function targetOptions() {
    const opts = []
    for (const b of books || []) {
      for (const a of (b.accounts || []).filter(a => !a.archived)) {
        opts.push({ value: `${b.id}|${a.id}`, label: `${b.icon} ${b.name} → ${a.name}` })
      }
    }
    return opts
  }

  async function poolClaim() {
    if (!tokenInput.trim()) return
    setBusy(true); setError('')
    try {
      await financeApi.sfPoolClaim(pool, tokenInput.trim())
      setTokenInput('')
      setShowTokenInput(false)
      setMsg('Connected — map its accounts onto this pool’s books below.')
      await loadStatus()
    } catch (err) {
      setError(err.message || 'Claim failed')
    } finally {
      setBusy(false)
    }
  }

  async function poolSync() {
    setBusy(true); setError('')
    try {
      const r = await financeApi.sfPoolSync(pool)
      setMsg(`Synced — ${r.created} new, ${r.skipped} already known.`)
      await loadStatus()
    } catch (err) {
      setError(err.message || 'Sync failed')
    } finally {
      setBusy(false)
    }
  }

  async function poolReveal() {
    setBusy(true); setError('')
    try {
      const r = await financeApi.sfPoolReveal(pool)
      setRevealed(r.access_url)
    } catch (err) {
      setError(err.message || 'Reveal failed')
    } finally {
      setBusy(false)
    }
  }

  async function poolDisconnect() {
    if (!window.confirm(`Disconnect this ${accountLabel} account? Its imported transactions stay.`)) return
    setBusy(true); setError('')
    try {
      await financeApi.sfPoolDisconnect(pool)
      setMsg('Disconnected.')
      setBankAccounts(null)
      setBooks(null)
      await loadStatus()
    } catch (err) {
      setError(err.message || 'Disconnect failed')
    } finally {
      setBusy(false)
    }
  }

  async function saveMapping() {
    setBusy(true); setError('')
    try {
      const byId = Object.fromEntries((bankAccounts || []).map(a => [a.id, a]))
      const entries = Object.entries(selections)
        .filter(([, v]) => v)
        .map(([sfId, v]) => {
          const [bookId, accountId] = v.split('|')
          return {
            simplefin_account_id: sfId,
            bank_name: byId[sfId]?.org || '',
            account_name: byId[sfId]?.name || '',
            target: { store: pool, workspace, book_id: bookId, account_id: accountId },
            enabled: true,
          }
        })
      const s = await financeApi.sfPoolSetMapping(pool, entries)
      setStatus(s)
      setMsg('Mapping saved. Transactions arrive on the next sync.')
    } catch (err) {
      setError(err.message || 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card p-5 space-y-4">
      <div>
        <h2 className="font-semibold">Bank Connections</h2>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400">
          Members with a SimpleFIN account mapped into this pool&apos;s books. Manage the actual
          connection (connect/reveal/sync/disconnect) from that member&apos;s own page under
          Users &amp; Roles.
        </p>
      </div>

      {rows === null ? (
        <div className="space-y-2">
          {[1, 2].map(i => <div key={i} className="h-8 bg-charcoal-100 dark:bg-charcoal-800 rounded animate-pulse" />)}
        </div>
      ) : rows.length === 0 ? (
        <p className="text-sm text-charcoal-500 dark:text-charcoal-400">No members currently have accounts mapped here.</p>
      ) : (
        <ul className="space-y-1.5">
          {rows.map(r => (
            <li key={r.user_id} className="flex items-center gap-2 text-sm">
              <span className="w-2 h-2 rounded-full bg-green-500 shrink-0" />
              <Link to={`/settings/admin/users/${r.user_id}`} className="flex-1 min-w-0 truncate hover:text-orange-500 transition-colors">
                {r.name}
              </Link>
              <span className="text-xs text-charcoal-400 shrink-0">{r.mapped_accounts} account{r.mapped_accounts !== 1 ? 's' : ''}</span>
            </li>
          ))}
        </ul>
      )}

      <div className="border-t border-charcoal-100 dark:border-charcoal-800 pt-4 space-y-3">
        <div>
          <p className="text-sm font-medium">Connect a {accountLabel} account</p>
          <p className="text-xs text-charcoal-500 dark:text-charcoal-400">
            A direct bank connection owned by this pool itself — not tied to any one member&apos;s own
            SimpleFIN connection. Feeds this pool&apos;s books only.
          </p>
        </div>

        {status === null ? (
          <div className="h-8 bg-charcoal-100 dark:bg-charcoal-800 rounded animate-pulse" />
        ) : (
          <>
            <div className="flex items-center gap-2 flex-wrap">
              <div className={`w-2 h-2 rounded-full shrink-0 ${status.connected ? (status.last_error ? 'bg-yellow-500' : 'bg-green-500') : 'bg-charcoal-300'}`} />
              {status.connected ? (
                <span className="text-xs text-charcoal-500 dark:text-charcoal-400">
                  {(status.account_map || []).length} mapped{status.last_sync ? ` · synced ${new Date(status.last_sync).toLocaleDateString()}` : ' · never synced'}
                </span>
              ) : (
                <span className="text-xs text-charcoal-400">not connected</span>
              )}
            </div>
            {status.last_error && <p className="text-xs text-red-500">{status.last_error}</p>}

            {showTokenInput ? (
              <div className="flex gap-2">
                <input className="input flex-1" placeholder="Paste SimpleFIN setup token" value={tokenInput} onChange={e => setTokenInput(e.target.value)} autoFocus />
                <button onClick={poolClaim} disabled={busy || !tokenInput.trim()} className="btn-primary shrink-0 text-sm">
                  {busy ? '…' : 'Connect'}
                </button>
                <button onClick={() => { setShowTokenInput(false); setTokenInput('') }} className="btn-ghost shrink-0 text-sm">Cancel</button>
              </div>
            ) : (
              <div className="flex gap-1.5 flex-wrap">
                <button onClick={() => setShowTokenInput(true)} className="btn-ghost text-xs">
                  {status.connected ? 'Replace token' : '＋ Connect'}
                </button>
                {status.connected && (
                  <>
                    <button onClick={poolSync} disabled={busy} className="btn-ghost text-xs">{busy ? 'Syncing…' : 'Sync now'}</button>
                    <button onClick={poolReveal} disabled={busy} className="btn-ghost text-xs">Reveal</button>
                    <button onClick={poolDisconnect} disabled={busy} className="btn-ghost text-xs text-red-500">Disconnect</button>
                  </>
                )}
              </div>
            )}

            {revealed && (
              <div className="text-xs bg-charcoal-100 dark:bg-charcoal-800 rounded p-2 break-all">
                <p className="text-charcoal-500 dark:text-charcoal-400 mb-1">Access URL (treat like a password — read-only bank data):</p>
                <p className="font-mono">{revealed}</p>
                <button onClick={() => setRevealed(null)} className="text-orange-500 mt-1">Hide</button>
              </div>
            )}

            {status.connected && (
              bankAccounts === null ? (
                <div className="h-16 bg-charcoal-100 dark:bg-charcoal-800 rounded-lg animate-pulse" />
              ) : bankAccounts.length === 0 ? (
                <p className="text-xs text-charcoal-500 dark:text-charcoal-400">No bank accounts found on the connection yet.</p>
              ) : (
                <div className="space-y-2 pt-1">
                  <p className="text-xs text-charcoal-500 dark:text-charcoal-400">
                    Point each bank account at one of this pool&apos;s book accounts. Unmapped accounts are ignored.
                  </p>
                  {bankAccounts.map(a => (
                    <div key={a.id} className="flex items-center gap-2">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm truncate">{a.org ? `${a.org} — ` : ''}{a.name}</p>
                        <p className="text-xs text-charcoal-500 dark:text-charcoal-400">Bank balance {fmtMoney(a.balance_cents, a.currency)}</p>
                      </div>
                      <select
                        className="input w-48 shrink-0 text-sm"
                        value={selections[a.id] || ''}
                        onChange={e => setSelections({ ...selections, [a.id]: e.target.value })}
                      >
                        <option value="">— not synced —</option>
                        {targetOptions().map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                      </select>
                    </div>
                  ))}
                  {targetOptions().length === 0 && (
                    <p className="text-xs text-red-500">This pool has no books with an account yet — create one on the Finance page first.</p>
                  )}
                  <button onClick={saveMapping} disabled={busy} className="btn-primary text-xs px-3 py-1.5">
                    {busy ? 'Saving…' : 'Save mapping'}
                  </button>
                </div>
              )
            )}
          </>
        )}

        {msg && <p className="text-xs text-green-600 dark:text-green-400">{msg}</p>}
        {error && <p className="text-xs text-red-500">{error}</p>}
      </div>
    </div>
  )
}
