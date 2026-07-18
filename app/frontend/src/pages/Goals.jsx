import { useEffect, useState } from 'react'
import HelpButton from '../components/HelpButton'
import { tasks as tasksApi, priorities as prioritiesApi } from '../lib/api'
import { useWorkspace } from '../lib/workspace'
import TaskModal from '../components/TaskModal'
import { catColor } from '../lib/constants'

export default function Goals() {
  const { workspace } = useWorkspace()
  const [goals, setGoals] = useState([])
  const [categories, setCategories] = useState([])
  const [filter, setFilter] = useState('pending')
  const [timeframe, setTimeframe] = useState('month')
  const [editTask, setEditTask] = useState(null)
  const [showModal, setShowModal] = useState(false)
  const [confirmDeleteId, setConfirmDeleteId] = useState(null)
  const [loading, setLoading] = useState(true)

  async function load() {
    setLoading(true)
    try {
      const [all, prio] = await Promise.all([tasksApi.list(), prioritiesApi.get()])
      setGoals(all.filter(t => t.type === 'goal'))
      setCategories(prio.order || [])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [workspace])

  async function toggleDone(goal) {
    await tasksApi.update(goal.id, { status: goal.status === 'done' ? 'pending' : 'done' })
    load()
  }

  async function remove(id) {
    await tasksApi.remove(id)
    setConfirmDeleteId(null)
    load()
  }

  async function clearCompleted() {
    if (!window.confirm('Archive all completed goals? They move to history and leave the Done list.')) return
    await tasksApi.cleanupGoals()
    load()
  }

  // Timeline window: goals due on or before the end of the selected period.
  // Overdue goals (due in the past) fall inside every window; undated goals
  // (legacy — new goals require a date) only surface under "All".
  const fmt = dt => `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`
  function periodEnd(tf) {
    const d = new Date()
    if (tf === 'day') return fmt(d)
    if (tf === 'week') { const e = new Date(d); e.setDate(d.getDate() + 6); return fmt(e) }
    if (tf === 'month') return fmt(new Date(d.getFullYear(), d.getMonth() + 1, 0))
    if (tf === 'quarter') { const q = Math.floor(d.getMonth() / 3); return fmt(new Date(d.getFullYear(), q * 3 + 3, 0)) }
    if (tf === 'year') return `${d.getFullYear()}-12-31`
    return null // 'all'
  }
  const horizon = periodEnd(timeframe)
  const inWindow = g => {
    if (!g.due_date) return timeframe === 'all'
    return horizon === null || g.due_date <= horizon
  }

  const windowGoals = goals.filter(inWindow)
  const filtered = windowGoals.filter(g =>
    filter === 'pending' ? g.status === 'pending' :
    filter === 'done'    ? g.status === 'done' : true
  )

  const total = windowGoals.length
  const done  = windowGoals.filter(g => g.status === 'done').length
  const pct   = total === 0 ? 0 : Math.round((done / total) * 100)
  const doneCount = goals.filter(g => g.status === 'done').length

  const grouped = categories.map(cat => ({
    cat,
    items: filtered.filter(g => g.category === cat)
  })).filter(g => g.items.length > 0)

  const knownCats = new Set(categories)
  const other = filtered.filter(g => !knownCats.has(g.category))

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2">
          <h1 className="text-2xl font-bold">Goals</h1>
          <HelpButton section="goals" />
        </span>
        <div className="flex gap-2">
          {doneCount > 0 && (
            <button onClick={clearCompleted} className="btn-ghost text-sm">
              Clear completed
            </button>
          )}
          <button
            onClick={() => { setEditTask(null); setShowModal(true) }}
            className="btn-primary text-sm"
          >
            + Add Goal
          </button>
        </div>
      </div>

      {/* Timeline filter */}
      <div className="flex gap-1 bg-charcoal-100 dark:bg-charcoal-800 rounded-lg p-1 overflow-x-auto">
        {[['day', 'Day'], ['week', 'Week'], ['month', 'Month'], ['quarter', 'Quarter'], ['year', 'Year'], ['all', 'All']].map(([tf, label]) => (
          <button
            key={tf}
            onClick={() => setTimeframe(tf)}
            className={`flex-1 py-1 px-2 rounded-md text-xs font-medium transition-colors whitespace-nowrap ${
              timeframe === tf
                ? 'bg-white dark:bg-charcoal-600 text-charcoal-900 dark:text-gray-100 shadow-sm'
                : 'text-charcoal-500 dark:text-charcoal-400'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Progress summary — reflects the selected timeline window */}
      {total > 0 && (
        <div className="bg-charcoal-50 dark:bg-charcoal-800 rounded-lg p-3">
          <div className="flex items-center justify-between text-sm mb-2">
            <span className="font-medium">{done} of {total} complete</span>
            <span className="text-orange-500 font-semibold">{pct}%</span>
          </div>
          <div className="h-2 bg-charcoal-200 dark:bg-charcoal-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-orange-500 rounded-full transition-all duration-500"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      )}

      {/* Status tabs */}
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
            {f}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3].map(i => <div key={i} className="h-16 bg-charcoal-100 dark:bg-charcoal-800 rounded-lg animate-pulse" />)}
        </div>
      ) : grouped.length === 0 && other.length === 0 ? (
        <div className="py-8 text-center text-charcoal-500 dark:text-charcoal-400">
          <p className="text-3xl mb-2">🎯</p>
          <p className="font-medium text-sm">
            {goals.length === 0 ? 'No goals yet' : 'Nothing here'}
          </p>
          {goals.length === 0 && (
            <p className="text-xs mt-1">Set a goal to start tracking your progress.</p>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          {grouped.map(({ cat, items }) => (
            <div key={cat}>
              <h3 className="text-xs font-semibold uppercase tracking-widest text-charcoal-500 dark:text-charcoal-400 mb-2">
                {cat}
              </h3>
              <div className="space-y-2">
                {items.map(goal => (
                  <GoalCard
                    key={goal.id}
                    goal={goal}
                    color={catColor(goal.category)}
                    onDone={() => toggleDone(goal)}
                    onEdit={() => { setEditTask(goal); setShowModal(true) }}
                    onDelete={() => setConfirmDeleteId(goal.id)}
                  />
                ))}
              </div>
            </div>
          ))}
          {other.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-widest text-charcoal-500 mb-2">Other</h3>
              <div className="space-y-2">
                {other.map(goal => (
                  <GoalCard
                    key={goal.id}
                    goal={goal}
                    color={catColor(goal.category)}
                    onDone={() => toggleDone(goal)}
                    onEdit={() => { setEditTask(goal); setShowModal(true) }}
                    onDelete={() => setConfirmDeleteId(goal.id)}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {confirmDeleteId && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
          <div className="card p-5 w-full max-w-xs">
            <h2 className="font-semibold mb-1">Delete Goal?</h2>
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
          defaultType="goal"
          categories={categories}
          onClose={() => { setShowModal(false); setEditTask(null) }}
          onSave={() => { setShowModal(false); setEditTask(null); load() }}
        />
      )}
    </div>
  )
}

function GoalCard({ goal, color, onDone, onEdit, onDelete }) {
  const today = new Date().toISOString().split('T')[0]
  const overdue = goal.due_date && goal.due_date < today && goal.status === 'pending'
  const done = goal.status === 'done'

  return (
    <div className={`card p-4 flex items-start gap-3 ${overdue ? 'border-red-500/40' : ''}`}>
      <button
        onClick={onDone}
        title={done ? 'Mark as not done' : 'Mark done'}
        className={`mt-0.5 shrink-0 w-6 h-6 rounded-full border-2 flex items-center justify-center transition-colors ${
          done
            ? 'border-orange-500 bg-orange-500 text-white hover:bg-orange-600'
            : 'border-charcoal-300 dark:border-charcoal-600 hover:border-orange-500 hover:bg-orange-50 dark:hover:bg-orange-900/20'
        }`}
      >
        {done && <span className="text-xs">✓</span>}
      </button>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 flex-wrap mb-1">
          <span className={`badge ${color}`}>{goal.category}</span>
          <span className="badge bg-charcoal-100 dark:bg-charcoal-700 text-charcoal-600 dark:text-charcoal-300">
            {goal.priority}
          </span>
          {overdue && <span className="text-xs text-red-500 font-medium">OVERDUE</span>}
        </div>
        <p className={`text-sm font-medium ${done ? 'line-through text-charcoal-400' : ''}`}>
          {goal.title}
        </p>
        {goal.due_date && (
          <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mt-0.5">
            Target: {goal.due_date}
          </p>
        )}
        {goal.notes && (
          <p className="text-xs text-charcoal-400 mt-1 line-clamp-2">{goal.notes}</p>
        )}
      </div>

      <div className="flex gap-1 shrink-0">
        <button onClick={onEdit} className="text-charcoal-400 hover:text-orange-500 p-1 text-xs">✎</button>
        <button onClick={onDelete} className="text-charcoal-400 hover:text-red-500 p-1 text-xs">✕</button>
      </div>
    </div>
  )
}
