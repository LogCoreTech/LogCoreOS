import HistoryCalendar from './HistoryCalendar'

// Task-specific adapter over the generic HistoryCalendar — maps a recurring
// task's completion_log (backend: services/task_service.py's
// append_log_entry, entries {date, status: "completed"|"missed"}) into the
// calendar's entriesByDate shape. No endpoint needed; the task object
// already carries this in full.

const STATUS_COLOR = {
  completed: 'bg-emerald-500',
  missed: 'bg-red-400',
}

const LEGEND = [
  { colorClass: 'bg-emerald-500', label: 'Completed' },
  { colorClass: 'bg-red-400', label: 'Missed' },
  { colorClass: 'bg-charcoal-50 dark:bg-charcoal-800', label: 'No occurrence' },
]

export default function RecurrenceLog({ completionLog = [] }) {
  const entriesByDate = {}
  for (const e of completionLog) {
    // A legacy entry with no status was always a completion (see task_service.py).
    const status = e.status || 'completed'
    entriesByDate[e.date] = {
      colorClass: STATUS_COLOR[status] || 'bg-charcoal-100 dark:bg-charcoal-700',
      title: `${e.date} — ${status}`,
    }
  }

  return (
    <div>
      <label className="block text-sm font-medium mb-1">History</label>
      <HistoryCalendar entriesByDate={entriesByDate} legend={LEGEND} />
    </div>
  )
}
