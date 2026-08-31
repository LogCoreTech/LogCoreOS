import { useState, useEffect } from 'react'
import { tasks as tasksApi } from '../module_packages/tasks/frontend/api'
import { priorities as prioritiesApi, tags as tagsApi } from '../lib/api'
import TagInput from './TagInput'
import RecurrencePicker, { describeRecurrence } from './RecurrencePicker'
import TaskView from './TaskView'

const PRIORITIES = ['High', 'Medium', 'Low']
const TYPES = ['todo', 'recurring', 'appointment']

export default function TaskModal({ task, categories: propCategories, defaultType, saveApi, users, assets, defaultAssetId, defaultGoalId, onClose, onSave, onDelete }) {
  const editing = !!task
  // Assigned pool tasks (household/team) live in another store — open them view-only.
  // Tasks page tags them with `_source`; Calendar tags them with `_household`.
  const readOnly = editing && (task._source === 'household' || task._source === 'team' || task._household === true)
  // Read-first: an existing task opens in view mode (more room to show a
  // recurring task's real history — see TaskView), same pattern Assets/Goals
  // already use (AssetModal/AssetView, GoalModal's own `editing` state). A
  // readOnly task always starts (and stays) in view mode simply because
  // TaskView never renders its Edit button when canEdit is false — no
  // separate mode-forcing guard needed.
  const [mode, setMode] = useState(editing ? 'view' : 'edit')
  const [categories, setCategories] = useState(propCategories || [])
  const [form, setForm] = useState({
    title:       task?.title       || '',
    category:    task?.category    || '',
    priority:    task?.priority    || 'Medium',
    type:        task?.type        || defaultType || 'todo',
    recurrence:  task?.recurrence  || null,
    due_date:    task?.due_date    || '',
    due_time:    task?.due_time    || '',
    notes:       task?.notes       || '',
    assigned_to: task?.assigned_to || '',
    asset_id:    task?.asset_id    || defaultAssetId || '',
    goal_id:     task?.goal_id     || defaultGoalId || '',
    tags:        task?.tags        || [],
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [tagSuggestions, setTagSuggestions] = useState([])

  // A pool context is identified by a saveApi override (household's/team's
  // own client) being passed in — mirrors how goal_id linking already tells
  // pool vs. personal apart elsewhere in this same round's changes.
  useEffect(() => {
    tagsApi.list(!!saveApi).then(r => setTagSuggestions(r.tags || [])).catch(() => setTagSuggestions([]))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Mount-only: pick an initial category once. Deliberately not re-run on
  // form.category/propCategories changes — both are written by this same
  // effect (via setForm/setCategories), so tracking them would risk
  // re-fetching priorities.get() on every unrelated re-render.
  useEffect(() => {
    if (!propCategories?.length) {
      prioritiesApi.get().then(p => {
        setCategories(p.order || [])
        if (!form.category && p.order?.length) {
          setForm(f => ({ ...f, category: p.order[0] }))
        }
      })
    } else if (!form.category && propCategories.length) {
      setForm(f => ({ ...f, category: propCategories[0] }))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function set(field, value) {
    setForm(f => ({ ...f, [field]: value }))
  }

  // Derive 12-hour display parts from stored 24-hour value
  const _tp    = (form.due_time || '').split(':')
  const _h24   = _tp[0] ? parseInt(_tp[0], 10) : null
  const tHour  = _h24 === null ? '' : _h24 === 0 ? '12' : _h24 > 12 ? String(_h24 - 12) : String(_h24)
  const tMin   = _tp[1] || ''
  const tAmpm  = _h24 === null ? '' : _h24 < 12 ? 'AM' : 'PM'

  function applyTime(h, m, ap) {
    if (!h) { set('due_time', ''); return }
    const h12 = parseInt(h, 10)
    const period = ap || 'AM'
    const h24out = period === 'AM' ? (h12 === 12 ? 0 : h12) : (h12 === 12 ? 12 : h12 + 12)
    set('due_time', `${String(h24out).padStart(2, '0')}:${m || '00'}`)
  }

  async function submit(e) {
    e.preventDefault()
    if (!form.title.trim()) { setError('Title is required'); return }
    setLoading(true)
    setError('')
    try {
      const payload = {
        ...form,
        due_date:    form.due_date   || null,
        due_time:    (form.due_date && form.due_time) ? form.due_time : null,
        recurrence:  form.type === 'recurring' ? form.recurrence : null,
        notes:       form.notes      || null,
        assigned_to: form.assigned_to || null,
        asset_id:    form.asset_id   || null,
        goal_id:     form.goal_id    || null,
        tags:        form.tags,
      }
      const api = saveApi || tasksApi
      if (editing) {
        await api.update(task.id, payload)
      } else {
        await api.add(payload)
      }
      onSave()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleDelete() {
    if (!confirm('Delete this task?')) return
    setLoading(true)
    try {
      const api = saveApi || tasksApi
      await api.remove(task.id)
      onDelete?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  // Cancel returns to the view for an existing task (matching
  // AssetModal.jsx's own handleCancel exactly); a brand-new task has no
  // view to return to, so it just closes.
  function handleCancel() {
    if (editing) setMode('view')
    else onClose()
  }

  if (mode === 'view' && task) {
    return (
      <TaskView
        task={task}
        canEdit={!readOnly}
        saveApi={saveApi}
        onEdit={() => setMode('edit')}
        onClose={onClose}
        onDelete={onDelete ? handleDelete : undefined}
        onSave={onSave}
      />
    )
  }

  return (
    <div className="modal-overlay">
      <div className="modal-card p-5 max-w-sm">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold">{editing ? 'Edit Task' : 'Add Task'}</h2>
          <button onClick={onClose} className="text-charcoal-400 hover:text-charcoal-700 dark:hover:text-charcoal-200">✕</button>
        </div>

        <form onSubmit={submit} className="space-y-4">
          {/* Title */}
          <div>
            <label className="block text-sm font-medium mb-1">Task</label>
            <input
              type="text"
              value={form.title}
              onChange={e => set('title', e.target.value)}
              placeholder="What needs to be done?"
              autoFocus
              className="input"
            />
          </div>

          {/* Category + Priority row */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium mb-1">Category</label>
              <select value={form.category} onChange={e => set('category', e.target.value)} className="input">
                {categories.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Priority</label>
              <select value={form.priority} onChange={e => set('priority', e.target.value)} className="input">
                {PRIORITIES.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
          </div>

          {/* Type — editable only at creation; already excluded from
              TaskUpdateBase server-side, so editing an existing task shows
              it as static text instead of a control that would silently
              no-op on save. */}
          <div>
            <label className="block text-sm font-medium mb-1">Type</label>
            {editing ? (
              <p className="input !bg-charcoal-50 dark:!bg-charcoal-800 text-charcoal-600 dark:text-charcoal-300 capitalize">
                {form.type}
              </p>
            ) : (
              <div className="flex gap-1">
                {TYPES.map(t => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => set('type', t)}
                    className={`flex-1 py-1.5 rounded-md text-xs font-medium capitalize transition-colors ${
                      form.type === t
                        ? 'bg-orange-500 text-white'
                        : 'bg-charcoal-100 dark:bg-charcoal-700 text-charcoal-600 dark:text-charcoal-300'
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Recurrence — create-only server-side; an existing recurring
              task's real pattern + history already shows in the task's own
              view (TaskView/RecurrenceLog), so edit mode just notes it. */}
          {form.type === 'recurring' && (
            <div>
              <label className="block text-sm font-medium mb-1">Repeats</label>
              {editing ? (
                <p className="input !bg-charcoal-50 dark:!bg-charcoal-800 text-charcoal-600 dark:text-charcoal-300">
                  {describeRecurrence(task.recurrence)} — set at creation, see the task view for history
                </p>
              ) : (
                <RecurrencePicker
                  value={form.recurrence}
                  onChange={r => set('recurrence', r)}
                  dueDate={form.due_date}
                />
              )}
            </div>
          )}

          {/* Due date + optional time */}
          <div>
            <label className="block text-sm font-medium mb-1">
              Due Date{' '}
              <span className="text-charcoal-400 font-normal">
                {!editing && form.type === 'recurring' && !form.due_date
                  ? '(starts from the pattern above if left blank)'
                  : '(optional)'}
              </span>
            </label>
            <div className="space-y-2">
              <input
                type="date"
                value={form.due_date}
                onChange={e => {
                  set('due_date', e.target.value)
                  if (!e.target.value) set('due_time', '')
                }}
                className="input"
              />
              {form.due_date && (
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-charcoal-500 dark:text-charcoal-400 shrink-0 w-8">Time</span>
                  <select
                    value={tHour}
                    onChange={e => applyTime(e.target.value, tMin, tAmpm)}
                    className="input !w-14 !px-1.5 text-center"
                  >
                    <option value="">--</option>
                    {['1','2','3','4','5','6','7','8','9','10','11','12'].map(h => (
                      <option key={h} value={h}>{h}</option>
                    ))}
                  </select>
                  <span className="text-charcoal-400 font-bold shrink-0">:</span>
                  <select
                    value={tMin}
                    onChange={e => applyTime(tHour, e.target.value, tAmpm)}
                    className="input !w-14 !px-1.5 text-center"
                  >
                    <option value="">--</option>
                    {Array.from({ length: 12 }, (_, i) => String(i * 5).padStart(2, '0')).map(m => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                  <select
                    value={tAmpm}
                    onChange={e => applyTime(tHour, tMin, e.target.value)}
                    className="input !w-16 !px-1.5 text-center"
                  >
                    <option value="">--</option>
                    <option value="AM">AM</option>
                    <option value="PM">PM</option>
                  </select>
                  {form.due_time && (
                    <button
                      type="button"
                      onClick={() => set('due_time', '')}
                      className="text-charcoal-400 hover:text-red-500 transition-colors ml-0.5 text-sm"
                      title="Clear time"
                    >
                      ✕
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Tags */}
          <div>
            <label className="block text-sm font-medium mb-1">
              Tags <span className="text-charcoal-400 font-normal">(optional)</span>
            </label>
            <TagInput value={form.tags} onChange={t => set('tags', t)} suggestions={tagSuggestions} placeholder="Add a tag…" />
          </div>

          {/* Notes */}
          <div>
            <label className="block text-sm font-medium mb-1">
              Notes <span className="text-charcoal-400 font-normal">(optional)</span>
            </label>
            <textarea
              value={form.notes}
              onChange={e => set('notes', e.target.value)}
              placeholder="Any context…"
              rows={2}
              className="input resize-none"
            />
          </div>

          {/* Assign to — only shown in household context when users list provided */}
          {users && users.length > 0 && (
            <div>
              <label className="block text-sm font-medium mb-1">Assign to</label>
              <select value={form.assigned_to} onChange={e => set('assigned_to', e.target.value)} className="input">
                <option value="">Unassigned</option>
                {users.map(u => <option key={u.name} value={u.name}>{u.name}</option>)}
              </select>
            </div>
          )}

          {/* Linked asset — only shown when an assets list is provided (assets module on) */}
          {assets && assets.length > 0 && (
            <div>
              <label className="block text-sm font-medium mb-1">
                Linked asset <span className="text-charcoal-400 font-normal">(optional)</span>
              </label>
              <select value={form.asset_id} onChange={e => set('asset_id', e.target.value)} className="input">
                <option value="">None</option>
                {assets.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </div>
          )}

          {error && <p className="text-red-500 text-sm">{error}</p>}

          <div className="flex gap-2 pt-1">
            {editing && onDelete && (
              <button type="button" onClick={handleDelete} disabled={loading}
                className="px-3 py-2 rounded-lg text-sm font-medium text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors">
                Delete
              </button>
            )}
            <button type="button" onClick={handleCancel} className="btn-ghost flex-1">Cancel</button>
            <button type="submit" disabled={loading} className="btn-primary flex-1">
              {loading ? 'Saving…' : editing ? 'Save Changes' : 'Add Task'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
