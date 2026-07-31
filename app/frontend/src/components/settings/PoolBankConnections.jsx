import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { finance as financeApi } from '../../lib/api'

// Team and Household each render their own independent instance of this —
// intentionally not a combined/shared summary between the two pools.
export default function PoolBankConnections({ pool, accountLabel }) {
  const [rows, setRows] = useState(null) // null = loading

  useEffect(() => {
    financeApi.sfPoolSummary(pool).then(r => setRows(Array.isArray(r) ? r : [])).catch(() => setRows([]))
  }, [pool])

  return (
    <div className="card p-5 space-y-4">
      <div>
        <h2 className="font-semibold">Bank Connections</h2>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400">
          Members with a SimpleFIN account mapped into this pool's books. Manage the actual
          connection (connect/reveal/sync/disconnect) from that member's own page under
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

      <div className="border-t border-charcoal-100 dark:border-charcoal-800 pt-4 opacity-50">
        <div className="flex items-center gap-2 mb-1">
          <p className="text-sm font-medium">Connect a {accountLabel} account</p>
          <span className="badge">Coming soon</span>
        </div>
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400">
          Direct bank connections for this pool, not tied to any one member's own SimpleFIN
          connection, are planned but not built yet.
        </p>
      </div>
    </div>
  )
}
