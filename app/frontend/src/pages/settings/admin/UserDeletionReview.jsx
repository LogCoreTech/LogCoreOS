import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { admin as adminApi } from '../../../lib/api'
import SettingsPageHeader from '../../../components/settings/SettingsPageHeader'

const MODULE_LABEL = { assets: '🗂️ Assets', finance: '💵 Finance', contacts: '👥 Contacts', notes: '📝 Notes' }
const MODULE_ORDER = ['assets', 'finance', 'contacts', 'notes']

function itemKey(item) {
  return `${item.module}:${item.workspace}:${item.item_id}`
}

function poolLabel(workspace) {
  return workspace === 'business' ? 'team' : 'household'
}

function DecisionSelect({ value, onChange, candidates, workspace }) {
  return (
    <select
      value={value.action ? (value.action === 'transfer_user' ? `user:${value.target_user_id || ''}` : value.action) : ''}
      onChange={e => {
        const raw = e.target.value
        if (raw.startsWith('user:')) onChange({ action: 'transfer_user', target_user_id: raw.slice(5) })
        else if (raw) onChange({ action: raw, target_user_id: null })
        else onChange({ action: null, target_user_id: null })
      }}
      className="input text-xs py-1"
    >
      <option value="">Choose…</option>
      <option value="delete">Delete permanently</option>
      <option value="transfer_pool">Transfer to {poolLabel(workspace)} pool</option>
      {candidates.map(u => (
        <option key={u.id} value={`user:${u.id}`}>Transfer to {u.name}</option>
      ))}
    </select>
  )
}

export default function UserDeletionReview() {
  const { userId } = useParams()
  const navigate = useNavigate()

  const [targetName, setTargetName] = useState('')
  const [preview, setPreview] = useState(null)
  const [decisions, setDecisions] = useState({})
  const [overridden, setOverridden] = useState({})
  const [showBlast, setShowBlast] = useState(false)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    Promise.all([adminApi.listUsers(), adminApi.deletionPreview(userId)])
      .then(([listRes, prev]) => {
        const list = listRes.users || listRes
        const found = list.find(u => u.id === userId)
        setTargetName(found ? found.name : '')
        setPreview(prev)
      })
      .catch(err => setError(err.message || 'Failed to load'))
      .finally(() => setLoading(false))
  }, [userId])

  const grouped = useMemo(() => {
    if (!preview) return {}
    const out = {}
    for (const item of preview.eligible_items) {
      out[item.module] = out[item.module] || []
      out[item.module].push(item)
    }
    return out
  }, [preview])

  function candidatesFor(item) {
    return (preview?.candidate_users || []).filter(u => (u.workspaces || ['personal']).includes(item.workspace))
  }

  function applyModuleDefault(module, decision) {
    setDecisions(prev => {
      const next = { ...prev }
      for (const item of grouped[module] || []) {
        const key = itemKey(item)
        if (overridden[key]) continue
        next[key] = decision
      }
      return next
    })
  }

  function setItemDecision(item, decision) {
    const key = itemKey(item)
    setOverridden(prev => ({ ...prev, [key]: true }))
    setDecisions(prev => ({ ...prev, [key]: decision }))
  }

  const allResolved = preview
    ? preview.eligible_items.every(item => {
        const d = decisions[itemKey(item)]
        if (!d || !d.action) return false
        if (d.action === 'transfer_user') {
          if (!d.target_user_id) return false
          // A bulk default can pick a user who isn't valid for every item's
          // workspace — guard against silently submitting that.
          if (!candidatesFor(item).some(u => u.id === d.target_user_id)) return false
        }
        return true
      })
    : false

  async function handleConfirm() {
    if (!preview || !allResolved) return
    setSubmitting(true)
    setError(null)
    try {
      const payload = preview.eligible_items.map(item => {
        const d = decisions[itemKey(item)]
        return {
          module: item.module,
          workspace: item.workspace,
          item_id: item.item_id,
          action: d.action,
          target_user_id: d.action === 'transfer_user' ? d.target_user_id : null,
        }
      })
      await adminApi.deletionExecute(userId, payload)
      navigate('/settings/admin/users')
    } catch (err) {
      setError(err.message || 'Failed to delete user')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="max-w-lg mx-auto space-y-6">
        <SettingsPageHeader title="Delete User" backTo={`/settings/admin/users/${userId}`} backLabel="User" />
        <p className="text-sm text-charcoal-400">Loading…</p>
      </div>
    )
  }

  if (!preview) {
    return (
      <div className="max-w-lg mx-auto space-y-6">
        <SettingsPageHeader title="Delete User" backTo={`/settings/admin/users/${userId}`} backLabel="User" />
        <p className="text-sm text-red-500">{error || 'Could not load this user.'}</p>
      </div>
    )
  }

  const hasEligible = preview.eligible_items.length > 0

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <SettingsPageHeader title={`Delete ${targetName}`} backTo={`/settings/admin/users/${userId}`} backLabel="User" />

      {error && <p className="text-sm text-red-500">{error}</p>}

      {!hasEligible && (
        <div className="card p-5">
          <p className="text-sm text-charcoal-500 dark:text-charcoal-400">
            {targetName} doesn&apos;t own anything currently shared with someone else. Deleting will
            permanently remove their account and Brain data.
          </p>
        </div>
      )}

      {hasEligible && (
        <p className="text-sm text-charcoal-500 dark:text-charcoal-400">
          {targetName} owns the following items that are shared with someone else. Choose what
          happens to each one before the account can be deleted.
        </p>
      )}

      {MODULE_ORDER.filter(m => (grouped[m] || []).length > 0).map(module => (
        <div key={module} className="card p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold text-sm">{MODULE_LABEL[module]}</h2>
            <select
              value=""
              onChange={e => {
                const raw = e.target.value
                if (!raw) return
                if (raw.startsWith('user:')) applyModuleDefault(module, { action: 'transfer_user', target_user_id: raw.slice(5) })
                else applyModuleDefault(module, { action: raw, target_user_id: null })
              }}
              className="input text-xs py-1 max-w-[55%]"
            >
              <option value="">Set all to…</option>
              <option value="delete">Delete permanently</option>
              <option value="transfer_pool">Transfer all to pool</option>
              {(preview.candidate_users || []).map(u => (
                <option key={u.id} value={`user:${u.id}`}>Transfer all to {u.name}</option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            {grouped[module].map(item => {
              const key = itemKey(item)
              const d = decisions[key] || { action: null, target_user_id: null }
              return (
                <div key={key} className="flex items-center gap-2 flex-wrap py-1.5 border-t border-charcoal-100 dark:border-charcoal-800 first:border-t-0 first:pt-0">
                  <div className="min-w-0 flex-1">
                    <div className="text-sm truncate">{item.label}</div>
                    <div className="text-xs text-charcoal-400 capitalize">{item.workspace}</div>
                  </div>
                  <DecisionSelect
                    value={d}
                    onChange={next => setItemDecision(item, next)}
                    candidates={candidatesFor(item)}
                    workspace={item.workspace}
                  />
                </div>
              )
            })}
          </div>
        </div>
      ))}

      {preview.blast_radius.length > 0 && (
        <div className="card p-5">
          <button onClick={() => setShowBlast(s => !s)} className="text-sm font-semibold w-full text-left flex items-center justify-between">
            <span>Will also lose access to elsewhere ({preview.blast_radius.length})</span>
            <span className="text-charcoal-400">{showBlast ? '−' : '+'}</span>
          </button>
          {showBlast && (
            <div className="mt-3 space-y-1.5">
              {preview.blast_radius.map((b, i) => (
                <div key={i} className="text-xs text-charcoal-500 dark:text-charcoal-400 flex items-center justify-between gap-2">
                  <span className="truncate">{MODULE_LABEL[b.module]} · {b.label} <span className="text-charcoal-400">({b.owner})</span></span>
                  <span className="shrink-0 capitalize">{b.access}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="card p-5">
        <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-3">
          Permanently deletes {targetName}&apos;s account and Brain folder. This cannot be undone.
        </p>
        <button
          onClick={handleConfirm}
          disabled={submitting || (hasEligible && !allResolved)}
          className="text-sm text-red-500 hover:text-red-600 font-medium disabled:opacity-30 disabled:cursor-not-allowed"
        >
          {submitting ? 'Deleting…' : 'Confirm & Delete User'}
        </button>
        {hasEligible && !allResolved && (
          <p className="text-xs text-charcoal-400 mt-2">Choose a destination for every item above first.</p>
        )}
      </div>

      <div className="h-20 md:hidden" aria-hidden="true" />
    </div>
  )
}
