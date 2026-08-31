import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { goals as goalsApi } from './api'
import { tags as tagsApi } from '../../../lib/api'
import TaskModal from '../../../components/TaskModal'
import TaskPicker from '../../../components/TaskPicker'
import TagInput from '../../../components/TagInput'
import MetricPicker from './MetricPicker'
import GoalPicker from './GoalPicker'
import RecurrenceLog from '../../../components/RecurrenceLog'
import HistoryCalendar from '../../../components/HistoryCalendar'
import MetricGraph from '../../../components/MetricGraph'

const METRIC_LOG_LEGEND = [{ colorClass: 'bg-orange-500', label: 'Logged value' }]

function ProgressBar({ pct }) {
  return (
    <div className="h-2 bg-charcoal-200 dark:bg-charcoal-700 rounded-full overflow-hidden">
      <div className="h-full bg-orange-500 rounded-full transition-all duration-500" style={{ width: `${pct}%` }} />
    </div>
  )
}

function emptyForm(parentId) {
  return { title: '', notes: '', category: '', due_date: '', parent_id: parentId || null, metric: null, tags: [] }
}

// Nested modals (the "+ Subgoal"/"+ Task" flows and the delete-choice popup)
// render INSIDE this modal's own DOM subtree, but CSS backdrop-filter (used
// by .card, which .modal-card applies) creates a new containing block for
// position:fixed descendants — so without a portal they'd size/clip against
// THIS modal's own box instead of the real viewport. Mirrors the existing
// createPortal precedent in components/assetDisplay.jsx's photo viewer, for
// the exact same reason. AssetModal.jsx's own nested TaskModal had the
// identical latent bug, fixed in the same pass (2026-08-29).
function Portal({ children }) {
  return createPortal(children, document.body)
}

export async function poolTaskApi(workspace) {
  if (workspace === 'business') {
    const { team } = await import('../../team/frontend/api')
    return team
  }
  const { shared } = await import('../../household/frontend/api')
  return shared
}

/**
 * Goal detail — drill-down modal. Mirrors AssetModal/AssetView's own
 * pattern: subgoals + linked tasks listed together underneath, clicking a
 * subgoal reopens THIS SAME modal on it (via onOpenGoal, handled by the
 * parent Goals.jsx re-setting goalId) rather than nesting DOM.
 *
 * Props: goalId (null = create mode), categories, workspace, onClose,
 * onChanged, onOpenGoal(goalId), parentId (create-a-subgoal preset), pool
 */
export default function GoalModal({ goalId, categories, workspace, onClose, onChanged, onOpenGoal, parentId, pool = false }) {
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(!!goalId)
  const [editing, setEditing] = useState(!goalId)
  const [form, setForm] = useState(emptyForm(parentId))
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [tagSuggestions, setTagSuggestions] = useState([])

  const [showSubgoalCreate, setShowSubgoalCreate] = useState(false)
  const [showSubgoalLink, setShowSubgoalLink] = useState(false)
  const [linkGoalId, setLinkGoalId] = useState(null)
  const [showTaskCreate, setShowTaskCreate] = useState(false)
  const [showTaskLink, setShowTaskLink] = useState(false)
  const [linkTaskId, setLinkTaskId] = useState(null)
  const [showDelete, setShowDelete] = useState(false)
  const [deleteCascade, setDeleteCascade] = useState(false)
  const [deleteLinkedTasks, setDeleteLinkedTasks] = useState(false)
  const [manualValue, setManualValue] = useState('')
  const [expandedHistory, setExpandedHistory] = useState(new Set())
  const [metricView, setMetricView] = useState('graph')

  function toggleHistory(taskId) {
    setExpandedHistory(prev => {
      const next = new Set(prev)
      if (next.has(taskId)) next.delete(taskId)
      else next.add(taskId)
      return next
    })
  }

  async function load() {
    if (!goalId) return
    setLoading(true)
    try {
      const d = await goalsApi.get(goalId, pool)
      setDetail(d)
      setForm({
        title: d.goal.title,
        notes: d.goal.notes || '',
        category: d.goal.category || '',
        due_date: d.goal.due_date || '',
        parent_id: d.goal.parent_id,
        metric: d.goal.metric || null,
        tags: d.goal.tags || [],
      })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [goalId]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    tagsApi.list(pool).then(r => setTagSuggestions(r.tags || [])).catch(() => setTagSuggestions([]))
  }, [pool])

  async function save(e) {
    e?.preventDefault()
    if (!form.title.trim()) { setError('Title is required'); return }
    setSaving(true)
    setError('')
    try {
      const payload = {
        title: form.title,
        notes: form.notes || null,
        category: form.category || '',
        due_date: form.due_date || null,
        parent_id: form.parent_id || null,
        metric: form.metric,
        tags: form.tags,
        pool,
      }
      if (goalId) {
        await goalsApi.update(goalId, payload)
      } else {
        const created = await goalsApi.create(payload)
        onChanged()
        onOpenGoal(created.id)
        return
      }
      setEditing(false)
      await load()
      onChanged()
    } catch (err) {
      setError(err.message || 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  async function toggleDone() {
    await goalsApi.update(goalId, { status: detail.goal.status === 'done' ? 'pending' : 'done', pool })
    await load()
    onChanged()
  }

  async function logManual() {
    if (manualValue === '') return
    await goalsApi.logMetric(goalId, Number(manualValue), null, pool)
    setManualValue('')
    await load()
    onChanged()
  }

  async function linkExistingTask() {
    if (!linkTaskId) return
    const api = pool ? await poolTaskApi(workspace) : (await import('../../tasks/frontend/api')).tasks
    await api.update(linkTaskId, { goal_id: goalId })
    setShowTaskLink(false)
    setLinkTaskId(null)
    await load()
    onChanged()
  }

  async function unlinkTask(taskId) {
    const api = pool ? await poolTaskApi(workspace) : (await import('../../tasks/frontend/api')).tasks
    await api.update(taskId, { goal_id: null })
    await load()
    onChanged()
  }

  async function toggleTaskCounts(taskId, current) {
    const api = pool ? await poolTaskApi(workspace) : (await import('../../tasks/frontend/api')).tasks
    await api.update(taskId, { counts_toward_goal: !current })
    await load()
    onChanged()
  }

  async function linkExistingGoal() {
    if (!linkGoalId) return
    await goalsApi.update(linkGoalId, { parent_id: goalId, pool })
    setShowSubgoalLink(false)
    setLinkGoalId(null)
    await load()
    onChanged()
  }

  async function doDelete() {
    await goalsApi.remove(goalId, { pool, cascade: deleteCascade, deleteLinkedTasks })
    setShowDelete(false)
    onChanged()
    onClose()
  }

  const goal = detail?.goal
  const progress = detail?.progress
  const hasMetric = !!goal?.metric

  return (
    <Portal>
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal-card max-w-lg max-h-[85vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold">{goalId ? (editing ? 'Edit Goal' : goal?.title) : 'New Goal'}</h2>
            <button onClick={onClose} className="text-charcoal-400 hover:text-charcoal-600">✕</button>
          </div>

          {loading ? (
            <p className="text-sm text-charcoal-400">Loading…</p>
          ) : editing ? (
            <form onSubmit={save} className="space-y-3">
              <div>
                <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Title</label>
                <input className="input w-full" value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} autoFocus />
              </div>
              <div>
                <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Category</label>
                <select className="input w-full" value={form.category} onChange={e => setForm({ ...form, category: e.target.value })}>
                  <option value="">—</option>
                  {categories.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Due date (optional)</label>
                <input type="date" className="input w-full" value={form.due_date} onChange={e => setForm({ ...form, due_date: e.target.value })} />
              </div>
              <div>
                <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Tags</label>
                <TagInput value={form.tags} onChange={t => setForm({ ...form, tags: t })} suggestions={tagSuggestions} placeholder="Add a tag…" />
              </div>
              <div>
                <label className="text-xs text-charcoal-500 dark:text-charcoal-400">Notes</label>
                <textarea className="input w-full" rows={3} value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} />
              </div>
              <MetricPicker value={form.metric} onChange={m => setForm({ ...form, metric: m })} />
              {error && <p className="text-sm text-red-500">{error}</p>}
              <div className="flex justify-end gap-2 pt-2">
                {detail && <button type="button" className="btn-ghost" onClick={() => setEditing(false)}>Cancel</button>}
                <button type="submit" className="btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
              </div>
            </form>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center gap-2 flex-wrap">
                {goal.category && <span className="badge bg-charcoal-100 dark:bg-charcoal-700 text-charcoal-600 dark:text-charcoal-300">{goal.category}</span>}
                {goal.due_date && <span className="text-xs text-charcoal-500 dark:text-charcoal-400">Target: {goal.due_date}</span>}
              </div>

              {goal.tags?.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {goal.tags.map(t => (
                    <span key={t} className="inline-flex items-center bg-orange-100 dark:bg-orange-900/40 text-orange-700 dark:text-orange-300 text-xs px-2 py-0.5 rounded-full">
                      {t}
                    </span>
                  ))}
                </div>
              )}

              {/* Progress */}
              <div className="bg-charcoal-50 dark:bg-charcoal-800 rounded-lg p-3">
                <div className="flex items-center justify-between text-sm mb-2">
                  <span className="font-medium capitalize">{progress.source === 'metric' ? 'Metric progress' : progress.source === 'rollup' ? 'Combined progress' : 'Progress'}</span>
                  <span className="text-orange-500 font-semibold">{progress.pct}%</span>
                </div>
                <ProgressBar pct={progress.pct} />
                {detail.on_pace && (
                  <p className={`text-xs mt-2 font-medium ${detail.on_pace === 'on_pace' ? 'text-green-600' : 'text-amber-600'}`}>
                    {detail.on_pace === 'on_pace' ? '✓ On pace to hit your target' : '⚠ Behind pace to hit your target'}
                  </p>
                )}
                {goal.metric?.provider === 'manual' && (
                  <>
                    <div className="flex gap-2 mt-3">
                      <input
                        type="number"
                        className="input flex-1 !py-1 text-sm"
                        placeholder="Log a new value…"
                        value={manualValue}
                        onChange={e => setManualValue(e.target.value)}
                      />
                      <button className="btn-ghost text-xs px-2" onClick={logManual}>Log</button>
                    </div>
                    <div className="mt-3">
                      <div className="flex justify-center mb-2">
                        <div className="inline-flex bg-charcoal-100 dark:bg-charcoal-700 rounded-full p-0.5 text-[11px]">
                          {['graph', 'calendar'].map(v => (
                            <button
                              key={v}
                              type="button"
                              onClick={() => setMetricView(v)}
                              className={`px-2.5 py-0.5 rounded-full font-medium capitalize transition-colors ${
                                metricView === v
                                  ? 'bg-white dark:bg-charcoal-600 text-charcoal-900 dark:text-gray-100 shadow-sm'
                                  : 'text-charcoal-500 dark:text-charcoal-400'
                              }`}
                            >
                              {v}
                            </button>
                          ))}
                        </div>
                      </div>
                      {metricView === 'graph' ? (
                        <MetricGraph
                          entries={goal.metric.history || []}
                          target={goal.metric.config?.target_value}
                        />
                      ) : (
                        <HistoryCalendar
                          entriesByDate={Object.fromEntries(
                            (goal.metric.history || []).map(e => [
                              e.date,
                              { colorClass: 'bg-orange-500', label: String(e.value) },
                            ])
                          )}
                          legend={METRIC_LOG_LEGEND}
                        />
                      )}
                    </div>
                  </>
                )}
                {!hasMetric && (
                  <label className="flex items-center gap-2 text-sm mt-3 cursor-pointer">
                    <input type="checkbox" checked={goal.status === 'done'} onChange={toggleDone} />
                    Mark done manually
                  </label>
                )}
              </div>

              {goal.notes && <p className="text-sm text-charcoal-600 dark:text-charcoal-300">{goal.notes}</p>}

              {/* Subgoals */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-charcoal-400">
                    Subgoals ({detail.subgoals.length})
                  </h3>
                  <div className="flex gap-2">
                    <button className="text-xs text-orange-500 hover:underline" onClick={() => setShowSubgoalLink(true)}>Link existing</button>
                    <button className="text-xs text-orange-500 hover:underline" onClick={() => setShowSubgoalCreate(true)}>+ Subgoal</button>
                  </div>
                </div>
                {detail.subgoals.length === 0 ? (
                  <p className="text-xs text-charcoal-400">No subgoals.</p>
                ) : (
                  <div className="space-y-1.5">
                    {detail.subgoals.map(sg => (
                      <button key={sg.id} onClick={() => onOpenGoal(sg.id)} className="w-full text-left text-sm flex items-center justify-between p-2 rounded-lg border border-charcoal-200 dark:border-charcoal-700 hover:border-orange-400">
                        <span className={sg.status === 'done' ? 'line-through text-charcoal-400' : ''}>{sg.title}</span>
                        <span className="text-xs text-charcoal-400 shrink-0 ml-2">›</span>
                      </button>
                    ))}
                  </div>
                )}
                {showSubgoalLink && (
                  <div className="flex gap-2 items-end mt-2">
                    <div className="flex-1"><GoalPicker label="Pick a goal to move under this one" value={linkGoalId} onChange={setLinkGoalId} excludeId={goalId} pool={pool} /></div>
                    <button className="btn-ghost text-xs px-2 py-2" onClick={linkExistingGoal}>Link</button>
                    <button className="btn-ghost text-xs px-2 py-2" onClick={() => { setShowSubgoalLink(false); setLinkGoalId(null) }}>✕</button>
                  </div>
                )}
              </div>

              {/* Linked tasks */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-charcoal-400">
                    Linked tasks ({detail.linked_tasks.length})
                  </h3>
                  <div className="flex gap-2">
                    <button className="text-xs text-orange-500 hover:underline" onClick={() => setShowTaskLink(true)}>Link existing</button>
                    <button className="text-xs text-orange-500 hover:underline" onClick={() => setShowTaskCreate(true)}>+ Task</button>
                  </div>
                </div>
                {detail.linked_tasks.length === 0 ? (
                  <p className="text-xs text-charcoal-400">No linked tasks.</p>
                ) : (
                  <ul className="space-y-1.5">
                    {detail.linked_tasks.map(t => (
                      <li key={t.id} className="text-sm p-2 rounded-lg border border-charcoal-200 dark:border-charcoal-700">
                        <div className="flex items-center justify-between">
                          <span className={t.status === 'done' ? 'line-through text-charcoal-400' : ''}>
                            {t.title}{t.type === 'recurring' && <span className="text-xs text-charcoal-400 ml-1">(recurring — {t.recurring_rate ?? 0}% / 30d)</span>}
                          </span>
                          <button onClick={() => unlinkTask(t.id)} className="text-xs text-charcoal-400 hover:text-red-500 shrink-0 ml-2">Unlink</button>
                        </div>
                        {t.type === 'recurring' && (
                          <>
                            <label className="flex items-center gap-1.5 mt-1 text-xs text-charcoal-400">
                              <input
                                type="checkbox"
                                checked={t.counts_toward_goal !== false}
                                onChange={() => toggleTaskCounts(t.id, t.counts_toward_goal !== false)}
                              />
                              Counts toward this goal&apos;s progress
                            </label>
                            <button
                              type="button"
                              onClick={() => toggleHistory(t.id)}
                              className="text-[11px] text-orange-500 hover:underline mt-1"
                            >
                              {expandedHistory.has(t.id) ? '▾ Hide history' : '▸ Show history'}
                            </button>
                            {expandedHistory.has(t.id) && (
                              <div className="mt-2">
                                <RecurrenceLog completionLog={t.completion_log || []} />
                              </div>
                            )}
                          </>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {showTaskLink && (
                <TaskLinkPicker pool={pool} workspace={workspace} value={linkTaskId} onChange={setLinkTaskId} onLink={linkExistingTask} onCancel={() => { setShowTaskLink(false); setLinkTaskId(null) }} />
              )}

              <div className="flex justify-between pt-2 border-t border-charcoal-100 dark:border-charcoal-800">
                <button onClick={() => setShowDelete(true)} className="text-sm text-red-500 hover:text-red-600">Delete</button>
                <button onClick={() => setEditing(true)} className="btn-ghost text-sm">Edit</button>
              </div>
            </div>
          )}

          {showSubgoalCreate && (
            <GoalModal
              goalId={null}
              parentId={goalId}
              pool={pool}
              workspace={workspace}
              categories={categories}
              onClose={() => setShowSubgoalCreate(false)}
              onChanged={() => { onChanged(); load() }}
              onOpenGoal={id => { setShowSubgoalCreate(false); onOpenGoal(id) }}
            />
          )}

          {showTaskCreate && (
            <PoolAwareTaskCreateModal
              pool={pool}
              workspace={workspace}
              goalId={goalId}
              categories={categories}
              onClose={() => setShowTaskCreate(false)}
              onSave={() => { setShowTaskCreate(false); load(); onChanged() }}
            />
          )}

          {showDelete && (
            <Portal>
              <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
                <div className="card p-5 w-full max-w-sm space-y-3">
                  <h2 className="font-semibold">Delete Goal?</h2>
                  {detail.subgoals.length > 0 && (
                    <label className="flex items-start gap-2 text-sm">
                      <input type="checkbox" checked={deleteCascade} onChange={e => setDeleteCascade(e.target.checked)} className="mt-0.5" />
                      <span>Also delete its {detail.subgoals.length} subgoal{detail.subgoals.length === 1 ? '' : 's'} (otherwise they move up a level)</span>
                    </label>
                  )}
                  {detail.linked_tasks.length > 0 && (
                    <label className="flex items-start gap-2 text-sm">
                      <input type="checkbox" checked={deleteLinkedTasks} onChange={e => setDeleteLinkedTasks(e.target.checked)} className="mt-0.5" />
                      <span>Also delete its {detail.linked_tasks.length} linked task{detail.linked_tasks.length === 1 ? '' : 's'} (otherwise they&apos;re just unlinked)</span>
                    </label>
                  )}
                  <div className="flex gap-2 pt-2">
                    <button onClick={() => setShowDelete(false)} className="btn-ghost flex-1">Cancel</button>
                    <button onClick={doDelete} className="flex-1 py-2 rounded-lg bg-red-500 hover:bg-red-600 text-white text-sm font-medium transition-colors">Delete</button>
                  </div>
                </div>
              </div>
            </Portal>
          )}
        </div>
      </div>
    </Portal>
  )
}

// Resolves the correct task-picker source (personal vs. pool) before
// rendering — TaskPicker's listFn needs a real function reference up front,
// not a promise, so this small wrapper awaits the dynamic import once.
function TaskLinkPicker({ pool, workspace, value, onChange, onLink, onCancel }) {
  const [listFn, setListFn] = useState(null)

  useEffect(() => {
    if (pool) {
      poolTaskApi(workspace).then(api => setListFn(() => api.list))
    } else {
      import('../../tasks/frontend/api').then(({ tasks }) => setListFn(() => tasks.list))
    }
  }, [pool, workspace])

  return (
    <div className="flex gap-2 items-end">
      <div className="flex-1">
        {listFn && <TaskPicker label="Pick a task" value={value} onChange={onChange} listFn={listFn} />}
      </div>
      <button className="btn-ghost text-xs px-2 py-2" onClick={onLink}>Link</button>
      <button className="btn-ghost text-xs px-2 py-2" onClick={onCancel}>✕</button>
    </div>
  )
}

// Same "resolve the async pool client before rendering" need as
// TaskLinkPicker above, applied to TaskModal's saveApi prop instead of
// TaskPicker's listFn.
function PoolAwareTaskCreateModal({ pool, workspace, goalId, categories, onClose, onSave }) {
  const [saveApi, setSaveApi] = useState(undefined)
  const [ready, setReady] = useState(!pool)

  useEffect(() => {
    if (!pool) return
    poolTaskApi(workspace).then(api => { setSaveApi(() => api); setReady(true) })
  }, [pool, workspace])

  if (!ready) return null
  return (
    <Portal>
      <TaskModal
        defaultGoalId={goalId}
        categories={categories}
        saveApi={saveApi}
        onClose={onClose}
        onSave={onSave}
      />
    </Portal>
  )
}
