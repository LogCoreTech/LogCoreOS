import { useEffect, useState } from 'react'
import { tasks as tasksApi, priorities as prioritiesApi } from '../lib/api'
import TaskModal from '../components/TaskModal'
import { catColor } from '../lib/constants'

const PRIORITY_ORDER = ['High', 'Medium', 'Low']

export default function Tasks() {
  const [taskList, setTaskList] = useState([])
  const [priorityOrder, setPriorityOrder] = useState([])
  const [filter, setFilter] = useState('pending')
  const [editTask, setEditTask] = useState(null)
  const [showModal, setShowModal] = useState(false)
  const [showReorder, setShowReorder] = useState(false)
  const [tempOrder, setTempOrder] = useState([])
  const [dragIdx, setDragIdx] = useState(null)
  const [loading, setLoading] = useState(true)
  const [confirmDeleteId, setConfirmDeleteId] = useState(null)

  async function load() {
    setLoading(true)
    try {
      const [all, prio] = await Promise.all([tasksApi.list(), prioritiesApi.get()])
      setTaskList(all)
      setPriorityOrder(prio.order || [])
      setTempOrder(prio.order || [])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  async function markDone(id) {
    await tasksApi.update(id, { status: 'done' })
    load()
  }

  async function remove(id) {
    await tasksApi.remove(id)
    setConfirmDeleteId(null)
    load()
  }

  async function saveOverride() {
    await prioritiesApi.override(tempOrder)
    setPriorityOrder(tempOrder)
    setShowReorder(false)
  }

  // Drag for reorder modal
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

  const filtered = taskList.filter(t =>
    filter === 'all'     ? true :
    filter === 'pending' ? t.status === 'pending' :
    filter === 'done'    ? t.status === 'done' :
    filter === 'overdue' ? (t.status === 'pending' && t.due_date && t.due_date < new Date().toISOString().split('T')[0]) : true
  )

  // Group by priority order, then by priority within group
  const grouped = priorityOrder.map(cat => ({
    cat,
    tasks: filtered
      .filter(t => t.category === cat)
      .sort((a, b) => PRIORITY_ORDER.indexOf(a.priority) - PRIORITY_ORDER.indexOf(b.priority))
  })).filter(g => g.tasks.length > 0)

  // Uncategorized (categories not in priority order)
  const knownCats = new Set(priorityOrder)
  const uncategorized = filtered.filter(t => !knownCats.has(t.category))

  return (
    <div className="max-w-2xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Tasks</h1>
        <div className="flex gap-2">
          <button
            onClick={() => setShowReorder(true)}
            className="btn-ghost text-sm"
          >
            ⇅ Reorder Today
          </button>
          <button onClick={() => { setEditTask(null); setShowModal(true) }} className="btn-primary">
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

      {loading ? (
        <div className="space-y-3">
          {[1,2,3].map(i => <div key={i} className="h-16 card animate-pulse" />)}
        </div>
      ) : grouped.length === 0 && uncategorized.length === 0 ? (
        <div className="card p-8 text-center text-charcoal-500 dark:text-charcoal-400">
          <p className="text-4xl mb-2">✓</p>
          <p>No tasks here.</p>
        </div>
      ) : (
        <>
          {grouped.map(({ cat, tasks }) => (
            <div key={cat}>
              <h2 className="text-xs font-semibold uppercase tracking-widest text-charcoal-500 dark:text-charcoal-400 mb-2">
                {cat}
              </h2>
              <div className="space-y-2">
                {tasks.map(task => (
                  <TaskCard
                    key={task.id}
                    task={task}
                    catColor={catColor(task.category)}
                    onDone={() => markDone(task.id)}
                    onEdit={() => { setEditTask(task); setShowModal(true) }}
                    onDelete={() => setConfirmDeleteId(task.id)}
                  />
                ))}
              </div>
            </div>
          ))}
          {uncategorized.length > 0 && (
            <div>
              <h2 className="text-xs font-semibold uppercase tracking-widest text-charcoal-500 mb-2">Other</h2>
              <div className="space-y-2">
                {uncategorized.map(task => (
                  <TaskCard
                    key={task.id}
                    task={task}
                    catColor={catColor(task.category)}
                    onDone={() => markDone(task.id)}
                    onEdit={() => { setEditTask(task); setShowModal(true) }}
                    onDelete={() => setConfirmDeleteId(task.id)}
                  />
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* Delete confirmation modal */}
      {confirmDeleteId && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
          <div className="card p-5 w-full max-w-xs">
            <h2 className="font-semibold mb-1">Delete Task?</h2>
            <p className="text-sm text-charcoal-500 dark:text-charcoal-400 mb-4">This cannot be undone.</p>
            <div className="flex gap-2">
              <button onClick={() => setConfirmDeleteId(null)} className="btn-ghost flex-1">Cancel</button>
              <button
                onClick={() => remove(confirmDeleteId)}
                className="flex-1 py-2 rounded-lg bg-red-500 hover:bg-red-600 text-white text-sm font-medium transition-colors"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reorder Today modal */}
      {showReorder && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-end md:items-center justify-center p-4">
          <div className="card p-5 w-full max-w-sm">
            <h3 className="font-semibold mb-1">Reorder Today's Priorities</h3>
            <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mb-4">
              Drag to change order for today only. Resets tomorrow.
            </p>
            <ul className="space-y-2 mb-4">
              {tempOrder.map((cat, i) => (
                <li
                  key={cat}
                  draggable
                  onDragStart={() => onDragStart(i)}
                  onDragOver={e => onDragOver(e, i)}
                  onDragEnd={onDragEnd}
                  className={`flex items-center gap-3 px-3 py-2 rounded-lg border cursor-grab transition-colors ${
                    dragIdx === i
                      ? 'border-orange-500 bg-orange-500/10'
                      : 'border-charcoal-200 dark:border-charcoal-700 bg-white dark:bg-charcoal-800'
                  }`}
                >
                  <span className="text-charcoal-400 text-xs w-4">{i+1}</span>
                  <span className="flex-1 text-sm">{cat}</span>
                  <span className="text-charcoal-300 dark:text-charcoal-600">⠿</span>
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
          onClose={() => { setShowModal(false); setEditTask(null) }}
          onSave={() => { setShowModal(false); setEditTask(null); load() }}
        />
      )}
    </div>
  )
}

function TaskCard({ task, catColor, onDone, onEdit, onDelete }) {
  const today = new Date().toISOString().split('T')[0]
  const overdue = task.due_date && task.due_date < today && task.status === 'pending'

  return (
    <div className={`card p-3 flex items-start gap-3 ${overdue ? 'border-red-500/40' : ''}`}>
      {task.status === 'pending' ? (
        <button
          onClick={onDone}
          className="mt-0.5 shrink-0 w-5 h-5 rounded border-2 border-charcoal-300 dark:border-charcoal-600 hover:border-orange-500 hover:bg-orange-500 transition-colors"
        />
      ) : (
        <div className="mt-0.5 shrink-0 w-5 h-5 rounded bg-orange-500 flex items-center justify-center text-white text-xs">✓</div>
      )}

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className={`badge ${catColor}`}>{task.category}</span>
          <span className="badge bg-charcoal-100 dark:bg-charcoal-700 text-charcoal-600 dark:text-charcoal-300">
            {task.priority}
          </span>
          {task.streak_count > 0 && (
            <span className="text-xs text-orange-500">🔥 {task.streak_count}</span>
          )}
          {overdue && <span className="text-xs text-red-500 font-medium">OVERDUE</span>}
        </div>
        <p className={`text-sm mt-1 ${task.status === 'done' ? 'line-through text-charcoal-400' : ''}`}>
          {task.title}
        </p>
        {task.due_date && (
          <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mt-0.5">Due {task.due_date}</p>
        )}
        {task.notes && (
          <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mt-0.5 truncate">{task.notes}</p>
        )}
      </div>

      <div className="flex gap-1 shrink-0">
        <button onClick={onEdit} className="text-charcoal-400 hover:text-orange-500 p-1 text-xs">✎</button>
        <button onClick={onDelete} className="text-charcoal-400 hover:text-red-500 p-1 text-xs">✕</button>
      </div>
    </div>
  )
}
