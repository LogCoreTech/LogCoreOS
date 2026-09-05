import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { tasks as tasksApi } from '../module_packages/tasks/frontend/api'
import { catColor } from '../lib/constants'
import { deepLinkUrl } from '../lib/deepLinks'
import RecurrenceLog from './RecurrenceLog'
import { describeRecurrence } from './RecurrencePicker'
import ConfirmDialog from './ConfirmDialog'
import useEscapeToClose from '../lib/useEscapeToClose'
import useFocusTrap from '../lib/useFocusTrap'

const PRIORITY_COLOR = {
  High:   'bg-orange-500 text-white',
  Medium: 'bg-yellow-400 text-charcoal-900',
  Low:    'bg-charcoal-300 dark:bg-charcoal-600 text-charcoal-700 dark:text-charcoal-200',
}

function formatDueTime(due_time) {
  if (!due_time) return ''
  const [h, m] = due_time.split(':').map(Number)
  const period = h < 12 ? 'AM' : 'PM'
  const h12 = h % 12 === 0 ? 12 : h % 12
  return ` at ${h12}:${String(m).padStart(2, '0')} ${period}`
}

// Read-first display for an existing task — mirrors the Assets/Goals
// read-first pattern (AssetModal/AssetView, GoalModal's own `editing` state)
// so there's more room to show a recurring task's real history than the
// compact edit form allows. No <form> here — plain divs, imperative
// handlers, same shape as AssetView.jsx.
export default function TaskView({ task, canEdit, saveApi, onEdit, onClose, onDelete, onSave }) {
  const navigate = useNavigate()
  const [goalTitle, setGoalTitle] = useState(null)
  const [assetTitle, setAssetTitle] = useState(null)
  const [loading, setLoading] = useState(false)
  const [confirmState, setConfirmState] = useState(null) // { title, message, danger, confirmLabel, onConfirm }
  const cardRef = useRef(null)

  useEscapeToClose(onClose)
  useFocusTrap(cardRef)

  // Pool context is identified by a saveApi override, same convention
  // TaskModal.jsx already uses for tag-suggestion lookups.
  const pool = !!saveApi

  useEffect(() => {
    if (task.goal_id) {
      import('../module_packages/goals/frontend/api')
        .then(({ goals }) => goals.get(task.goal_id, pool))
        .then(d => setGoalTitle(d.goal.title))
        .catch(() => {})
    }
    if (task.asset_id) {
      import('../module_packages/assets/frontend/api')
        .then(({ assets }) => assets.get(task.asset_id))
        .then(a => setAssetTitle(a.name))
        .catch(() => {})
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task.goal_id, task.asset_id])

  async function toggleComplete() {
    setLoading(true)
    try {
      const api = saveApi || tasksApi
      await api.update(task.id, { status: task.status === 'done' ? 'pending' : 'done' })
      onSave()
    } finally {
      setLoading(false)
    }
  }

  // Item #23, 2026-09-04 UX Polish Batch — copies everything except
  // completion/streak state (a fresh copy is always pending, streak-free).
  // `saveApi` already scopes this to the same store (pool stays pool,
  // personal stays personal) since it's the exact client this view itself
  // reads/writes through.
  async function handleDuplicate() {
    setLoading(true)
    try {
      const api = saveApi || tasksApi
      await api.add({
        title: `${task.title} (copy)`,
        category: task.category,
        priority: task.priority,
        type: task.type,
        recurrence: task.recurrence || null,
        due_date: task.due_date || null,
        due_time: task.due_time || null,
        notes: task.notes || null,
        assigned_to: task.assigned_to || null,
        asset_id: task.asset_id || null,
        goal_id: task.goal_id || null,
        tags: task.tags || [],
      })
      onSave()
    } finally {
      setLoading(false)
    }
  }

  function handleDelete() {
    // Item #29, 2026-09-04 UX Polish Batch — context-aware warning: the
    // owner's own named example (a streak). Only the highest-value curated
    // sites got this, not every confirm() in the app.
    const message = task.streak_count > 0
      ? `Delete this task? You'll lose its ${task.streak_count}-day streak.`
      : 'Delete this task?'
    setConfirmState({
      title: 'Delete task',
      message,
      confirmLabel: 'Delete',
      danger: true,
      onConfirm: async () => {
        setConfirmState(null)
        setLoading(true)
        try {
          const api = saveApi || tasksApi
          await api.remove(task.id)
          onDelete()
        } finally {
          setLoading(false)
        }
      },
    })
  }

  return (
    <div className="modal-overlay">
      <div ref={cardRef} className="modal-card p-5 max-w-sm max-h-[85vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold">{task.title}</h2>
          <button onClick={onClose} aria-label="Close" className="text-charcoal-400 hover:text-charcoal-700 dark:hover:text-charcoal-200">✕</button>
        </div>

        <div className="space-y-4">
          <div className="flex items-center gap-2 flex-wrap">
            {task.category && <span className={`badge ${catColor(task.category)}`}>{task.category}</span>}
            {task.priority && (
              <span className={`badge ${PRIORITY_COLOR[task.priority] || ''}`}>{task.priority}</span>
            )}
            {task.streak_count > 0 && (
              <span className="text-xs text-orange-500 font-medium">🔥 {task.streak_count}</span>
            )}
          </div>

          {task.due_date && (
            <p className="text-sm text-charcoal-600 dark:text-charcoal-300">
              Due {task.due_date}{formatDueTime(task.due_time)}
            </p>
          )}

          {task.type === 'recurring' && (
            <div>
              <p className="text-sm text-charcoal-600 dark:text-charcoal-300 mb-2">
                {describeRecurrence(task.recurrence)}
              </p>
              <RecurrenceLog completionLog={task.completion_log || []} />
            </div>
          )}

          {task.tags?.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {task.tags.map(t => (
                <span key={t} className="inline-flex items-center bg-orange-100 dark:bg-orange-900/40 text-orange-700 dark:text-orange-300 text-xs px-2 py-0.5 rounded-full">
                  {t}
                </span>
              ))}
            </div>
          )}

          {task.notes && <p className="text-sm text-charcoal-600 dark:text-charcoal-300 whitespace-pre-wrap">{task.notes}</p>}

          {task.assigned_to && (
            <p className="text-xs text-charcoal-400">Assigned to {task.assigned_to}</p>
          )}

          {(goalTitle || assetTitle) && (
            <div className="flex flex-wrap gap-2">
              {goalTitle && (
                <button
                  type="button"
                  onClick={() => navigate(deepLinkUrl('goals', task.goal_id))}
                  className="text-xs px-2 py-1 rounded-full bg-charcoal-100 dark:bg-charcoal-700 text-charcoal-600 dark:text-charcoal-300 hover:border-orange-400 border border-transparent"
                >
                  🎯 {goalTitle}
                </button>
              )}
              {assetTitle && (
                <button
                  type="button"
                  onClick={() => navigate(deepLinkUrl('assets', task.asset_id))}
                  className="text-xs px-2 py-1 rounded-full bg-charcoal-100 dark:bg-charcoal-700 text-charcoal-600 dark:text-charcoal-300 hover:border-orange-400 border border-transparent"
                >
                  📦 {assetTitle}
                </button>
              )}
            </div>
          )}

          {task.created_at && (
            <p className="text-[11px] text-charcoal-400">
              Created {new Date(task.created_at).toLocaleDateString()}
            </p>
          )}

          {canEdit && (
            <label className="flex items-center gap-2 text-sm cursor-pointer pt-1">
              <input type="checkbox" checked={task.status === 'done'} onChange={toggleComplete} disabled={loading} />
              {task.status === 'done' ? 'Completed' : 'Mark Complete'}
            </label>
          )}
        </div>

        <div className="flex gap-2 pt-4 mt-4 border-t border-charcoal-100 dark:border-charcoal-800">
          {canEdit && onDelete && (
            <button type="button" onClick={handleDelete} disabled={loading}
              className="px-3 py-2 rounded-lg text-sm font-medium text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors">
              Delete
            </button>
          )}
          {canEdit && (
            <button type="button" onClick={handleDuplicate} disabled={loading}
              className="px-3 py-2 rounded-lg text-sm font-medium text-charcoal-500 hover:bg-charcoal-100 dark:hover:bg-charcoal-800 transition-colors">
              Duplicate
            </button>
          )}
          <button type="button" onClick={onClose} className="btn-ghost flex-1">Close</button>
          {canEdit && (
            <button type="button" onClick={onEdit} className="btn-primary flex-1">✎ Edit</button>
          )}
        </div>

        {confirmState && (
          <ConfirmDialog
            title={confirmState.title}
            message={confirmState.message}
            danger={confirmState.danger}
            confirmLabel={confirmState.confirmLabel}
            onConfirm={confirmState.onConfirm}
            onCancel={() => setConfirmState(null)}
          />
        )}
      </div>
    </div>
  )
}
