import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import HelpButton from '../../../components/HelpButton'
import { tasks as tasksApi } from './api'
import { priorities as prioritiesApi } from '../../../lib/api'
import { assets as assetsApi } from '../../assets/frontend/api'
import { shared as sharedApi } from '../../household/frontend/api'
import { team as teamApi } from '../../team/frontend/api'
import { useAuth } from '../../../lib/auth'
import { useWorkspace } from '../../../lib/workspace'
import TaskModal from '../../../components/TaskModal'
import { catColor, scoreTask } from '../../../lib/constants'

const SORT_MODES = [
  { id: 'priority', label: 'Priority' },
  { id: 'date', label: 'Date/Time' },
  { id: 'alpha', label: 'A–Z' },
]

// "14:30" -> "2:30 PM" — same toLocaleString shape Chat.jsx's fmtFilename already
// uses for timestamps, for visual consistency across the app.
function fmtDueTime(due_time) {
  const [h, m] = due_time.split(':')
  return new Date(2000, 0, 1, +h, +m).toLocaleString(undefined, { hour: 'numeric', minute: '2-digit' })
}

export default function Tasks() {
  const { user } = useAuth()
  const { workspace } = useWorkspace()
  const [taskList, setTaskList] = useState([])
  const [assignedPoolTasks, setAssignedPoolTasks] = useState([])
  const [priorityOrder, setPriorityOrder] = useState([])
  const [filter, setFilter] = useState('pending')
  const [tagFilter, setTagFilter] = useState(null)
  const [sortMode, setSortMode] = useState(() => localStorage.getItem('lc_tasks_sort') || 'priority')
  const [editTask, setEditTask] = useState(null)
  const [showModal, setShowModal] = useState(false)
  const [showReorder, setShowReorder] = useState(false)
  const [tempOrder, setTempOrder] = useState([])
  const [dragIdx, setDragIdx] = useState(null)
  const [loading, setLoading] = useState(true)
  const [assetList, setAssetList] = useState([])
  const assetsEnabled = !user?.disabledModules?.includes('assets')
  const [searchParams, setSearchParams] = useSearchParams()

  // Deep link (?task=<id>) — dashboard nav-button clicks land here.
  useEffect(() => {
    const target = searchParams.get('task')
    if (!target || loading) return
    const found = taskList.find(t => t.id === target)
    if (found) { setEditTask(found); setShowModal(true) }
    searchParams.delete('task')
    setSearchParams(searchParams, { replace: true })
  }, [loading, taskList, searchParams, setSearchParams])

  async function load() {
    setLoading(true)
    const [all, prio, pool, assetsRes] = await Promise.allSettled([
      tasksApi.list(),
      prioritiesApi.get(),
      tasksApi.assigned(),
      assetsEnabled ? assetsApi.list() : Promise.resolve([]),
    ])
    if (all.status === 'fulfilled') setTaskList(all.value)
    if (prio.status === 'fulfilled') {
      setPriorityOrder(prio.value.order || [])
      setTempOrder(prio.value.order || [])
    }
    if (pool.status === 'fulfilled') {
      setAssignedPoolTasks(pool.value)
    }
    if (assetsRes.status === 'fulfilled') setAssetList(assetsRes.value || [])
    setLoading(false)
  }

  // Reload when the user or workspace changes only; `load` is redefined every
  // render and isn't memoized, so including it would refetch on every render.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load() }, [user?.name, workspace])

  async function toggleDone(task) {
    const newStatus = task.status === 'done' ? 'pending' : 'done'
    if (task._source === 'household') {
      await sharedApi.update(task.id, { status: newStatus })
    } else if (task._source === 'team') {
      await teamApi.update(task.id, { status: newStatus })
    } else {
      await tasksApi.update(task.id, { status: newStatus })
    }
    load()
  }

  async function saveOverride() {
    try {
      await prioritiesApi.saveOverride(tempOrder)
    } catch { /* non-fatal — order is still applied locally */ }
    setPriorityOrder(tempOrder)
    setShowReorder(false)
  }

  // Drag for reorder modal (desktop)
  function onDragStart(i) { setDragIdx(i) }
  function onDragOver(e, i) {
    e.preventDefault()
    if (dragIdx === null || dragIdx === i) return
    const next = [...tempOrder]
    const [m] = next.splice(dragIdx, 1)
    next.splice(i, 0, m)
    setTempOrder(next)
    setDragIdx(i)
  }
  function onDragEnd() { setDragIdx(null) }

  function moveItem(from, to) {
    const next = [...tempOrder]
    const [m] = next.splice(from, 1)
    next.splice(to, 0, m)
    setTempOrder(next)
  }

  function changeSortMode(mode) {
    setSortMode(mode)
    localStorage.setItem('lc_tasks_sort', mode)
  }

  const _today = new Date()
  const _todayStr = `${_today.getFullYear()}-${String(_today.getMonth() + 1).padStart(2, '0')}-${String(_today.getDate()).padStart(2, '0')}`

  // Merge personal tasks + assigned pool tasks (tagged with _source from backend).
  const allTasks = [
    ...taskList,
    ...assignedPoolTasks,
  ]

  const filtered = allTasks
    .filter(t =>
      filter === 'all'     ? true :
      filter === 'pending' ? t.status === 'pending' :
      filter === 'done'    ? t.status === 'done' :
      filter === 'overdue' ? (t.status === 'pending' && t.due_date && t.due_date < _todayStr) : true
    )
    .filter(t => !tagFilter || (t.tags || []).includes(tagFilter))

  // One flat list, no category grouping — sort mode picks the ordering.
  // 'priority' mirrors the backend's own score_task() formula (ported to JS
  // in lib/constants.js) so a high-priority Family task outranks a
  // medium-priority Religion task regardless of category, exactly like
  // GET /tasks/scored already does for pending/own tasks — applied here to
  // every task shown (including assigned pool tasks and any filter tab).
  const sorted = [...filtered].sort((a, b) => {
    if (sortMode === 'date') {
      const ad = a.due_date ? `${a.due_date} ${a.due_time || '00:00'}` : null
      const bd = b.due_date ? `${b.due_date} ${b.due_time || '00:00'}` : null
      if (ad && bd) return ad < bd ? -1 : ad > bd ? 1 : 0
      if (ad) return -1
      if (bd) return 1
      return 0
    }
    if (sortMode === 'alpha') {
      return (a.title || '').localeCompare(b.title || '')
    }
    return scoreTask(b, priorityOrder, _todayStr) - scoreTask(a, priorityOrder, _todayStr)
  })

  return (
    <div className="w-full max-w-2xl mx-auto space-y-5 overflow-x-hidden">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <span className="flex items-center gap-2"><h1 className="text-2xl font-bold">Tasks</h1><HelpButton section="tasks" /></span>
        <div className="flex gap-2 shrink-0">
          <button
            onClick={() => setShowReorder(true)}
            className="btn-ghost text-sm whitespace-nowrap"
          >
            ⇅ <span className="hidden sm:inline">Reorder </span>Today
          </button>
          <button onClick={() => { setEditTask(null); setShowModal(true) }} className="btn-primary whitespace-nowrap">
            + Add
          </button>
        </div>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-1 bg-charcoal-100 dark:bg-charcoal-800 rounded-lg p-1">
        {['pending', 'all', 'done', 'overdue'].map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`flex-1 py-1 rounded-md text-xs font-medium capitalize transition-colors ${
              filter === f
                ? 'bg-white dark:bg-charcoal-600 text-charcoal-900 dark:text-gray-100 shadow-sm'
                : 'text-charcoal-500 dark:text-charcoal-400'
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {tagFilter && (
        <button
          onClick={() => setTagFilter(null)}
          className="inline-flex items-center gap-1.5 bg-orange-100 dark:bg-orange-900/40 text-orange-700 dark:text-orange-300 text-xs px-2.5 py-1 rounded-full"
        >
          Tag: {tagFilter} <span className="font-bold">✕</span>
        </button>
      )}

      {/* Sort mode */}
      <div className="flex items-center gap-2 text-xs text-charcoal-500 dark:text-charcoal-400">
        <span className="shrink-0">Sort by</span>
        <div className="flex gap-1 bg-charcoal-100 dark:bg-charcoal-800 rounded-lg p-1 flex-1">
          {SORT_MODES.map(m => (
            <button
              key={m.id}
              onClick={() => changeSortMode(m.id)}
              className={`flex-1 py-1 rounded-md text-xs font-medium transition-colors ${
                sortMode === m.id
                  ? 'bg-white dark:bg-charcoal-600 text-charcoal-900 dark:text-gray-100 shadow-sm'
                  : 'text-charcoal-500 dark:text-charcoal-400'
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1,2,3].map(i => <div key={i} className="h-16 card animate-pulse" />)}
        </div>
      ) : sorted.length === 0 ? (
        <div className="card p-8 text-center text-charcoal-500 dark:text-charcoal-400">
          <p className="text-4xl mb-2">✓</p>
          <p>No tasks here.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {sorted.map(task => (
            <TaskCard
              key={task.id}
              task={task}
              catColor={catColor(task.category)}
              today={_todayStr}
              onDone={() => toggleDone(task)}
              onEdit={() => { setEditTask(task); setShowModal(true) }}
              onTagClick={t => setTagFilter(t)}
            />
          ))}
        </div>
      )}

      {/* Reorder Today modal */}
      {showReorder && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-end md:items-center justify-center p-4">
          <div className="card p-5 w-full max-w-sm">
            <h3 className="font-semibold mb-1">Reorder Today&apos;s Priorities</h3>
            <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-4">
              Use the arrows or drag to change order for today only. Resets tomorrow.
            </p>
            <ul className="space-y-2 mb-4">
              {tempOrder.map((cat, i) => (
                <li
                  key={cat}
                  draggable
                  onDragStart={() => onDragStart(i)}
                  onDragOver={e => onDragOver(e, i)}
                  onDragEnd={onDragEnd}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg border transition-colors ${
                    dragIdx === i
                      ? 'border-orange-500 bg-orange-500/10'
                      : 'border-charcoal-200 dark:border-charcoal-700 bg-white dark:bg-charcoal-800'
                  }`}
                >
                  <span className="text-charcoal-400 text-xs w-4 shrink-0">{i+1}</span>
                  <span className="flex-1 text-sm">{cat}</span>
                  <div className="flex flex-col shrink-0">
                    <button
                      type="button"
                      onClick={() => moveItem(i, i - 1)}
                      disabled={i === 0}
                      className="text-charcoal-400 hover:text-orange-500 disabled:opacity-20 leading-none px-1 py-0.5 text-xs"
                    >▲</button>
                    <button
                      type="button"
                      onClick={() => moveItem(i, i + 1)}
                      disabled={i === tempOrder.length - 1}
                      className="text-charcoal-400 hover:text-orange-500 disabled:opacity-20 leading-none px-1 py-0.5 text-xs"
                    >▼</button>
                  </div>
                  <span className="text-charcoal-300 dark:text-charcoal-600 cursor-grab hidden md:block">⠿</span>
                </li>
              ))}
            </ul>
            <div className="flex gap-2">
              <button onClick={() => setShowReorder(false)} className="btn-ghost flex-1">Cancel</button>
              <button onClick={saveOverride} className="btn-primary flex-1">Apply Today</button>
            </div>
          </div>
        </div>
      )}

      {showModal && (
        <TaskModal
          task={editTask}
          categories={priorityOrder}
          assets={assetsEnabled ? assetList : null}
          onClose={() => { setShowModal(false); setEditTask(null) }}
          onSave={() => { setShowModal(false); setEditTask(null); load() }}
          onDelete={() => { setShowModal(false); setEditTask(null); load() }}
        />
      )}

      {/* Clears the fixed mobile footer nav so the last task is never hidden behind it */}
      <div className="h-20 md:hidden" aria-hidden="true" />
    </div>
  )
}

function TaskCard({ task, catColor, today, onDone, onEdit, onTagClick }) {
  const overdue = task.due_date && task.due_date < today && task.status === 'pending'

  return (
    <div className={`card p-3 flex items-start gap-3 overflow-hidden ${overdue ? 'border-red-500/40' : ''}`}>
      <button
        onClick={onDone}
        className={`mt-0.5 shrink-0 w-5 h-5 rounded transition-colors flex items-center justify-center text-white text-xs ${
          task.status === 'done'
            ? 'bg-orange-500 hover:bg-orange-400'
            : 'border-2 border-charcoal-300 dark:border-charcoal-600 hover:border-orange-500 hover:bg-orange-500'
        }`}
      >
        {task.status === 'done' && '✓'}
      </button>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className={`badge ${catColor}`}>{task.category}</span>
          <span className="badge bg-charcoal-100 dark:bg-charcoal-700 text-charcoal-600 dark:text-charcoal-300">
            {task.priority}
          </span>
          {task._source === 'household' && <span className="text-xs text-blue-500 dark:text-blue-400">🏠</span>}
          {task._source === 'team' && <span className="text-xs text-indigo-500 dark:text-indigo-400">🧑‍🤝‍🧑</span>}
          {task.streak_count > 0 && (
            <span className="text-xs text-orange-500">🔥 {task.streak_count}</span>
          )}
          {overdue && <span className="text-xs text-red-500 font-medium">OVERDUE</span>}
        </div>
        <p className={`text-sm mt-1 truncate ${task.status === 'done' ? 'line-through text-charcoal-400' : ''}`}>
          {task.title}
        </p>
        {task.due_date && (
          <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mt-0.5">
            Due {task.due_date}{task.due_time && ` · ${fmtDueTime(task.due_time)}`}
          </p>
        )}
        {task.notes && (
          <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mt-0.5 truncate">{task.notes}</p>
        )}
        {task.tags?.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1.5">
            {task.tags.map(t => (
              <span
                key={t}
                onClick={() => onTagClick(t)}
                className="inline-flex items-center bg-orange-100 dark:bg-orange-900/40 text-orange-700 dark:text-orange-300 text-[11px] px-1.5 py-0.5 rounded-full hover:bg-orange-200 dark:hover:bg-orange-900/70 cursor-pointer"
              >
                {t}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="shrink-0">
        <button onClick={onEdit} className="text-charcoal-400 hover:text-orange-500 p-1 text-xs">✎</button>
      </div>
    </div>
  )
}
