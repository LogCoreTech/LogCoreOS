import { useEffect, useState } from 'react'
import { admin as adminApi } from '../../../lib/api'
import SettingsPageHeader from '../../../components/settings/SettingsPageHeader'

const ACTION_LABELS = {
  'user.delete': 'Deleted user',
  'user.role_change': 'Changed role',
  'user.modules_change': 'Changed module access',
  'module.install': 'Installed module',
  'module.uninstall': 'Uninstalled module',
  'user.2fa_enrolled': 'Enabled two-factor authentication',
  'user.2fa_disabled': 'Disabled two-factor authentication',
  'user.2fa_admin_reset': "Reset a user's two-factor authentication",
}

function describe(entry) {
  const label = ACTION_LABELS[entry.action] || entry.action
  const d = entry.details || {}
  if (entry.action === 'user.role_change') return `${label} — ${d.from} → ${d.to}`
  if (entry.action === 'user.modules_change') return `${label} (${(d.to || []).length} disabled)`
  return label
}

export default function AuditLog() {
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    adminApi.getAuditLog(200)
      .then(d => setEntries(d.entries || []))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <SettingsPageHeader title="Audit Log" backTo="/settings/admin" backLabel="Admin Settings" />

      <p className="text-sm text-charcoal-500 dark:text-charcoal-400">
        The most recent admin actions — user deletions, role changes, module access changes,
        and module installs/uninstalls.
      </p>

      <div className="card divide-y divide-charcoal-100 dark:divide-charcoal-800">
        {loading ? (
          <p className="text-sm text-charcoal-400 p-4">Loading…</p>
        ) : entries.length === 0 ? (
          <p className="text-sm text-charcoal-400 p-4">No admin actions recorded yet.</p>
        ) : (
          entries.map(e => (
            <div key={e.id} className="p-3">
              <div className="flex items-start justify-between gap-3">
                <p className="text-sm font-medium text-charcoal-800 dark:text-charcoal-100">
                  {describe(e)} — <span className="font-normal">{e.target}</span>
                </p>
                <p className="text-xs text-charcoal-400 shrink-0 whitespace-nowrap">
                  {new Date(e.at).toLocaleString()}
                </p>
              </div>
              <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mt-0.5">
                by {e.actor?.name || 'unknown'}
              </p>
            </div>
          ))
        )}
      </div>

      <div className="h-20 md:hidden" aria-hidden="true" />
    </div>
  )
}
