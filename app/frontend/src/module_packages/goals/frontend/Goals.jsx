import { useEffect, useMemo, useState } from 'react'
import HelpButton from '../../../components/HelpButton'
import { goals as goalsApi } from './api'
import { tasks as tasksApi } from '../../tasks/frontend/api'
import { priorities as prioritiesApi } from '../../../lib/api'
import { useWorkspace } from '../../../lib/workspace'
import { useAuth } from '../../../lib/auth'
import { catColor } from '../../../lib/constants'
import GoalModal, { poolTaskApi } from './GoalModal'

export default function Goals() {
  const { workspace } = useWorkspace()
  const { user, activeModuleIds } = useAuth()
  const [goals, setGoals] = useState([])
  const [categories, setCategories] = useState([])
  const [tab, setTab] = useState('me') // 'me' | 'pool'
  const [filter, setFilter] = useState('pending')
  const [timeframe, setTimeframe] = useState('all')
  const [tagFilter, setTagFilter] = useState(null)
  const [expanded, setExpanded] = useState(new Set())
  const [tasksByGoal, setTasksByGoal] = useState({})
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

  // Linked tasks shown inline in the hierarchy (owner ask, 2026-08-30:
  // "goals... work similar to assets with the condense and expand
  // buttons... with linked tasks also visible with it") — fetched once per
  // tab/workspace and grouped by goal_id client-side, the same "fetch
  // everything, group locally" shape Assets' own tree already uses for its
  // parent/child grouping, rather than a new backend endpoint.
  useEffect(() => {
    let cancelled = false
    async function loadTasks() {
      const api = tab === 'pool' ? await poolTaskApi(workspace) : tasksApi
      const all = await api.list().catch(() => [])
      if (cancelled) return
      const map = {}
      for (const t of Array.isArray(all) ? all : []) {
        if (!t.goal_id) continue
        ;(map[t.goal_id] = map[t.goal_id] || []).push(t)
      }
      setTasksByGoal(map)
    }
    loadTasks()
    return () => { cancelled = true }
  }, [tab, workspace])

  function toggle(id) {
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

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

  // Hierarchy, same shape Assets' own tree already uses: group by
  // parent_id, a goal whose parent didn't pass the filter above floats up
  // to root instead of vanishing — a real match should never be hidden
  // just because its parent got filtered out.
  const childrenMap = useMemo(() => {
    const map = {}
    const ids = new Set(filtered.map(g => g.id))
    for (const g of filtered) {
      const parent = g.parent_id && ids.has(g.parent_id) ? g.parent_id : '_root'
      ;(map[parent] = map[parent] || []).push(g)
    }
    for (const key of Object.keys(map)) {
      map[key].sort((x, y) => x.title.localeCompare(y.title))
    }
    return map
  }, [filtered])
  const roots = childrenMap['_root'] || []

  function openGoal(goal) {
    setOpenGoalId(goal.id)
    setOpenGoalPool(isPoolGoal(goal))
  }

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
        // Each top-level goal gets its OWN card (owner ask, 2026-08-30:
        // "make the each of the top level goals have its own card? so
        // everything isnt all together") — one card per root, its own
        // subtree/linked tasks rendered inside that same card via the
        // normal recursive expand, instead of every root goal sharing one
        // big undifferentiated block.
        <div className="space-y-2">
          {roots.map(goal => (
            <div key={goal.id} className="card p-2 space-y-0.5">
              <GoalRow
                goal={goal}
                depth={0}
                childrenMap={childrenMap}
                tasksByGoal={tasksByGoal}
                expanded={expanded}
                onToggle={toggle}
                onOpen={openGoal}
                onTagClick={t => setTagFilter(t)}
                today={todayStr}
              />
            </div>
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

// Recursive tree row — module level per the MEMORY.md rule (components
// defined inside components remount on every parent render). Mirrors
// Assets.jsx's own AssetRow shape (chevron + indent + hover-free compact
// row), extended with a goal's own linked tasks rendered as leaf rows
// underneath it when expanded.
function GoalRow({ goal, depth, childrenMap, tasksByGoal, expanded, onToggle, onOpen, onTagClick, today }) {
  const children = childrenMap[goal.id] || []
  const linkedTasks = tasksByGoal[goal.id] || []
  const hasKids = children.length > 0 || linkedTasks.length > 0
  const isOpen = expanded.has(goal.id)
  const overdue = goal.due_date && goal.due_date < today && goal.status !== 'done'
  const done = goal.status === 'done'
  const color = catColor(goal.category)
  const pad = ['pl-0', 'pl-5', 'pl-10', 'pl-14', 'pl-20', 'pl-24'][Math.min(depth, 5)]

  return (
    <>
      <div className={`flex items-center gap-2 py-2 px-2 rounded-lg hover:bg-charcoal-50 dark:hover:bg-charcoal-800 transition-colors ${pad} ${overdue ? 'border-l-2 border-red-500/40' : ''}`}>
        <button
          onClick={() => hasKids && onToggle(goal.id)}
          className={`w-6 text-xl leading-none text-charcoal-400 shrink-0 ${hasKids ? 'hover:text-orange-500' : 'opacity-0'}`}
        >
          {isOpen ? '▼' : '▶'}
        </button>
        <button onClick={() => onOpen(goal)} className="flex items-center gap-1.5 flex-wrap flex-1 min-w-0 text-left">
          <span className={`badge ${color} shrink-0`}>{goal.category || 'Uncategorized'}</span>
          <span className={`text-sm font-medium truncate ${done ? 'line-through text-charcoal-400' : ''}`}>
            {goal.title}
          </span>
          {overdue && <span className="text-[10px] text-red-500 font-medium shrink-0">OVERDUE</span>}
          {goal.due_date && <span className="text-[10px] text-charcoal-400 shrink-0">{goal.due_date}</span>}
          {(goal.tags || []).map(t => (
            <span
              key={t}
              onClick={e => { e.stopPropagation(); onTagClick(t) }}
              className="inline-flex items-center bg-orange-100 dark:bg-orange-900/40 text-orange-700 dark:text-orange-300 text-[10px] px-1.5 py-0.5 rounded-full hover:bg-orange-200 dark:hover:bg-orange-900/70 shrink-0"
            >
              {t}
            </span>
          ))}
        </button>
        <button onClick={() => onOpen(goal)} className="shrink-0 text-sm font-semibold text-orange-500">
          {goal.progress?.pct ?? 0}%
        </button>
      </div>
      {isOpen && (
        <>
          {linkedTasks.map(t => (
            <TaskLeafRow key={t.id} task={t} depth={depth + 1} onOpen={() => onOpen(goal)} />
          ))}
          {children.map(c => (
            <GoalRow
              key={c.id}
              goal={c}
              depth={depth + 1}
              childrenMap={childrenMap}
              tasksByGoal={tasksByGoal}
              expanded={expanded}
              onToggle={onToggle}
              onOpen={onOpen}
              onTagClick={onTagClick}
              today={today}
            />
          ))}
        </>
      )}
    </>
  )
}

// A linked task's own row — read-only preview (done state, title, a
// recurring badge). Clicking opens the PARENT goal's own detail view,
// which already has full linked-task actions (unlink, the "counts toward
// this goal's progress" toggle, etc.) — this row is a glance, not a second
// place to edit a task from.
function TaskLeafRow({ task, depth, onOpen }) {
  const pad = ['pl-5', 'pl-10', 'pl-14', 'pl-20', 'pl-24', 'pl-28'][Math.min(depth, 5)]
  const done = task.status === 'done'
  return (
    <button
      onClick={onOpen}
      className={`w-full flex items-center gap-2 py-1.5 px-2 rounded-lg hover:bg-charcoal-50 dark:hover:bg-charcoal-800 transition-colors text-left ${pad}`}
    >
      <span className="w-4 shrink-0" aria-hidden="true" />
      <span className="shrink-0">{done ? '✅' : '⬜'}</span>
      <span className={`text-sm truncate flex-1 min-w-0 ${done ? 'line-through text-charcoal-400' : ''}`}>
        {task.title}
      </span>
      {task.type === 'recurring' && (
        <span className="text-[10px] text-charcoal-400 shrink-0">recurring</span>
      )}
    </button>
  )
}
