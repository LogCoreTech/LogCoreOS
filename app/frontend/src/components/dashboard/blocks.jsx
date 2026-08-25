import { useState } from 'react'
import { Link } from 'react-router-dom'
import { fmtMoney } from '../finance/money'
import { ALL_MODULES, catColor } from '../../lib/constants'
import { deepLinkUrl } from '../../lib/deepLinks'
import { assets as assetsApi, contacts as contactsApi } from '../../lib/api'
import { tasks as tasksApi } from '../../module_packages/tasks/frontend/api'
import { AttachmentThumb } from '../assetDisplay'
import { ACTION_MODULE_BY_KIND, buttonColorClasses } from './actionKinds'

function priorityDot(p) {
  return p === 'High' ? 'bg-red-500' : p === 'Medium' ? 'bg-yellow-500' : 'bg-charcoal-400'
}

function Empty({ text }) {
  return <p className="text-sm text-charcoal-400 dark:text-charcoal-500">{text}</p>
}

// Runs a curated status preset (blockRegistry.js's ACTION_PRESETS_BY_KIND)
// against one record — the same underlying calls StatusButtonBlock.run()
// already makes, just parameterized by whichever row's id a click came from
// instead of one fixed config'd id.
async function runStatusAction(recordKind, preset, recordId) {
  if (recordKind === 'task') {
    const status = preset === 'mark_done' ? 'done' : preset === 'mark_skipped' ? 'skipped' : 'pending'
    await tasksApi.update(recordId, { status })
  } else if (recordKind === 'asset') {
    if (preset === 'unarchive') await assetsApi.unarchive(recordId)
    else await assetsApi.archive(recordId)
  }
}

function ActionButton({ action, recordKind, recordId, onDone }) {
  const [state, setState] = useState('idle') // idle | busy | error

  if (action.kind === 'nav') {
    const module = ACTION_MODULE_BY_KIND[recordKind]
    if (!module) return null
    return (
      <Link
        to={deepLinkUrl(module, recordId)}
        onClick={e => e.stopPropagation()}
        className={`badge shrink-0 ${buttonColorClasses(action.color)}`}
        title={action.label || 'Open'}
      >
        {action.label || '→ Open'}
      </Link>
    )
  }

  async function run(e) {
    e.preventDefault()
    e.stopPropagation()
    setState('busy')
    try {
      await runStatusAction(recordKind, action.preset, recordId)
      setState('idle')
      onDone?.()
    } catch {
      setState('error')
      setTimeout(() => setState('idle'), 3000)
    }
  }

  return (
    <button
      type="button"
      onClick={run}
      disabled={state === 'busy'}
      className={`badge shrink-0 ${state === 'error' ? 'bg-red-100 dark:bg-red-900/40 text-red-600 dark:text-red-300' : buttonColorClasses(action.color)}`}
      title={action.label || action.preset}
    >
      {state === 'busy' ? '…' : state === 'error' ? '⚠' : (action.label || action.preset)}
    </button>
  )
}

// A block's own user-configured action buttons (block.config.actions), for
// one record — either a specific row (list-shaped blocks call this once per
// row, passing that row's own id) or the block's single subject (detail-
// shaped blocks call this once). See actionKinds.js for why nav/status never
// need to ask "which module" or "which record type" — both are implied by
// recordKind, which the block itself already knows.
export function BlockActionButtons({ actions, recordKind, recordId, onDone }) {
  if (!actions?.length || !recordId || !recordKind) return null
  // `ml-auto` makes this self-right-aligning in any flex ROW parent, whether
  // or not that row also has justify-between/a flex-1 sibling doing the same
  // job (harmless overlap where those already exist — with justify-between
  // and this being the last child, the auto-margin just absorbs the same
  // free space justify-between would have anyway). Was previously up to
  // each call site to remember on its own, and 2 of 9 didn't (CollectionBlock's
  // Kanban view, NoteEmbedBlock) — owner report, 2026-08-18.
  return (
    <div className="flex items-center gap-1 shrink-0 ml-auto" onClick={e => e.stopPropagation()}>
      {actions.map((a, i) => (
        <ActionButton key={i} action={a} recordKind={recordKind} recordId={recordId} onDone={onDone} />
      ))}
    </div>
  )
}

// Shared row renderer — Tasks' own block components (Top3TasksBlock,
// DueTodayBlock, GoalsProgressBlock, SingleTaskBlock, all in
// module_packages/tasks/frontend/ since 2026-08-25) import this back from
// core, same direction/pattern BlockActionButtons above already uses; kept
// here rather than moved into the tasks package because LinkedTasksBlock
// below (Assets' own block) needs it too, discovered only once ESLint
// caught the leftover reference — genuinely cross-cutting, not
// tasks-exclusive, the same reasoning BlockActionButtons itself stays core
// for. `flex-1` here is load-bearing specifically for Top3TasksBlock, where
// this whole row is itself a flex ITEM inside another flex row (the
// numbered `<li>`) — without it, a flex item defaults to sizing to its own
// content (flex: 0 1 auto), so a short title left the entire row —
// buttons included — bunched at the left instead of stretched to the
// block's real width; `ml-auto` on BlockActionButtons can only push to the
// edge of whatever box it's actually in, not rescue an unstretched one
// (owner, 2026-08-18: "regardless if the text reaches all the way there or
// not"). A no-op everywhere else this is used (a direct child of a plain
// `space-y-2` div, not a flex container, where `flex-1`'s flex-context-only
// properties have no effect).
export function TaskRow({ task, actions, onAction }) {
  return (
    <div className="flex items-center gap-2 min-w-0 flex-1">
      <span className={`badge shrink-0 ${catColor(task.category)}`}>{task.category}</span>
      <span className="text-sm truncate flex-1">{task.title}</span>
      {task.streak_count > 0 && <span className="text-xs text-orange-500 shrink-0">🔥{task.streak_count}</span>}
      <BlockActionButtons actions={actions} recordKind="task" recordId={task.id} onDone={onAction} />
    </div>
  )
}

export function PoolTasksBlock({ data }) {
  const tasks = data?.tasks || []
  if (!tasks.length) return <Empty text="No pending pool tasks." />
  return (
    <div className="space-y-2">
      {tasks.map(t => (
        <div key={t.id} className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full shrink-0 ${priorityDot(t.priority)}`} />
          <span className="text-sm truncate flex-1">{t.title}</span>
          {t.assigned_to && <span className="text-xs text-charcoal-400 shrink-0">{t.assigned_to}</span>}
        </div>
      ))}
    </div>
  )
}

export function FinanceActivityBlock({ data }) {
  const txs = data?.transactions || []
  if (!txs.length) return <Empty text="No transactions." />
  return (
    <div className="space-y-1.5">
      {txs.map(tx => (
        <div key={tx.id} className="flex items-center justify-between text-sm">
          <span className="truncate">{tx.payee || tx.category || '(uncategorized)'}</span>
          <span className={`shrink-0 ml-2 font-medium ${tx.amount_cents < 0 ? 'text-charcoal-600 dark:text-charcoal-300' : 'text-green-600 dark:text-green-400'}`}>
            {fmtMoney(tx.amount_cents)}
          </span>
        </div>
      ))}
    </div>
  )
}

export function FinanceBookReportBlock({ data }) {
  const r = data?.report
  if (!r) return <Empty text="No report data." />
  return (
    <div className="space-y-1 text-sm">
      <p className="font-medium">{data.book_name}</p>
      <div className="flex justify-between"><span>Income</span><span className="text-green-600 dark:text-green-400">{fmtMoney(r.income_cents)}</span></div>
      <div className="flex justify-between"><span>Expenses</span><span>{fmtMoney(r.expense_cents)}</span></div>
      <div className="flex justify-between font-semibold border-t border-charcoal-100 dark:border-charcoal-700 pt-1"><span>Net</span><span>{fmtMoney(r.net_cents)}</span></div>
    </div>
  )
}

export function LinkedDealsBlock({ data }) {
  const deals = data?.deals || []
  if (!deals.length) return <Empty text="No deals." />
  return (
    <div className="space-y-1.5">
      {deals.map(d => (
        <div key={d.id} className="flex items-center justify-between text-sm">
          <span className="truncate">{d.title}</span>
          <span className="badge shrink-0 ml-2">{d.stage}</span>
        </div>
      ))}
    </div>
  )
}

export function CustomFieldsBlock({ data }) {
  const fields = data?.fields || {}
  const entries = Object.entries(fields)
  if (!entries.length) return <Empty text="No custom fields set." />
  return (
    <dl className="space-y-1 text-sm">
      {entries.map(([k, v]) => (
        <div key={k} className="flex justify-between gap-2">
          <dt className="text-charcoal-500 dark:text-charcoal-400">{k}</dt>
          <dd className="truncate text-right">{String(v)}</dd>
        </div>
      ))}
    </dl>
  )
}

export function LinkedAssetsBlock({ data, actions, onAction }) {
  const assets = data?.assets || []
  if (!assets.length) return <Empty text="No linked assets." />
  return (
    <div className="space-y-1.5">
      {assets.map(a => (
        <div key={a.id} className="flex items-center gap-2 text-sm">
          <span className="shrink-0">{a.icon}</span>
          <span className="truncate flex-1">{a.name}</span>
          <BlockActionButtons actions={actions} recordKind="asset" recordId={a.id} onDone={onAction} />
        </div>
      ))}
    </div>
  )
}

export function DocumentsBlock({ data }) {
  const files = data?.attachments || []
  if (!files.length) return <Empty text="No attachments." />
  return (
    <div className="grid grid-cols-3 gap-2">
      {files.map(f => (
        <AttachmentThumb key={f.id} assetId={data.asset_id} file={f} canEdit={false} onDelete={() => {}} />
      ))}
    </div>
  )
}

export function LinkedTasksBlock({ data, actions, onAction }) {
  const tasks = data?.tasks || []
  if (!tasks.length) return <Empty text="No linked tasks." />
  return <div className="space-y-2">{tasks.map(t => <TaskRow key={t.id} task={t} actions={actions} onAction={onAction} />)}</div>
}

export function LinkedContactBlock({ data }) {
  const ids = data?.contact_ids || []
  if (!ids.length) return <Empty text="No linked contact." />
  return (
    <div className="space-y-1">
      {ids.map(id => (
        <Link key={id} to={`/contacts?contact=${id}`} className="text-sm text-orange-500 hover:underline block">
          View contact →
        </Link>
      ))}
    </div>
  )
}

// New block type (2026-08-15) — the dashboard had no general "list of
// contacts" block before this; linked_deals/linked_assets are scoped to one
// contact/asset's own related records, not a standalone contacts list.
export function ContactsListBlock({ data, actions, onAction }) {
  const contacts = data?.contacts || []
  if (!contacts.length) return <Empty text="No contacts." />
  return (
    <div className="space-y-1.5">
      {contacts.map(c => (
        <div key={c.id} className="flex items-center gap-2 text-sm">
          <span className="shrink-0">{c.type === 'company' ? '🏢' : '🧑'}</span>
          <span className="truncate flex-1">{c.name}</span>
          <BlockActionButtons actions={actions} recordKind="contact" recordId={c.id} onDone={onAction} />
        </div>
      ))}
    </div>
  )
}

export function MyAssetsSummaryBlock({ data }) {
  const counts = data?.counts || {}
  const entries = Object.entries(counts)
  if (!entries.length) return <Empty text="No assets yet." />
  return (
    <div className="space-y-1.5">
      {entries.map(([key, count]) => (
        <div key={key} className="flex items-center justify-between text-sm">
          <span className="truncate">{key || '(untyped)'}</span>
          <span className="text-charcoal-400 shrink-0">{count}</span>
        </div>
      ))}
    </div>
  )
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

export function CollectionBlock({ data, actions, onAction }) {
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

export function NoteEmbedBlock({ data, actions, onAction }) {
  if (!data?.preview) return <Empty text="Note is empty." />
  return (
    <div className="flex flex-col gap-2 h-full">
      <p className="text-sm whitespace-pre-wrap line-clamp-6 flex-1">{data.preview}</p>
      {/* `ml-auto` on BlockActionButtons only affects the cross axis in a
          flex-col parent — needs its own row to actually sit right. */}
      <div className="flex justify-end">
        <BlockActionButtons actions={actions} recordKind="note" recordId={data.path} onDone={onAction} />
      </div>
    </div>
  )
}

export function AiUsageMeBlock({ data }) {
  const u = data?.usage
  if (!u) return <Empty text="No usage data." />
  return (
    <div className="text-sm space-y-1">
      <p>{u.used_messages} message{u.used_messages === 1 ? '' : 's'} · {u.used_tokens?.toLocaleString?.() ?? u.used_tokens} tokens</p>
      <p className="text-charcoal-400 text-xs">{u.period} period{u.pct != null ? ` — ${Math.round(u.pct * 100)}% of limit` : ''}</p>
    </div>
  )
}

export function AiUsageOverviewBlock({ data }) {
  const rows = data?.users || []
  if (!rows.length) return <Empty text="No usage data." />
  return (
    <div className="space-y-1.5">
      {rows.slice(0, 6).map(r => (
        <div key={r.user_id || r.name} className="flex items-center justify-between text-sm">
          <span className="truncate">{r.name}</span>
          <span className="text-charcoal-400 shrink-0 ml-2">{r.used_tokens?.toLocaleString?.() ?? r.used_tokens} tok</span>
        </div>
      ))}
    </div>
  )
}

export function RecentAiActionsBlock({ data }) {
  const runs = data?.runs || []
  if (!runs.length) return <Empty text="No recent AI activity." />
  return (
    <div className="space-y-1.5">
      {runs.slice(0, 6).map(r => (
        <p key={r.id} className="text-sm truncate">{r.goal || '(no prompt)'}</p>
      ))}
    </div>
  )
}

export function TextBlock({ data }) {
  return <p className="text-sm whitespace-pre-wrap">{data?.text || ''}</p>
}

export function LinkButtonBlock({ data }) {
  if (!data?.url) return <Empty text="No link configured." />
  return (
    <a href={data.url} target="_blank" rel="noopener noreferrer" className="btn-primary inline-block text-sm">
      {data.label || 'Open link'}
    </a>
  )
}

export function HeadingDividerBlock({ data }) {
  if (data?.style === 'divider') return <hr className="border-charcoal-200 dark:border-charcoal-700" />
  return <h3 className="font-semibold text-sm uppercase tracking-wide text-charcoal-500 dark:text-charcoal-400">{data?.text}</h3>
}

export function NavButtonBlock({ data }) {
  if (!data?.module) return <Empty text="No destination configured." />
  const url = deepLinkUrl(data.module, data.record_id, data.section)
  const moduleLabel = data.module === 'settings'
    ? 'Settings'
    : ALL_MODULES.find(m => m.id === data.module)?.label || data.module
  const label = data.label || data.title || `Go to ${moduleLabel}`
  return (
    <Link to={url} className="btn-pill" title={label}>
      {label}
    </Link>
  )
}

// The first write-capable block in an otherwise entirely passive dashboard —
// the click goes straight to each target module's own existing endpoint
// (same gate a normal page use would hit), never through the dashboard at
// all. Needs real feedback since a legitimate 403 is possible (a shared
// viewer can see a button labeled using the owner's visibility via
// share_underlying_data, but the click always resolves as their own
// identity) — a silent no-op would look broken.
export function StatusButtonBlock({ data, onAction }) {
  const [state, setState] = useState('idle') // idle | busy | done | error
  const [errorMsg, setErrorMsg] = useState('')

  if (!data?.record_type) return <Empty text="No action configured." />

  function defaultLabel() {
    if (data.record_type === 'task') {
      const map = { pending: 'Mark Pending', done: 'Mark Done', skipped: 'Mark Skipped' }
      return map[data.target_status] || 'Update Task'
    }
    if (data.record_type === 'contact') return `Set ${data.field_key || 'field'}`
    if (data.action === 'archive') return 'Archive'
    if (data.action === 'unarchive') return 'Unarchive'
    if (data.action === 'set_field') return `Set ${data.field_key || 'field'}`
    return 'Run Action'
  }

  async function run() {
    setState('busy')
    setErrorMsg('')
    try {
      if (data.record_type === 'task') {
        await tasksApi.update(data.record_id, { status: data.target_status })
      } else if (data.record_type === 'contact') {
        // Contacts have no "fields" wrapper like Assets do — PATCH /contacts/{id}
        // is a flat body, so this must be {gender: 'male'}, never
        // {fields: {gender: 'male'}}, or the API silently accepts it and
        // changes nothing (pydantic ignores unknown keys).
        if (data.field_key) await contactsApi.update(data.record_id, { [data.field_key]: data.field_value })
      } else if (data.record_type === 'asset') {
        if (data.action === 'unarchive') await assetsApi.unarchive(data.record_id)
        else if (data.action === 'set_field' && data.field_key) {
          await assetsApi.update(data.record_id, { fields: { [data.field_key]: data.field_value } })
        } else {
          await assetsApi.archive(data.record_id)
        }
      }
      setState('done')
      onAction?.()
      setTimeout(() => setState('idle'), 2000)
    } catch (e) {
      setState('error')
      setErrorMsg(e.message || 'Action failed — you may not have permission.')
      setTimeout(() => setState('idle'), 3000)
    }
  }

  const label = data.label || defaultLabel()
  const text = state === 'busy' ? 'Working…' : state === 'done' ? '✓ Done' : state === 'error' ? '⚠ Failed' : label
  const tooltip = state === 'error' ? errorMsg : data.title ? `${label} — ${data.title}` : label

  return (
    <button
      className={`btn-pill ${state === 'error' ? 'btn-pill-error' : ''}`}
      onClick={run}
      disabled={state === 'busy'}
      title={tooltip}
    >
      {text}
    </button>
  )
}
