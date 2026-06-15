import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { tasks as tasksApi } from '../lib/api'
import { useAuth } from '../lib/auth'
import TaskModal from '../components/TaskModal'

const CATEGORY_COLORS = {
  God:             'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300',
  Family:          'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
  Job:             'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
  LogCore:         'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300',
  'Personal Growth':'bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-300',
  Hobbies:         'bg-pink-100 text-pink-700 dark:bg-pink-900/30 dark:text-pink-300',
}

function catColor(cat) {
  return CATEGORY_COLORS[cat] || 'bg-charcoal-100 text-charcoal-700 dark:bg-charcoal-700 dark:text-charcoal-300'
}

function priorityDot(p) {
  return p === 'High' ? 'bg-red-500' : p === 'Medium' ? 'bg-yellow-500' : 'bg-charcoal-400'
}

export default function Dashboard() {
  const { user } = useAuth()
  const [top3, setTop3] = useState([])
  const [today, setToday] = useState([])
  const [streaks, setStreaks] = useState([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [completing, setCompleting] = useState(null)

  async function load() {
    setLoading(true)
    try {
      const [t3, all] = await Promise.all([tasksApi.top3(), tasksApi.list()])
      setTop3(t3)
      const todayStr = new Date().toISOString().split('T')[0]
      setToday(all.filter(t => t.status === 'pending' && t.due_date === todayStr))
      setStreaks(all.filter(t => t.type === 'recurring' && (t.streak_count || 0) > 0)
        .sort((a, b) => b.streak_count - a.streak_count)
        .slice(0, 5))
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  async function markDone(id) {
    setCompleting(id)
    try {
      await tasksApi.update(id, { status: 'done' })
      await load()
    } finally {
      setCompleting(null)
    }
  }

  const todayDate = new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">Good {greeting()}, {user?.name?.split(' ')[0]}</h1>
          <p className="text-charcoal-500 dark:text-charcoal-400 text-sm mt-0.5">{todayDate}</p>
        </div>
        <button onClick={() => setShowModal(true)} className="btn-primary">
          + Add Task
        </button>
      </div>

      {/* Top 3 */}
      <div className="card p-5">
        <h2 className="font-semibold text-sm uppercase tracking-wide text-orange-500 mb-3">
          🎯 Top 3 Right Now
        </h2>
        {loading ? (
          <div className="space-y-3">
            {[1,2,3].map(i => <Skeleton key={i} />)}
          </div>
        ) : top3.length === 0 ? (
          <p className="text-charcoal-500 dark:text-charcoal-400 text-sm">
            No pending tasks. <Link to="/tasks" className="text-orange-500">Add one →</Link>
          </p>
        ) : (
          <ol className="space-y-3">
            {top3.map((task, i) => (
              <li key={task.id} className="flex items-start gap-3">
                <span className="text-orange-500 font-bold text-lg leading-none w-5 mt-0.5">{i+1}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`badge ${catColor(task.category)}`}>{task.category}</span>
                    <div className={`w-2 h-2 rounded-full ${priorityDot(task.priority)}`} />
                    {task.streak_count > 0 && (
                      <span className="text-xs text-orange-500">🔥 {task.streak_count}</span>
                    )}
                  </div>
                  <p className="font-medium mt-1 text-sm">{task.title}</p>
                  {task.due_date && (
                    <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mt-0.5">
                      Due {task.due_date}
                    </p>
                  )}
                </div>
                <button
                  onClick={() => markDone(task.id)}
                  disabled={completing === task.id}
                  className="shrink-0 w-6 h-6 rounded-full border-2 border-charcoal-300 dark:border-charcoal-600 hover:border-orange-500 hover:bg-orange-500 transition-colors flex items-center justify-center"
                  title="Mark done"
                >
                  {completing === task.id && <span className="text-xs">…</span>}
                </button>
              </li>
            ))}
          </ol>
        )}
      </div>

      {/* Streaks */}
      {streaks.length > 0 && (
        <div className="card p-5">
          <h2 className="font-semibold text-sm uppercase tracking-wide text-charcoal-500 dark:text-charcoal-400 mb-3">
            🔥 Active Streaks
          </h2>
          <div className="space-y-2">
            {streaks.map(task => (
              <div key={task.id} className="flex items-center justify-between">
                <div className="flex items-center gap-2 min-w-0">
                  <span className={`badge ${catColor(task.category)}`}>{task.category}</span>
                  <span className="text-sm truncate">{task.title}</span>
                </div>
                <span className="text-orange-500 font-semibold text-sm shrink-0 ml-2">
                  {task.streak_count} days
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Due Today */}
      {today.length > 0 && (
        <div className="card p-5">
          <h2 className="font-semibold text-sm uppercase tracking-wide text-charcoal-500 dark:text-charcoal-400 mb-3">
            📅 Due Today
          </h2>
          <div className="space-y-2">
            {today.map(task => (
              <div key={task.id} className="flex items-center gap-3">
                <button
                  onClick={() => markDone(task.id)}
                  disabled={completing === task.id}
                  className="shrink-0 w-5 h-5 rounded border-2 border-charcoal-300 dark:border-charcoal-600 hover:border-orange-500 hover:bg-orange-500 transition-colors"
                />
                <span className={`badge shrink-0 ${catColor(task.category)}`}>{task.category}</span>
                <span className="text-sm flex-1">{task.title}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {showModal && (
        <TaskModal onClose={() => setShowModal(false)} onSave={() => { setShowModal(false); load() }} />
      )}
    </div>
  )
}

function greeting() {
  const h = new Date().getHours()
  return h < 12 ? 'morning' : h < 17 ? 'afternoon' : 'evening'
}

function Skeleton() {
  return <div className="h-12 bg-charcoal-100 dark:bg-charcoal-700 rounded-lg animate-pulse" />
}
