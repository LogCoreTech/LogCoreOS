import { useState } from 'react'
import { Link } from 'react-router-dom'
import { fmtMoney } from '../finance/money'
import { ALL_MODULES, catColor } from '../../lib/constants'
import { deepLinkUrl } from '../../lib/deepLinks'
import { contacts as contactsApi } from '../../lib/api'
import { assets as assetsApi } from '../../module_packages/assets/frontend/api'
import { tasks as tasksApi } from '../../module_packages/tasks/frontend/api'
import { ACTION_MODULE_BY_KIND, buttonColorClasses } from './actionKinds'

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
