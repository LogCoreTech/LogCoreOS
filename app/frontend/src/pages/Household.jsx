import { useEffect, useState } from 'react'
import { shared as sharedApi } from '../lib/api'
import { useAuth } from '../lib/auth'
import { catColor } from '../lib/constants'
import TaskModal from '../components/TaskModal'
import EventModal, { EVENT_COLORS } from '../components/EventModal'

const DAYS   = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December']

function daysInMonth(year, month) { return new Date(year, month + 1, 0).getDate() }
function firstDayOfMonth(year, month) { return new Date(year, month, 1).getDay() }
function _todayStr() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export default function Household() {
  const { user } = useAuth()
  const isAdmin  = user?.role === 'admin'
  const today    = new Date()

  const [year, setYear]     = useState(today.getFullYear())
  const [month, setMonth]   = useState(today.getMonth())
  const [tasks, setTasks]   = useState([])
  const [events, setEvents] = useState([])
  const [selected, setSelected] = useState(_todayStr)
  const [showTaskModal, setShowTaskModal]   = useState(false)
  const [editTask, setEditTask]             = useState(null)
  const [showEventModal, setShowEventModal] = useState(false)
  const [editEvent, setEditEvent]           = useState(null)
  const [loading, setLoading] = useState(true)

  async function load() {
    setLoading(true)
    try {
      const [t, e] = await Promise.all([sharedApi.list(), sharedApi.sharedEvents()])
      setTasks(t)
      setEvents(e)
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

  const totalDays = daysInMonth(year, month)
  const startDay  = firstDayOfMonth(year, month)
  const todayStr  = _todayStr()

  // Index tasks by due_date
  const byDate = {}
  tasks.forEach(t => {
    if (t.due_date) {
      if (!byDate[t.due_date]) byDate[t.due_date] = []
      byDate[t.due_date].push(t)
    }
  })

  // Index events by start_date (for grid dots)
  const eventsByDate = {}
  events.forEach(ev => {
    if (!eventsByDate[ev.start_date]) eventsByDate[ev.start_date] = []
    eventsByDate[ev.start_date].push(ev)
  })

  // Selected-day: range-check for multi-day events
  const selectedEvents = selected
    ? events.filter(ev => ev.start_date <= selected && selected <= (ev.end_date || ev.start_date))
    : []
  const selectedTasks = selected ? (byDate[selected] || []) : []

  const cells = []
  for (let i = 0; i < startDay; i++) cells.push(null)
  for (let d = 1; d <= totalDays; d++) cells.push(d)

  function dateStr(d) {
    const mm = String(month + 1).padStart(2, '0')
    const dd = String(d).padStart(2, '0')
    return `${year}-${mm}-${dd}`
  }

  // Household event API adapter for EventModal
  const householdEventApi = {
    add:    (body) => sharedApi.addSharedEvent(body),
    update: (id, body) => sharedApi.updateSharedEvent(id, body),
    remove: (id) => sharedApi.removeSharedEvent(id),
  }

  return (
    <div className="max-w-2xl mx-auto space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Household</h1>
          <p className="text-sm text-charcoal-500 dark:text-charcoal-400 mt-0.5">
            Shared calendar for everyone
          </p>
        </div>
        {isAdmin && (
          <div className="flex gap-2">
            <button
              onClick={() => { setEditEvent(null); setShowEventModal(true) }}
              className="btn-primary"
            >
              + Event
            </button>
            <button
              onClick={() => { setEditTask(null); setShowTaskModal(true) }}
              className="btn-ghost"
            >
              + Task
            </button>
          </div>
        )}
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
            const ds         = dateStr(day)
            const dayTasks   = byDate[ds] || []
            const dayEvents  = eventsByDate[ds] || []
            const isToday    = ds === todayStr
            const isSelected = ds === selected

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

                {/* Event color dots */}
                {dayEvents.length > 0 && (
                  <div className="flex gap-0.5 mt-0.5 flex-wrap justify-center px-1">
                    {dayEvents.slice(0, 3).map((ev, idx) => (
                      <span key={idx} className="w-1.5 h-1.5 rounded-full shrink-0"
                        style={{
                          backgroundColor: isSelected
                            ? 'rgba(255,255,255,0.7)'
                            : (EVENT_COLORS[ev.color] || '#3b82f6'),
                        }} />
                    ))}
                  </div>
                )}

                {/* Task dots */}
                {dayTasks.length > 0 && (
                  <div className="flex gap-0.5 mt-0.5 flex-wrap justify-center px-1">
                    {dayTasks.slice(0, 3).map((t, idx) => (
                      <span key={idx} className={`w-1.5 h-1.5 rounded-full ${
                        isSelected ? 'bg-white/70'
                        : t.status !== 'pending' ? 'bg-charcoal-300 dark:bg-charcoal-600'
                        : 'bg-orange-500'
                      }`} />
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

      {/* Selected-day panel */}
      {selected && (
        <div className="card p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold text-sm">
              {new Date(selected + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
            </h2>
            {isAdmin && (
              <div className="flex gap-3">
                <button
                  onClick={() => { setEditEvent(null); setShowEventModal(true) }}
                  className="text-xs font-medium hover:underline"
                  style={{ color: '#3b82f6' }}
                >
                  + Event
                </button>
                <button
                  onClick={() => { setEditTask(null); setShowTaskModal(true) }}
                  className="text-xs text-orange-500 font-medium hover:underline"
                >
                  + Task
                </button>
              </div>
            )}
          </div>

          {selectedEvents.length === 0 && selectedTasks.length === 0 && (
            <p className="text-sm text-charcoal-400 dark:text-charcoal-500">Nothing scheduled this day.</p>
          )}

          {/* Events */}
          {selectedEvents.length > 0 && (
            <div className="space-y-1.5 mb-3">
              <p className="text-xs font-medium text-charcoal-400 dark:text-charcoal-500 uppercase tracking-wide">Events</p>
              {selectedEvents.map(ev => (
                <div
                  key={ev.id}
                  className={`flex items-center gap-3 py-1 rounded-lg px-2 -mx-2 ${
                    isAdmin ? 'cursor-pointer hover:bg-charcoal-50 dark:hover:bg-charcoal-800' : ''
                  }`}
                  onClick={isAdmin ? () => { setEditEvent(ev); setShowEventModal(true) } : undefined}
                >
                  <span className="w-2 h-2 rounded-full shrink-0"
                    style={{ backgroundColor: EVENT_COLORS[ev.color] || '#3b82f6' }} />
                  <span className="flex-1 text-sm">{ev.title}</span>
                  {!ev.all_day && ev.start_time && (
                    <span className="text-xs text-charcoal-400">{ev.start_time}</span>
                  )}
                  {ev.created_by && (
                    <span className="text-xs text-charcoal-400">{ev.created_by}</span>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Tasks */}
          {selectedTasks.length > 0 && (
            <div className="space-y-2">
              {selectedEvents.length > 0 && (
                <p className="text-xs font-medium text-charcoal-400 dark:text-charcoal-500 uppercase tracking-wide">Tasks</p>
              )}
              {selectedTasks.map(task => (
                <div
                  key={task.id}
                  className={`flex items-center gap-3 py-1 rounded-lg px-2 -mx-2 ${
                    isAdmin ? 'cursor-pointer hover:bg-charcoal-50 dark:hover:bg-charcoal-800' : ''
                  }`}
                  onClick={isAdmin ? () => { setEditTask(task); setShowTaskModal(true) } : undefined}
                >
                  <div className={`w-2 h-2 rounded-full shrink-0 ${task.status !== 'pending' ? 'bg-charcoal-300' : 'bg-orange-500'}`} />
                  <span className={`flex-1 text-sm ${task.status !== 'pending' ? 'line-through text-charcoal-400' : ''}`}>
                    {task.title}
                  </span>
                  <span className={`badge text-xs ${catColor(task.category)}`}>{task.category}</span>
                  {task.due_time && <span className="text-xs text-charcoal-400">{task.due_time}</span>}
                  {task.created_by && <span className="text-xs text-charcoal-400">{task.created_by}</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* This month summary (when no day selected) */}
      {!selected && !loading && (
        <div className="card p-4">
          <h2 className="font-semibold text-sm mb-3 text-charcoal-500 dark:text-charcoal-400 uppercase tracking-wide">
            This Month
          </h2>
          {(() => {
            const mm = String(month + 1).padStart(2, '0')
            const prefix = `${year}-${mm}-`
            const mTasks  = tasks.filter(t => t.due_date?.startsWith(prefix) && t.status === 'pending')
            const mEvents = events.filter(ev => ev.start_date?.startsWith(prefix))
            if (mTasks.length === 0 && mEvents.length === 0) return (
              <p className="text-sm text-charcoal-400 dark:text-charcoal-500">Nothing scheduled this month.</p>
            )
            const combined = [
              ...mEvents.map(ev => ({ _type: 'event', date: ev.start_date, ev })),
              ...mTasks.map(t  => ({ _type: 'task',  date: t.due_date,    t  })),
            ].sort((a, b) => a.date.localeCompare(b.date))
            return (
              <div className="space-y-1.5">
                {combined.slice(0, 10).map((item) => (
                  item._type === 'event' ? (
                    <div key={`ev-${item.ev.id}`} className="flex items-center gap-2 text-sm">
                      <span className="text-xs text-charcoal-400 w-5 shrink-0">{item.date.slice(8)}</span>
                      <span className="w-2 h-2 rounded-full shrink-0"
                        style={{ backgroundColor: EVENT_COLORS[item.ev.color] || '#3b82f6' }} />
                      <span className="flex-1 truncate">{item.ev.title}</span>
                      {!item.ev.all_day && item.ev.start_time && (
                        <span className="text-xs text-charcoal-400 shrink-0">{item.ev.start_time}</span>
                      )}
                    </div>
                  ) : (
                    <div key={`t-${item.t.id}`} className="flex items-center gap-2 text-sm">
                      <span className="text-xs text-charcoal-400 w-5 shrink-0">{item.date.slice(8)}</span>
                      <span className={`badge text-xs ${catColor(item.t.category)}`}>{item.t.category}</span>
                      <span className="flex-1 truncate">{item.t.title}</span>
                    </div>
                  )
                ))}
              </div>
            )
          })()}
        </div>
      )}

      {showTaskModal && (
        <TaskModal
          task={editTask}
          saveApi={sharedApi}
          onClose={() => { setShowTaskModal(false); setEditTask(null) }}
          onSave={() => { setShowTaskModal(false); setEditTask(null); load() }}
        />
      )}

      {showEventModal && (
        <EventModal
          event={editEvent}
          defaultDate={selected || undefined}
          saveApi={householdEventApi}
          onClose={() => { setShowEventModal(false); setEditEvent(null) }}
          onSave={() => { setShowEventModal(false); setEditEvent(null); load() }}
        />
      )}
    </div>
  )
}
