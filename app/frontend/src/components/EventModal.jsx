import { useState } from 'react'
import { calendar as calendarApi } from '../lib/api'

export const EVENT_COLORS = {
  blue:   '#3b82f6',
  orange: '#f97316',
  green:  '#22c55e',
  red:    '#ef4444',
  purple: '#a855f7',
  teal:   '#14b8a6',
  pink:   '#ec4899',
  yellow: '#eab308',
}

// saveApi: { add, update, remove } — defaults to personal calendar endpoints
// poolSaveApi: same shape, shared pool endpoints — enables "Add to Household/Teams" button
// poolLabel: display name for the shared pool ('Household' or 'Teams')
// isHouseholdEvent: true when the event being edited is already a shared pool event
export default function EventModal({ event, defaultDate, onClose, onSave, saveApi, poolSaveApi, poolLabel = 'Household', isHouseholdEvent }) {
  const editing = !!event
  const api = saveApi || {
    add:    (body)       => calendarApi.addEvent(body),
    update: (id, body)   => calendarApi.updateEvent(id, body),
    remove: (id)         => calendarApi.removeEvent(id),
  }

  const [form, setForm] = useState({
    title:      event?.title      || '',
    start_date: event?.start_date || defaultDate || '',
    end_date:   event?.end_date   || '',
    start_time: event?.start_time || '',
    end_time:   event?.end_time   || '',
    all_day:    event?.all_day    ?? true,
    color:      event?.color      || 'blue',
    notes:      event?.notes      || '',
  })
  const [shareToPool, setShareToPool] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')

  function set(field, value) {
    setForm(f => ({ ...f, [field]: value }))
  }

  function toggleAllDay(checked) {
    setForm(f => ({ ...f, all_day: checked, start_time: '', end_time: '' }))
  }

  async function submit(e) {
    e.preventDefault()
    if (!form.title.trim())  { setError('Title is required'); return }
    if (!form.start_date)    { setError('Start date is required'); return }
    setLoading(true)
    setError('')
    try {
      const payload = {
        ...form,
        end_date:   form.end_date   || null,
        start_time: form.all_day ? null : (form.start_time || null),
        end_time:   form.all_day ? null : (form.end_time   || null),
        notes:      form.notes      || null,
      }

      if (shareToPool && poolSaveApi) {
        if (editing) {
          // Convert personal → shared pool: delete personal, create in pool
          await api.remove(event.id)
          await poolSaveApi.add(payload)
        } else {
          await poolSaveApi.add(payload)
        }
      } else if (editing) {
        await api.update(event.id, payload)
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
    if (!confirm('Delete this event?')) return
    setLoading(true)
    try {
      await api.remove(event.id)
      onSave()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-card p-5 max-w-sm">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <h2 className="font-semibold">{editing ? 'Edit Event' : 'Add Event'}</h2>
            {isHouseholdEvent && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 font-medium">
                🏠 Household
              </span>
            )}
          </div>
          <button onClick={onClose} className="text-charcoal-400 hover:text-charcoal-700 dark:hover:text-charcoal-200">✕</button>
        </div>

        <form onSubmit={submit} className="space-y-4">
          {/* Title */}
          <div>
            <label className="block text-sm font-medium mb-1">Title</label>
            <input
              type="text"
              value={form.title}
              onChange={e => set('title', e.target.value)}
              placeholder="Event name"
              autoFocus
              className="input"
            />
          </div>

          {/* Dates */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium mb-1">Start Date</label>
              <input type="date" value={form.start_date}
                onChange={e => set('start_date', e.target.value)} className="input" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">
                End Date <span className="text-charcoal-400 font-normal">(opt)</span>
              </label>
              <input type="date" value={form.end_date}
                onChange={e => set('end_date', e.target.value)} className="input" />
            </div>
          </div>

          {/* All day toggle */}
          <label className="flex items-center gap-2.5 text-sm cursor-pointer select-none">
            <input
              type="checkbox"
              checked={form.all_day}
              onChange={e => toggleAllDay(e.target.checked)}
              className="w-4 h-4 rounded accent-orange-500"
            />
            All day
          </label>

          {/* Times (hidden when all_day) */}
          {!form.all_day && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium mb-1">Start Time</label>
                <input type="time" value={form.start_time}
                  onChange={e => set('start_time', e.target.value)} className="input" />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">End Time</label>
                <input type="time" value={form.end_time}
                  onChange={e => set('end_time', e.target.value)} className="input" />
              </div>
            </div>
          )}

          {/* Color swatches */}
          <div>
            <label className="block text-sm font-medium mb-2">Color</label>
            <div className="flex gap-2 flex-wrap">
              {Object.entries(EVENT_COLORS).map(([name, hex]) => (
                <button
                  key={name}
                  type="button"
                  onClick={() => set('color', name)}
                  style={{ backgroundColor: hex }}
                  title={name}
                  className={`w-6 h-6 rounded-full transition-all ${
                    form.color === name
                      ? 'ring-2 ring-offset-2 ring-charcoal-800 dark:ring-white scale-110'
                      : 'opacity-75 hover:opacity-100 hover:scale-105'
                  }`}
                />
              ))}
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
              placeholder="Any details…"
              rows={2}
              className="input resize-none"
            />
          </div>

          {/* Add to shared pool toggle — shown when poolSaveApi provided and not already a pool event */}
          {poolSaveApi && !isHouseholdEvent && (
            <button
              type="button"
              onClick={() => setShareToPool(h => !h)}
              className={`w-full flex items-center justify-center gap-2 py-2 rounded-lg border text-sm font-medium transition-colors ${
                shareToPool
                  ? 'bg-blue-500 border-blue-500 text-white'
                  : 'border-charcoal-300 dark:border-charcoal-600 text-charcoal-600 dark:text-charcoal-300 hover:border-blue-400 hover:text-blue-500'
              }`}
            >
              {shareToPool ? `Will be added to ${poolLabel}` : `Add to ${poolLabel}`}
            </button>
          )}

          {error && <p className="text-red-500 text-sm">{error}</p>}

          <div className="flex gap-2 pt-1">
            {editing && (
              <button type="button" onClick={handleDelete} disabled={loading}
                className="px-3 py-2 rounded-lg text-sm font-medium text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors">
                Delete
              </button>
            )}
            <button type="button" onClick={onClose} className="btn-ghost flex-1">Cancel</button>
            <button type="submit" disabled={loading} className="btn-primary flex-1">
              {loading ? 'Saving…' : editing ? 'Save Changes' : shareToPool ? `Add to ${poolLabel}` : 'Add Event'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
