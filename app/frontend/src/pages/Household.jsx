import { useEffect, useState } from 'react'
import { shared as sharedApi, admin as adminApi } from '../lib/api'
import { useAuth } from '../lib/auth'
import TaskModal from '../components/TaskModal'
import EventModal from '../components/EventModal'
import CalendarGrid from '../components/CalendarGrid'
import { catColor } from '../lib/constants'

const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December']

const PRI_ON = {
  High:   'bg-orange-500 text-white border-orange-500',
  Medium: 'bg-yellow-400 text-charcoal-900 border-yellow-400',
  Low:    'bg-charcoal-400 text-white border-charcoal-400',
}
const PRI_OFF = 'bg-transparent text-charcoal-500 dark:text-charcoal-400 border-charcoal-300 dark:border-charcoal-600'

const PRI_DOT = {
  High:   'bg-orange-500',
  Medium: 'bg-yellow-400',
  Low:    'bg-charcoal-300 dark:bg-charcoal-600',
}

const TABS = [
  { id: 'calendar', label: 'Calendar' },
  { id: 'tasks',    label: 'Tasks' },
]

function todayStr() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export default function Household() {
  const { user } = useAuth()
  const isAdmin  = user?.role === 'admin'
  const today    = new Date()

  const [view, setView]     = useState('calendar')
  const [year, setYear]     = useState(today.getFullYear())
  const [month, setMonth]   = useState(today.getMonth())
  const [tasks, setTasks]   = useState([])
  const [events, setEvents] = useState([])
  const [selected, setSelected]           = useState(todayStr())
  const [shownPriorities, setShownPriorities] = useState(['High', 'Medium', 'Low'])
  const [taskFilter, setTaskFilter]       = useState('pending')
  const [showTaskModal, setShowTaskModal] = useState(false)
  const [editTask, setEditTask]           = useState(null)
  const [showEventModal, setShowEventModal] = useState(false)
  const [editEvent, setEditEvent]         = useState(null)
  const [users, setUsers]                 = useState([])

  async function load() {
    const [t, e] = await Promise.allSettled([sharedApi.list(), sharedApi.sharedEvents()])
    if (t.status === 'fulfilled') setTasks(t.value)
    if (e.status === 'fulfilled') setEvents(e.value)
  }

  useEffect(() => { load() }, [])
  useEffect(() => {
    if (isAdmin) adminApi.users().then(setUsers).catch(() => {})
  }, [isAdmin])

  function prev() {
    if (month === 0) { setYear(y => y - 1); setMonth(11) }
    else setMonth(m => m - 1)
  }
  function next() {
    if (month === 11) { setYear(y => y + 1); setMonth(0) }
    else setMonth(m => m + 1)
  }
  function goToday() {
    const d = new Date()
    setYear(d.getFullYear())
    setMonth(d.getMonth())
    setSelected(todayStr())
  }
  function togglePriority(p) {
    setShownPriorities(prev =>
      prev.includes(p) ? prev.filter(x => x !== p) : [...prev, p]
    )
  }
  async function markDone(id) {
    await sharedApi.update(id, { status: 'done' })
    load()
  }

  const visibleTasks = tasks.filter(t => shownPriorities.includes(t.priority))

  const _today = todayStr()
  const filteredTasks = tasks.filter(t =>
    taskFilter === 'all'     ? true :
    taskFilter === 'pending' ? t.status === 'pending' :
    taskFilter === 'done'    ? t.status === 'done' :
    taskFilter === 'overdue' ? (t.status === 'pending' && t.due_date && t.due_date < _today) : true
  )

  const householdEventApi = {
    add:    body       => sharedApi.addSharedEvent(body),
    update: (id, body) => sharedApi.updateSharedEvent(id, body),
    remove: id         => sharedApi.removeSharedEvent(id),
  }

  return (
    <div className="w-full max-w-4xl mx-auto space-y-4">

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-bold">Household</h1>
          <p className="text-sm text-charcoal-500 dark:text-charcoal-400 mt-0.5">Shared space for everyone</p>
        </div>

        {/* Tab-aware header actions */}
        <div className="flex items-center gap-2 flex-wrap">
          {view === 'calendar' && (
            <div className="flex gap-1">
              {['High', 'Medium', 'Low'].map(p => (
                <button
                  key={p}
                  onClick={() => togglePriority(p)}
                  className={`text-xs px-2.5 py-1 rounded-full border font-medium transition-colors ${
                    shownPriorities.includes(p) ? PRI_ON[p] : PRI_OFF
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
          )}
          {isAdmin && view === 'calendar' && (
            <button
              onClick={() => { setEditEvent(null); setShowEventModal(true) }}
              className="btn-primary"
            >
              + Event
            </button>
          )}
          {isAdmin && (
            <button
              onClick={() => { setEditTask(null); setShowTaskModal(true) }}
              className="btn-ghost"
            >
              + Task
            </button>
          )}
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 bg-charcoal-100 dark:bg-charcoal-800 rounded-lg p-1">
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => setView(id)}
            className={`flex-1 py-1.5 rounded-md text-xs font-medium transition-colors ${
              view === id
                ? 'bg-white dark:bg-charcoal-600 text-charcoal-900 dark:text-gray-100 shadow-sm'
                : 'text-charcoal-500 dark:text-charcoal-400'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* ── Calendar tab ── */}
      {view === 'calendar' && (
        <>
          {/* Month nav */}
          <div className="flex items-center justify-between">
            <button onClick={prev} className="btn-ghost px-3 py-1.5 text-sm">‹</button>
            <div className="flex items-center gap-3">
              <span className="font-semibold text-base">{MONTHS[month]} {year}</span>
              <button
                onClick={goToday}
                className="text-xs px-2 py-0.5 rounded border border-orange-400 text-orange-500 hover:bg-orange-50 dark:hover:bg-orange-900/20 transition-colors"
              >
                Today
              </button>
            </div>
            <button onClick={next} className="btn-ghost px-3 py-1.5 text-sm">›</button>
          </div>

          {/* Calendar grid — full-bleed on mobile, card on desktop */}
          <div className="-mx-4 md:mx-0 md:card md:p-4">
            <CalendarGrid
              tasks={tasks}
              visibleTasks={visibleTasks}
              events={events}
              year={year}
              month={month}
              selectedDay={selected}
              onSelectDay={ds => setSelected(ds ?? todayStr())}
              readOnly={!isAdmin}
              onEditTask={task => { setEditTask(task); setShowTaskModal(true) }}
              onEditEvent={ev  => { setEditEvent(ev);  setShowEventModal(true) }}
              onAddTask={() => { setEditTask(null); setShowTaskModal(true) }}
              onAddEvent={() => { setEditEvent(null); setShowEventModal(true) }}
            />
          </div>
        </>
      )}

      {/* ── Tasks tab ── */}
      {view === 'tasks' && (
        <>
          {/* Filter tabs */}
          <div className="flex gap-1 bg-charcoal-100 dark:bg-charcoal-800 rounded-lg p-1">
            {['pending', 'all', 'done', 'overdue'].map(f => (
              <button
                key={f}
                onClick={() => setTaskFilter(f)}
                className={`flex-1 py-1 rounded-md text-xs font-medium capitalize transition-colors ${
                  taskFilter === f
                    ? 'bg-white dark:bg-charcoal-600 text-charcoal-900 dark:text-gray-100 shadow-sm'
                    : 'text-charcoal-500 dark:text-charcoal-400'
                }`}
              >
                {f}
              </button>
            ))}
          </div>

          {/* Task list */}
          {filteredTasks.length === 0 ? (
            <div className="card p-8 text-center text-charcoal-500 dark:text-charcoal-400">
              <p className="text-4xl mb-2">✓</p>
              <p>No tasks here.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {filteredTasks.map(task => (
                <HouseholdTaskCard
                  key={task.id}
                  task={task}
                  isAdmin={isAdmin}
                  today={_today}
                  onDone={() => markDone(task.id)}
                  onEdit={() => { setEditTask(task); setShowTaskModal(true) }}
                />
              ))}
            </div>
          )}
        </>
      )}

      {/* Modals */}
      {showTaskModal && (
        <TaskModal
          task={editTask}
          saveApi={sharedApi}
          users={isAdmin ? users : undefined}
          onClose={() => { setShowTaskModal(false); setEditTask(null) }}
          onSave={() => { setShowTaskModal(false); setEditTask(null); load() }}
          onDelete={() => { setShowTaskModal(false); setEditTask(null); load() }}
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

function HouseholdTaskCard({ task, isAdmin, today, onDone, onEdit }) {
  const overdue = task.status === 'pending' && task.due_date && task.due_date < today

  return (
    <div className={`card p-3 flex items-start gap-3 overflow-hidden ${overdue ? 'border-red-500/40' : ''}`}>
      {/* Checkbox */}
      {task.status === 'pending' ? (
        <button
          onClick={onDone}
          className="mt-0.5 shrink-0 w-5 h-5 rounded border-2 border-charcoal-300 dark:border-charcoal-600 hover:border-orange-500 hover:bg-orange-500 transition-colors"
        />
      ) : (
        <div className="mt-0.5 shrink-0 w-5 h-5 rounded bg-orange-500 flex items-center justify-center text-white text-xs">✓</div>
      )}

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className={`badge ${catColor(task.category)}`}>{task.category}</span>
          <span className={`w-2 h-2 rounded-full shrink-0 ${PRI_DOT[task.priority] || 'bg-charcoal-300'}`} />
          <span className="text-xs text-charcoal-500 dark:text-charcoal-400">{task.priority}</span>
          {overdue && <span className="text-xs text-red-500 font-medium">OVERDUE</span>}
        </div>
        <p className={`text-sm mt-1 truncate ${task.status === 'done' ? 'line-through text-charcoal-400' : ''}`}>
          {task.recurrence && '↻ '}{task.title}
        </p>
        <div className="flex items-center gap-2 mt-0.5 flex-wrap">
          {task.due_date && (
            <p className="text-xs text-charcoal-500 dark:text-charcoal-400">Due {task.due_date}</p>
          )}
          {task.assigned_to && (
            <p className="text-xs text-blue-500 dark:text-blue-400 font-medium">→ {task.assigned_to}</p>
          )}
          {task.created_by && (
            <p className="text-xs text-charcoal-400 dark:text-charcoal-500">by {task.created_by}</p>
          )}
        </div>
        {task.notes && (
          <p className="text-xs text-charcoal-500 dark:text-charcoal-400 mt-0.5 truncate">{task.notes}</p>
        )}
      </div>

      {/* Edit — admin only */}
      {isAdmin && (
        <button onClick={onEdit} className="text-charcoal-400 hover:text-orange-500 p-1 text-xs shrink-0">✎</button>
      )}
    </div>
  )
}
