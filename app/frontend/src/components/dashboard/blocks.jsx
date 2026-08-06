import { useState } from 'react'
import { Link } from 'react-router-dom'
import { fmtMoney } from '../finance/money'
import { ALL_MODULES, catColor } from '../../lib/constants'
import { deepLinkUrl } from '../../lib/deepLinks'
import { assets as assetsApi, contacts as contactsApi, tasks as tasksApi } from '../../lib/api'

function priorityDot(p) {
  return p === 'High' ? 'bg-red-500' : p === 'Medium' ? 'bg-yellow-500' : 'bg-charcoal-400'
}

function Empty({ text }) {
  return <p className="text-sm text-charcoal-400 dark:text-charcoal-500">{text}</p>
}

function TaskRow({ task }) {
  return (
    <div className="flex items-center gap-2 min-w-0">
      <span className={`badge shrink-0 ${catColor(task.category)}`}>{task.category}</span>
      <span className="text-sm truncate flex-1">{task.title}</span>
      {task.streak_count > 0 && <span className="text-xs text-orange-500 shrink-0">🔥{task.streak_count}</span>}
    </div>
  )
}

export function Top3TasksBlock({ data }) {
  const tasks = data?.tasks || []
  if (!tasks.length) return <Empty text="No pending tasks." />
  return (
    <ol className="space-y-2">
      {tasks.map((t, i) => (
        <li key={t.id} className="flex items-center gap-2">
          <span className="text-orange-500 font-bold text-sm w-4 shrink-0">{i + 1}</span>
          <TaskRow task={t} />
        </li>
      ))}
    </ol>
  )
}

export function DueTodayBlock({ data }) {
  const tasks = data?.tasks || []
  if (!tasks.length) return <Empty text="Nothing due today." />
  return <div className="space-y-2">{tasks.map(t => <TaskRow key={t.id} task={t} />)}</div>
}

export function StreaksBlock({ data }) {
  const tasks = data?.tasks || []
  if (!tasks.length) return <Empty text="No active streaks." />
  return (
    <div className="space-y-2">
      {tasks.map(t => (
        <div key={t.id} className="flex items-center justify-between text-sm">
          <span className="truncate">{t.title}</span>
          <span className="text-orange-500 font-semibold shrink-0 ml-2">{t.streak_count} days</span>
        </div>
      ))}
    </div>
  )
}

export function GoalsProgressBlock({ data }) {
  const goals = data?.goals || []
  if (!goals.length) return <Empty text="No goals yet." />
  return <div className="space-y-2">{goals.map(g => <TaskRow key={g.id} task={g} />)}</div>
}

export function SingleTaskBlock({ data }) {
  const task = data?.task
  if (!task) return <Empty text="Task not found." />
  return <TaskRow task={task} />
}

export function HomeFavouritesBlock({ data }) {
  const entities = data?.entities || []
  if (!entities.length) return <Empty text="No favourited devices." />
  return (
    <div className="grid grid-cols-2 gap-2">
      {entities.map(e => (
        <div key={e.entity_id} className="p-2 rounded-lg border border-charcoal-200 dark:border-charcoal-700 bg-charcoal-50 dark:bg-charcoal-800">
          <p className="text-sm font-medium truncate">{e.attributes?.friendly_name || e.entity_id}</p>
          <p className="text-xs text-charcoal-500 dark:text-charcoal-400">{e.state}</p>
        </div>
      ))}
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

export function UpcomingEventsBlock({ data }) {
  const events = data?.events || []
  if (!events.length) return <Empty text="No upcoming events." />
  return (
    <div className="space-y-2">
      {events.map(e => (
        <div key={e.id} className="flex items-center justify-between text-sm">
          <span className="truncate">{e.title}</span>
          <span className="text-xs text-charcoal-400 shrink-0 ml-2">{e.date}</span>
        </div>
      ))}
    </div>
  )
}

export function SingleEventBlock({ data }) {
  const e = data?.event
  if (!e) return <Empty text="Event not found." />
  return (
    <div>
      <p className="text-sm font-medium">{e.title}</p>
      <p className="text-xs text-charcoal-400">{e.date}</p>
      {e.notes && <p className="text-xs text-charcoal-500 mt-1">{e.notes}</p>}
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

export function LinkedAssetsBlock({ data }) {
  const assets = data?.assets || []
  if (!assets.length) return <Empty text="No linked assets." />
  return (
    <div className="space-y-1.5">
      {assets.map(a => (
        <div key={a.id} className="flex items-center gap-2 text-sm">
          <span className="shrink-0">{a.icon}</span>
          <span className="truncate">{a.name}</span>
        </div>
      ))}
    </div>
  )
}

export function DocumentsBlock({ data }) {
  const files = data?.attachments || []
  if (!files.length) return <Empty text="No attachments." />
  return (
    <div className="space-y-1.5">
      {files.map(f => <p key={f.id} className="text-sm truncate">📎 {f.filename}</p>)}
    </div>
  )
}

export function LinkedTasksBlock({ data }) {
  const tasks = data?.tasks || []
  if (!tasks.length) return <Empty text="No linked tasks." />
  return <div className="space-y-2">{tasks.map(t => <TaskRow key={t.id} task={t} />)}</div>
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

export function NoteEmbedBlock({ data }) {
  if (!data?.preview) return <Empty text="Note is empty." />
  return <p className="text-sm whitespace-pre-wrap line-clamp-6">{data.preview}</p>
}

export function JournalEntryBlock({ data }) {
  if (!data?.preview) return <Empty text="No entry for this date." />
  return (
    <div>
      <p className="text-xs text-charcoal-400 mb-1">{data.date}</p>
      <p className="text-sm whitespace-pre-wrap line-clamp-6">{data.preview}</p>
    </div>
  )
}

export function WorkflowStatusBlock({ data }) {
  const wf = data?.workflow
  if (!wf) return <Empty text="Workflow not found." />
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="truncate">{wf.name}</span>
      <span className={`badge shrink-0 ml-2 ${wf.active ? 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300' : ''}`}>
        {wf.active ? 'active' : 'inactive'}
      </span>
    </div>
  )
}

export function InboxSummaryBlock({ data }) {
  return (
    <div className="text-sm">
      <p><span className="text-orange-500 font-semibold">{data?.new_count ?? 0}</span> new item{(data?.new_count ?? 0) === 1 ? '' : 's'}</p>
      <p className="text-charcoal-400 text-xs">{data?.total ?? 0} total in inbox</p>
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
  const url = deepLinkUrl(data.module, data.record_id)
  const moduleLabel = ALL_MODULES.find(m => m.id === data.module)?.label || data.module
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
        if (data.action === 'unarchive') await contactsApi.unarchive(data.record_id)
        else await contactsApi.archive(data.record_id)
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
