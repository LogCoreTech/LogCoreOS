import { useEffect, useState } from 'react'
import { tasks as tasksApi } from '../lib/api'
import { catColor } from '../lib/constants'
import TaskModal from '../components/TaskModal'

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December']

function daysInMonth(year, month) {
  return new Date(year, month + 1, 0).getDate()
}

function firstDayOfMonth(year, month) {
  return new Date(year, month, 1).getDay()
}

export default function Calendar() {
  const today = new Date()
  const [year, setYear]     = useState(today.getFullYear())
  const [month, setMonth]   = useState(today.getMonth())
  const [tasks, setTasks]   = useState([])
  const [selected, setSelected] = useState(null) // 'YYYY-MM-DD'
  const [showModal, setShowModal] = useState(false)
  const [editTask, setEditTask] = useState(null)
  const [loading, setLoading] = useState(true)

  async function load() {
    setLoading(true)
    try {
      setTasks(await tasksApi.list())
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  function prev() {
    if (month === 0) { setYear(y => y - 1); setMonth(11) }
    else setMonth(m => m - 1)
  }
  function next() {
    if (month === 11) { setYear(y => y + 1); setMonth(0) }
    else setMonth(m => m + 1)
  }

  const totalDays  = daysInMonth(year, month)
  const startDay   = firstDayOfMonth(year, month)
  const todayStr   = today.toISOString().split('T')[0]

  // Index tasks by date
  const byDate = {}
  tasks.forEach(t => {
    if (t.due_date) {
      if (!byDate[t.due_date]) byDate[t.due_date] = []
      byDate[t.due_date].push(t)
    }
  })

  const selectedTasks = selected ? (byDate[selected] || []) : []

  const cells = []
  for (let i = 0; i < startDay; i++) cells.push(null)
  for (let d = 1; d <= totalDays; d++) cells.push(d)

  function dateStr(d) {
    const mm = String(month + 1).padStart(2, '0')
    const dd = String(d).padStart(2, '0')
    return `${year}-${mm}-${dd}`
  }

  return (
    <div className="max-w-2xl mx-auto space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Calendar</h1>
        <button onClick={() => { setEditTask(null); setShowModal(true) }} className="btn-primary">+ Add Task</button>
      </div>

      {/* Month nav */}
      <div className="card p-4">
        <div className="flex items-center justify-between mb-4">
          <button onClick={prev} className="btn-ghost px-3 py-1 text-sm">‹</button>
          <div className="text-center">
            <p className="font-semibold text-base">{MONTHS[month]} {year}</p>
            <button
              onClick={() => { setYear(today.getFullYear()); setMonth(today.getMonth()); setSelected(todayStr) }}
              className="text-xs text-orange-500 hover:underline"
            >
              Today
            </button>
          </div>
          <button onClick={next} className="btn-ghost px-3 py-1 text-sm">›</button>
        </div>

        {/* Day headers */}
        <div className="grid grid-cols-7 mb-1">
          {DAYS.map(d => (
            <div key={d} className="text-center text-xs font-medium text-charcoal-400 dark:text-charcoal-500 py-1">{d}</div>
          ))}
        </div>

        {/* Day cells */}
        <div className="grid grid-cols-7 gap-0.5">
          {cells.map((day, i) => {
            if (!day) return <div key={`e${i}`} />
            const ds = dateStr(day)
            const dayTasks = byDate[ds] || []
            const isToday = ds === todayStr
            const isSelected = ds === selected
            const hasPending = dayTasks.some(t => t.status === 'pending')
            const allDone = dayTasks.length > 0 && dayTasks.every(t => t.status !== 'pending')

            return (
              <button
                key={ds}
                onClick={() => setSelected(isSelected ? null : ds)}
                className={`relative flex flex-col items-center py-1.5 rounded-lg transition-colors min-h-[3rem] ${
                  isSelected
                    ? 'bg-orange-500 text-white'
                    : isToday
                    ? 'bg-orange-100 dark:bg-orange-900/30 text-orange-600 dark:text-orange-400 font-semibold'
                    : 'hover:bg-charcoal-100 dark:hover:bg-charcoal-700'
                }`}
              >
                <span className="text-sm leading-none">{day}</span>
                {dayTasks.length > 0 && (
                  <div className="flex gap-0.5 mt-1 flex-wrap justify-center px-1">
                    {dayTasks.slice(0, 3).map((t, idx) => (
                      <span
                        key={idx}
                        className={`w-1.5 h-1.5 rounded-full ${
                          isSelected
                            ? 'bg-white/70'
                            : t.status !== 'pending'
                            ? 'bg-charcoal-300 dark:bg-charcoal-600'
                            : 'bg-orange-500'
                        }`}
                      />
                    ))}
                    {dayTasks.length > 3 && (
                      <span className={`text-[9px] leading-none ${isSelected ? 'text-white/70' : 'text-charcoal-400'}`}>
                        +{dayTasks.length - 3}
                      </span>
                    )}
                  </div>
                )}
              </button>
            )
          })}
        </div>
      </div>

      {/* Selected day task list */}
      {selected && (
        <div className="card p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold text-sm">
              {new Date(selected + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
            </h2>
            <button
              onClick={() => { setEditTask(null); setShowModal(true) }}
              className="text-xs text-orange-500 font-medium hover:underline"
            >
              + Add
            </button>
          </div>
          {selectedTasks.length === 0 ? (
            <p className="text-sm text-charcoal-400 dark:text-charcoal-500">No tasks due this day.</p>
          ) : (
            <div className="space-y-2">
              {selectedTasks.map(task => (
                <div
                  key={task.id}
                  className="flex items-center gap-3 py-1 cursor-pointer hover:bg-charcoal-50 dark:hover:bg-charcoal-800 rounded-lg px-2 -mx-2"
                  onClick={() => { setEditTask(task); setShowModal(true) }}
                >
                  <div className={`w-2 h-2 rounded-full shrink-0 ${task.status !== 'pending' ? 'bg-charcoal-300' : 'bg-orange-500'}`} />
                  <span className={`flex-1 text-sm ${task.status !== 'pending' ? 'line-through text-charcoal-400' : ''}`}>
                    {task.title}
                  </span>
                  <span className={`badge text-xs ${catColor(task.category)}`}>{task.category}</span>
                  {task.due_time && (
                    <span className="text-xs text-charcoal-400">{task.due_time}</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Upcoming tasks summary */}
      {!selected && !loading && (
        <div className="card p-4">
          <h2 className="font-semibold text-sm mb-3 text-charcoal-500 dark:text-charcoal-400 uppercase tracking-wide">
            This Month
          </h2>
          {(() => {
            const mm = String(month + 1).padStart(2, '0')
            const prefix = `${year}-${mm}-`
            const monthTasks = tasks.filter(t => t.due_date?.startsWith(prefix) && t.status === 'pending')
            if (monthTasks.length === 0) return (
              <p className="text-sm text-charcoal-400 dark:text-charcoal-500">No upcoming tasks this month.</p>
            )
            return (
              <div className="space-y-1.5">
                {monthTasks
                  .sort((a, b) => a.due_date.localeCompare(b.due_date))
                  .slice(0, 8)
                  .map(task => (
                    <div key={task.id} className="flex items-center gap-2 text-sm">
                      <span className="text-xs text-charcoal-400 w-5 shrink-0">
                        {task.due_date.slice(8)}
                      </span>
                      <span className={`badge text-xs ${catColor(task.category)}`}>{task.category}</span>
                      <span className="flex-1 truncate">{task.title}</span>
                      {task.due_time && <span className="text-xs text-charcoal-400 shrink-0">{task.due_time}</span>}
                    </div>
                  ))
                }
              </div>
            )
          })()}
        </div>
      )}

      {showModal && (
        <TaskModal
          task={editTask}
          onClose={() => { setShowModal(false); setEditTask(null) }}
          onSave={() => { setShowModal(false); setEditTask(null); load() }}
        />
      )}
    </div>
  )
}
