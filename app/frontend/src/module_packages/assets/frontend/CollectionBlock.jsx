import { useState } from 'react'
import { Link } from 'react-router-dom'
import { BlockActionButtons } from '../../../components/dashboard/blocks'
import { assets as assetsApi } from './api'

function Empty({ text }) {
  return <p className="text-sm text-charcoal-400 dark:text-charcoal-500">{text}</p>
}

function fieldSummary(row, displayFields) {
  return displayFields
    .map(f => row.fields?.[f.key])
    .filter(v => v !== undefined && v !== null && v !== '')
    .join(' · ')
}

// Inline status control shared by the List and Kanban views below — the same
// select doubles as "set the status" (list) and "move to another column"
// (kanban), since changing its value is the whole action either way. Calls
// the asset module's own PATCH directly, exactly like status_button's
// set_field action, never a dashboard-specific write path — so a viewer who
// can see this row but not edit that asset gets a real error here too.
function CollectionStatusControl({ row, statusField, statusOptions, onAction }) {
  const [state, setState] = useState('idle') // idle | busy | error
  const [errorMsg, setErrorMsg] = useState('')

  async function change(value) {
    setState('busy')
    setErrorMsg('')
    try {
      await assetsApi.update(row.id, { fields: { [statusField]: value } })
      setState('idle')
      onAction?.()
    } catch (e) {
      setState('error')
      setErrorMsg(e.message || 'Could not update — you may not have permission.')
      setTimeout(() => setState('idle'), 3000)
    }
  }

  return (
    <div className="shrink-0">
      <select
        className={`badge !py-1 cursor-pointer border-0 ${state === 'error' ? 'bg-red-100 dark:bg-red-900/40 text-red-600 dark:text-red-300' : 'bg-charcoal-100 dark:bg-charcoal-700'}`}
        value={row.status_value || ''}
        disabled={state === 'busy'}
        onClick={e => e.stopPropagation()}
        onChange={e => change(e.target.value)}
        title={state === 'error' ? errorMsg : undefined}
      >
        <option value="">—</option>
        {(statusOptions || []).map(o => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  )
}

export default function CollectionBlock({ data, actions, onAction }) {
  const rows = data?.rows || []
  const view = data?.view || 'list'
  const displayFields = data?.display_fields || []
  const statusField = data?.status_field
  const statusOptions = data?.status_options

  if (view === 'count') {
    return (
      <div className="h-full flex flex-col items-center justify-center">
        <span className="text-4xl font-bold font-mono">{data?.count ?? 0}</span>
        {data?.template_label && (
          <span className="text-xs text-charcoal-400 uppercase tracking-wide mt-1">{data.template_label}</span>
        )}
      </div>
    )
  }

  if (!rows.length) return <Empty text="No matching records." />

  if (view === 'kanban') {
    if (!statusField) return <Empty text="Pick a status field above to use the Kanban layout." />
    const columns = [...(statusOptions || []), null] // null = "Other" bucket for an unset/off-list value
    return (
      <div className="flex gap-3 h-full overflow-x-auto">
        {columns.map(col => {
          const colRows = rows.filter(r => (r.status_value || null) === col)
          if (col === null && colRows.length === 0) return null
          return (
            <div key={col ?? '__other'} className="flex-1 min-w-[160px]">
              <p className="text-xs font-semibold uppercase tracking-wide text-charcoal-400 mb-1.5">
                {col ?? 'Other'} <span className="text-charcoal-300 dark:text-charcoal-600">({colRows.length})</span>
              </p>
              <div className="space-y-1.5">
                {colRows.map(row => (
                  <div key={row.id} className="card p-2">
                    <Link to={`/assets?asset=${row.id}`} className="text-sm font-medium truncate block hover:text-orange-500">
                      {row.name}
                    </Link>
                    {displayFields.length > 0 && (
                      <p className="text-xs text-charcoal-400 truncate">{fieldSummary(row, displayFields)}</p>
                    )}
                    <div className="mt-1.5 flex items-center gap-1.5 flex-wrap">
                      <CollectionStatusControl row={row} statusField={statusField} statusOptions={statusOptions} onAction={onAction} />
                      <BlockActionButtons actions={actions} recordKind="asset" recordId={row.id} onDone={onAction} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )
        })}
      </div>
    )
  }

  return (
    <div>
      {rows.map(row => (
        <div key={row.id} className="flex items-center justify-between gap-2 py-1.5 border-b border-charcoal-100 dark:border-charcoal-700 last:border-0">
          <Link to={`/assets?asset=${row.id}`} className="min-w-0 flex-1 hover:text-orange-500">
            <p className="text-sm font-medium truncate">{row.name}</p>
            {displayFields.length > 0 && (
              <p className="text-xs text-charcoal-400 truncate">{fieldSummary(row, displayFields)}</p>
            )}
          </Link>
          {statusField && (
            <CollectionStatusControl row={row} statusField={statusField} statusOptions={statusOptions} onAction={onAction} />
          )}
          <BlockActionButtons actions={actions} recordKind="asset" recordId={row.id} onDone={onAction} />
        </div>
      ))}
    </div>
  )
}
