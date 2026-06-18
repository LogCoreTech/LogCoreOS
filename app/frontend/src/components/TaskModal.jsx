import { useState, useEffect } from 'react'
import { tasks as tasksApi, priorities as prioritiesApi } from '../lib/api'

const PRIORITIES = ['High', 'Medium', 'Low']
const TYPES = ['todo', 'recurring', 'goal', 'appointment']
const RECURRENCES = ['daily', 'weekly', 'monthly']

export default function TaskModal({ task, categories: propCategories, defaultType, saveApi, onClose, onSave }) {
  const editing = !!task
  const [categories, setCategories] = useState(propCategories || [])
  const [form, setForm] = useState({
    title:      task?.title       || '',
    category:   task?.category    || '',
    priority:   task?.priority    || 'Medium',
    type:       task?.type        || defaultType || 'todo',
    recurrence: task?.recurrence  || null,
    due_date:   task?.due_date    || '',
    due_time:   task?.due_time    || '',
    notes:      task?.notes       || '',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

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
  }, [])

  function set(field, value) {
    setForm(f => ({ ...f, [field]: value }))
  }

  async function submit(e) {
    e.preventDefault()
    if (!form.title.trim()) { setError('Title is required'); return }
    setLoading(true)
    setError('')
    try {
      const payload = {
        ...form,
        due_date:   form.due_date   || null,
        due_time:   (form.due_date && form.due_time) ? form.due_time : null,
        recurrence: form.type === 'recurring' ? (form.recurrence || 'daily') : null,
        notes:      form.notes      || null,
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

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-end md:items-center justify-center p-4">
      <div className="card p-5 w-full max-w-sm max-h-[90vh] overflow-y-auto">
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

          {/* Type */}
          <div>
            <label className="block text-sm font-medium mb-1">Type</label>
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
          </div>

          {/* Recurrence (only if recurring) */}
          {form.type === 'recurring' && (
            <div>
              <label className="block text-sm font-medium mb-1">Repeats</label>
              <select
                value={form.recurrence || 'daily'}
                onChange={e => set('recurrence', e.target.value)}
                className="input"
              >
                {RECURRENCES.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
          )}

          {/* Due date + optional time */}
          <div>
            <label className="block text-sm font-medium mb-1">
              Due Date <span className="text-charcoal-400 font-normal">(optional)</span>
            </label>
            <div className="flex gap-2">
              <input
                type="date"
                value={form.due_date}
                onChange={e => {
                  set('due_date', e.target.value)
                  if (!e.target.value) set('due_time', '')
                }}
                className="input flex-1"
              />
              {form.due_date && (
                <input
                  type="time"
                  value={form.due_time}
                  onChange={e => set('due_time', e.target.value)}
                  placeholder="--:--"
                  className="input w-28"
                  title="Time (optional — for appointments)"
                />
              )}
            </div>
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

          {error && <p className="text-red-500 text-sm">{error}</p>}

          <div className="flex gap-2 pt-1">
            <button type="button" onClick={onClose} className="btn-ghost flex-1">Cancel</button>
            <button type="submit" disabled={loading} className="btn-primary flex-1">
              {loading ? 'Saving…' : editing ? 'Save Changes' : 'Add Task'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
