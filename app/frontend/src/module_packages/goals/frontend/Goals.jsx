import { useEffect, useState } from 'react'
import HelpButton from '../../../components/HelpButton'
import { goals as goalsApi } from './api'
import { priorities as prioritiesApi } from '../../../lib/api'
import { useWorkspace } from '../../../lib/workspace'
import { useAuth } from '../../../lib/auth'
import { catColor } from '../../../lib/constants'
import GoalModal from './GoalModal'

export default function Goals() {
  const { workspace } = useWorkspace()
  const { user, activeModuleIds } = useAuth()
  const [goals, setGoals] = useState([])
  const [categories, setCategories] = useState([])
  const [tab, setTab] = useState('me') // 'me' | 'pool'
  const [filter, setFilter] = useState('pending')
  const [timeframe, setTimeframe] = useState('all')
  const [tagFilter, setTagFilter] = useState(null)
  const [openGoalId, setOpenGoalId] = useState(null)
  const [openGoalPool, setOpenGoalPool] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const [loading, setLoading] = useState(true)

  // Ownership is the tab axis: "ME" = everything you personally own, any
  // depth; the pool tab (labeled per workspace) = your household/team's
  // goals. Hidden entirely when that pool module isn't installed/enabled
  // for you — a member without pool_edit still sees it (read-only, same as
  // pool tasks/notes today), it only disappears when the module itself is off.
  const poolId = workspace === 'business' ? 'team' : 'household'
  const poolLabel = workspace === 'business' ? 'Team' : 'Household'
  const poolAvailable = activeModuleIds?.includes(poolId) && !user?.disabledModules?.includes(poolId)

  async function load() {
    setLoading(true)
    try {
      const [all, prio] = await Promise.all([goalsApi.list(), prioritiesApi.get()])
      setGoals(all)
      setCategories(prio.order || [])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [workspace])
  useEffect(() => { if (!poolAvailable && tab === 'pool') setTab('me') }, [poolAvailable, tab])

  const fmt = dt => `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`
  const todayStr = fmt(new Date())
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
    if (!g.due_date) return true // undated goals are common now (due_date is optional) — always shown
    return horizon === null || g.due_date <= horizon
  }

  const isPoolGoal = g => !!g._owner && g._owner.startsWith('_')
  const tabGoals = goals.filter(g => isPoolGoal(g) === (tab === 'pool'))

  const windowGoals = tabGoals.filter(inWindow)
  const filtered = windowGoals
    .filter(g => (filter === 'pending' ? g.status !== 'done' : filter === 'done' ? g.status === 'done' : true))
    .filter(g => !tagFilter || (g.tags || []).includes(tagFilter))

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2">
          <h1 className="text-2xl font-bold">Goals</h1>
          <HelpButton section="goals" />
        </span>
        <button onClick={() => setShowCreate(true)} className="btn-primary text-sm">
          + Add Goal
        </button>
      </div>

      {/* ME / pool tabs */}
      {poolAvailable && (
        <div className="flex gap-1 bg-charcoal-100 dark:bg-charcoal-800 rounded-lg p-1">
          {[['me', 'ME'], ['pool', poolLabel]].map(([t, label]) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`flex-1 py-1.5 rounded-md text-sm font-medium transition-colors ${
                tab === t
                  ? 'bg-white dark:bg-charcoal-600 text-charcoal-900 dark:text-gray-100 shadow-sm'
                  : 'text-charcoal-500 dark:text-charcoal-400'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      )}

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

      {tagFilter && (
        <button
          onClick={() => setTagFilter(null)}
          className="inline-flex items-center gap-1.5 bg-orange-100 dark:bg-orange-900/40 text-orange-700 dark:text-orange-300 text-xs px-2.5 py-1 rounded-full"
        >
          Tag: {tagFilter} <span className="font-bold">✕</span>
        </button>
      )}

      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3].map(i => <div key={i} className="h-16 bg-charcoal-100 dark:bg-charcoal-800 rounded-lg animate-pulse" />)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="py-8 text-center text-charcoal-500 dark:text-charcoal-400">
          <p className="text-3xl mb-2">🎯</p>
          <p className="font-medium text-sm">
            {tabGoals.length === 0 ? (tab === 'pool' ? `No ${poolLabel.toLowerCase()} goals yet` : 'No goals yet') : 'Nothing here'}
          </p>
          {tabGoals.length === 0 && (
            <p className="text-xs mt-1">Set a goal to start tracking your progress.</p>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map(goal => (
            <GoalCard
              key={goal.id}
              goal={goal}
              color={catColor(goal.category)}
              today={todayStr}
              onOpen={() => { setOpenGoalId(goal.id); setOpenGoalPool(isPoolGoal(goal)) }}
              onTagClick={t => setTagFilter(t)}
            />
          ))}
        </div>
      )}

      {(openGoalId || showCreate) && (
        <GoalModal
          goalId={openGoalId}
          pool={showCreate ? tab === 'pool' : openGoalPool}
          workspace={workspace}
          categories={categories}
          onClose={() => { setOpenGoalId(null); setShowCreate(false) }}
          onChanged={load}
          onOpenGoal={id => { setOpenGoalId(id); setOpenGoalPool(false) }}
        />
      )}

      <div className="h-20 md:hidden" aria-hidden="true" />
    </div>
  )
}

function GoalCard({ goal, color, today, onOpen, onTagClick }) {
  const overdue = goal.due_date && goal.due_date < today && goal.status !== 'done'
  const done = goal.status === 'done'

  return (
    <div className={`card p-4 flex items-start gap-3 ${overdue ? 'border-red-500/40' : ''}`}>
      <button onClick={onOpen} className="flex-1 min-w-0 text-left">
        <div className="flex items-center gap-1.5 flex-wrap mb-1">
          <span className={`badge ${color}`}>{goal.category || 'Uncategorized'}</span>
          {goal.parent_id && (
            <span className="badge bg-charcoal-100 dark:bg-charcoal-700 text-charcoal-600 dark:text-charcoal-300">Subgoal</span>
          )}
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
        {goal.tags?.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1.5">
            {goal.tags.map(t => (
              <span
                key={t}
                onClick={e => { e.stopPropagation(); onTagClick(t) }}
                className="inline-flex items-center bg-orange-100 dark:bg-orange-900/40 text-orange-700 dark:text-orange-300 text-[11px] px-1.5 py-0.5 rounded-full hover:bg-orange-200 dark:hover:bg-orange-900/70"
              >
                {t}
              </span>
            ))}
          </div>
        )}
      </button>
      <button onClick={onOpen} className="shrink-0 text-right">
        <span className="text-sm font-semibold text-orange-500">{goal.progress?.pct ?? 0}%</span>
      </button>
    </div>
  )
}
