import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { tasks as tasksApi, auth as authApi, home as homeApi } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useWorkspace } from '../lib/workspace'
import TaskModal from '../components/TaskModal'
import { catColor } from '../lib/constants'

function priorityDot(p) {
  return p === 'High' ? 'bg-red-500' : p === 'Medium' ? 'bg-yellow-500' : 'bg-charcoal-400'
}

export default function Dashboard() {
  const { user } = useAuth()
  const { workspace } = useWorkspace()
  const [top3, setTop3] = useState([])
  const [today, setToday] = useState([])
  const [streaks, setStreaks] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showModal, setShowModal] = useState(false)
  const [completing, setCompleting] = useState(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const [t3, all, todayResp] = await Promise.all([
        tasksApi.top3(), tasksApi.list(), authApi.today(),
      ])
      const todayStr = todayResp?.today ?? new Date().toISOString().split('T')[0]
      setTop3(t3)
      setToday(all.filter(t => t.status === 'pending' && t.due_date === todayStr))
      setStreaks(all.filter(t => t.type === 'recurring' && (t.streak_count || 0) > 0)
        .sort((a, b) => b.streak_count - a.streak_count)
        .slice(0, 5))
    } catch (e) {
      setError(e.message || 'Failed to load dashboard')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [workspace])

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

      {error && (
        <p className="text-sm text-red-500 dark:text-red-400">{error}</p>
      )}

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

      {/* Smart Home widget */}
      {!user?.disabledModules?.includes('home') && <HomeWidget />}

      {showModal && (
        <TaskModal onClose={() => setShowModal(false)} onSave={() => { setShowModal(false); load() }} />
      )}
    </div>
  )
}

function HomeWidget() {
  const [favEntities, setFavEntities] = useState([])
  const [loaded, setLoaded] = useState(false)

  async function load() {
    try {
      const [favIds, all] = await Promise.all([homeApi.getFavourites(), homeApi.entities()])
      if (!favIds?.length) { setLoaded(true); return }
      const favSet = new Set(favIds)
      setFavEntities((all || []).filter(e => favSet.has(e.entity_id)))
    } catch {
      // HA not configured — silently skip
    } finally {
      setLoaded(true)
    }
  }

  useEffect(() => {
    load()
    const t = setInterval(load, 30000)
    return () => clearInterval(t)
  }, [])

  if (!loaded || !favEntities.length) return null

  async function quickToggle(entity) {
    const domain = entity.entity_id.split('.')[0]
    if (!['light', 'switch', 'input_boolean'].includes(domain)) return
    const svc = entity.state === 'on' ? 'turn_off' : 'turn_on'
    try {
      await homeApi.callService(entity.entity_id, { service: svc, data: {} })
      setTimeout(load, 800)
    } catch {}
  }

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-semibold text-sm uppercase tracking-wide text-charcoal-500 dark:text-charcoal-400">
          💡 Smart Home
        </h2>
        <Link to="/home" className="text-xs text-orange-500 hover:underline">All devices →</Link>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
        {favEntities.map(e => {
          const domain = e.entity_id.split('.')[0]
          const isToggleable = ['light', 'switch', 'input_boolean'].includes(domain)
          const name = e.attributes?.friendly_name || e.entity_id
          const isOn = e.state === 'on'
          return (
            <button
              key={e.entity_id}
              onClick={() => quickToggle(e)}
              disabled={!isToggleable}
              className={`text-left p-2 rounded-lg border transition-colors
                ${isOn
                  ? 'border-orange-300 bg-orange-50 dark:border-orange-700 dark:bg-orange-900/20'
                  : 'border-charcoal-200 dark:border-charcoal-700 bg-charcoal-50 dark:bg-charcoal-800'
                }
                ${isToggleable ? 'hover:border-orange-400 cursor-pointer' : 'cursor-default'}`}
            >
              <p className="text-xs text-charcoal-400 dark:text-charcoal-500 truncate">{domain}</p>
              <p className="text-sm font-medium truncate">{name}</p>
              <p className={`text-xs font-semibold mt-0.5 ${isOn ? 'text-orange-500' : 'text-charcoal-400 dark:text-charcoal-500'}`}>
                {e.state}{e.attributes?.unit_of_measurement ? ` ${e.attributes.unit_of_measurement}` : ''}
              </p>
            </button>
          )
        })}
      </div>
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
