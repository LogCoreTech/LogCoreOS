import { useEffect, useState } from 'react'
import { shared as sharedApi } from '../lib/api'
import TaskModal from '../components/TaskModal'
import { catColor } from '../lib/constants'

export default function Household() {
  const [tasks, setTasks]   = useState([])
  const [filter, setFilter] = useState('pending')
  const [editTask, setEditTask]   = useState(null)
  const [showModal, setShowModal] = useState(false)
  const [confirmDeleteId, setConfirmDeleteId] = useState(null)
  const [loading, setLoading] = useState(true)

  async function load() {
    setLoading(true)
    try {
      setTasks(await sharedApi.list())
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  async function markDone(id) {
    await sharedApi.update(id, { status: 'done' })
    load()
  }

  async function remove(id) {
    await sharedApi.remove(id)
    setConfirmDeleteId(null)
    load()
  }

  const filtered = tasks.filter(t =>
    filter === 'all'     ? true :
    filter === 'pending' ? t.status === 'pending' :
    filter === 'done'    ? t.status !== 'pending' : true
  )

  const grouped = filtered.reduce((acc, t) => {
    const key = t.category || 'Other'
    if (!acc[key]) acc[key] = []
    acc[key].push(t)
    return acc
  }, {})

  const pendingCount = tasks.filter(t => t.status === 'pending').length

  return (
    <div className="max-w-2xl mx-auto space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Household</h1>
          <p className="text-sm text-charcoal-500 dark:text-charcoal-400 mt-0.5">
            Shared tasks visible to everyone
          </p>
        </div>
        <button
          onClick={() => { setEditTask(null); setShowModal(true) }}
          className="btn-primary"
        >
          + Add
        </button>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-1 bg-charcoal-100 dark:bg-charcoal-800 rounded-lg p-1">
        {['pending', 'done', 'all'].map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`flex-1 py-1 rounded-md text-xs font-medium capitalize transition-colors ${
              filter === f
                ? 'bg-white dark:bg-charcoal-600 text-charcoal-900 dark:text-gray-100 shadow-sm'
                : 'text-charcoal-500 dark:text-charcoal-400'
            }`}
          >
            {f}{f === 'pending' && pendingCount > 0 ? ` (${pendingCount})` : ''}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => <div key={i} className="h-16 card animate-pulse" />)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="card p-8 text-center text-charcoal-500 dark:text-charcoal-400">
          <p className="text-4xl mb-2">🏠</p>
          <p className="font-medium mb-1">
            {tasks.length === 0 ? 'No shared tasks yet' : 'Nothing here'}
          </p>
          {tasks.length === 0 && (
            <p className="text-sm">Add tasks that everyone in your household can see.</p>
          )}
        </div>
      ) : (
        <div className="space-y-5">
          {Object.entries(grouped).map(([cat, items]) => (
            <div key={cat}>
              <h2 className="text-xs font-semibold uppercase tracking-widest text-charcoal-500 dark:text-charcoal-400 mb-2">
                {cat}
              </h2>
              <div className="space-y-2">
                {items.map(task => (
                  <SharedTaskCard
                    key={task.id}
                    task={task}
                    color={catColor(task.category)}
                    onDone={() => markDone(task.id)}
                    onEdit={() => { setEditTask(task); setShowModal(true) }}
                    onDelete={() => setConfirmDeleteId(task.id)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

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

      {showModal && (
        <TaskModal
          task={editTask}
          saveApi={sharedApi}
          onClose={() => { setShowModal(false); setEditTask(null) }}
          onSave={() => { setShowModal(false); setEditTask(null); load() }}
        />
      )}
    </div>
  )
}

function SharedTaskCard({ task, color, onDone, onEdit, onDelete }) {
  const today = new Date().toISOString().split('T')[0]
  const overdue = task.due_date && task.due_date < today && task.status === 'pending'
  const done = task.status !== 'pending'

  return (
    <div className={`card p-3 flex items-start gap-3 ${overdue ? 'border-red-500/40' : ''}`}>
      {done ? (
        <div className="mt-0.5 shrink-0 w-5 h-5 rounded bg-orange-500 flex items-center justify-center text-white text-xs">✓</div>
      ) : (
        <button
          onClick={onDone}
          className="mt-0.5 shrink-0 w-5 h-5 rounded border-2 border-charcoal-300 dark:border-charcoal-600 hover:border-orange-500 hover:bg-orange-500 transition-colors"
        />
      )}

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className={`badge ${color}`}>{task.category}</span>
          <span className="badge bg-charcoal-100 dark:bg-charcoal-700 text-charcoal-600 dark:text-charcoal-300">
            {task.priority}
          </span>
          {overdue && <span className="text-xs text-red-500 font-medium">OVERDUE</span>}
        </div>
        <p className={`text-sm mt-1 ${done ? 'line-through text-charcoal-400' : ''}`}>
          {task.title}
        </p>
        <div className="flex items-center gap-2 mt-0.5">
          {task.due_date && (
            <span className="text-xs text-charcoal-500 dark:text-charcoal-400">Due {task.due_date}</span>
          )}
          {task.created_by && (
            <span className="text-xs text-charcoal-400">by {task.created_by}</span>
          )}
          {task.completed_by && done && (
            <span className="text-xs text-charcoal-400">done by {task.completed_by}</span>
          )}
        </div>
      </div>

      <div className="flex gap-1 shrink-0">
        <button onClick={onEdit} className="text-charcoal-400 hover:text-orange-500 p-1 text-xs">✎</button>
        <button onClick={onDelete} className="text-charcoal-400 hover:text-red-500 p-1 text-xs">✕</button>
      </div>
    </div>
  )
}
