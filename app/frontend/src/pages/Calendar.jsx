import { useEffect, useState } from 'react'
import { calendar as calendarApi, shared as sharedApi, team as teamApi } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useWorkspace } from '../lib/workspace'
import TaskModal from '../components/TaskModal'
import EventModal from '../components/EventModal'
import CalendarGrid from '../components/CalendarGrid'

const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December']

const PRI_ON = {
  High:   'bg-orange-500 text-white border-orange-500',
  Medium: 'bg-yellow-400 text-charcoal-900 border-yellow-400',
  Low:    'bg-charcoal-400 text-white border-charcoal-400',
}
const PRI_OFF = 'bg-transparent text-charcoal-500 dark:text-charcoal-400 border-charcoal-300 dark:border-charcoal-600'

const POOL_ON  = 'bg-blue-500 text-white border-blue-500'
const POOL_OFF = 'bg-transparent text-charcoal-500 dark:text-charcoal-400 border-charcoal-300 dark:border-charcoal-600'

function todayStr() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export default function Calendar() {
  const { user } = useAuth()
  const { workspace } = useWorkspace()
  const isAdmin  = user?.role === 'admin'
  const isPersonal = workspace === 'personal'
  const poolApi  = isPersonal ? sharedApi : teamApi
  const poolEmoji = isPersonal ? '🏠' : '🧑‍🤝‍🧑'
  const poolLabel = isPersonal ? 'Household' : 'Teams'

  const today = new Date()
  const [year, setYear]   = useState(today.getFullYear())
  const [month, setMonth] = useState(today.getMonth())
  const [tasks, setTasks]               = useState([])
  const [assignedPoolTasks, setAssignedPoolTasks] = useState([])
  const [events, setEvents]             = useState([])
  const [poolEvents, setPoolEvents]     = useState([])
  const [selected, setSelected] = useState(todayStr())
  const [shownPriorities, setShownPriorities] = useState(['High', 'Medium', 'Low'])
  const [showPool, setShowPool]         = useState(true)
  const [showModal, setShowModal]       = useState(false)
  const [editTask, setEditTask]         = useState(null)
  const [showEventModal, setShowEventModal] = useState(false)
  const [editEvent, setEditEvent]       = useState(null)
  const [loading, setLoading] = useState(true)

  const poolEventApi = {
    add:    body       => poolApi.addSharedEvent(body),
    update: (id, body) => poolApi.updateSharedEvent(id, body),
    remove: id         => poolApi.removeSharedEvent(id),
  }

  async function load() {
    setLoading(true)
    const [t, e, pe, pt] = await Promise.allSettled([
      calendarApi.tasks(),
      calendarApi.events(),
      poolApi.sharedEvents(),
      poolApi.list(),
    ])
    if (t.status  === 'fulfilled') setTasks(t.value)
    if (e.status  === 'fulfilled') setEvents(e.value)
    if (pe.status === 'fulfilled') setPoolEvents(pe.value)
    if (pt.status === 'fulfilled') {
      setAssignedPoolTasks(
        pt.value.filter(task => task.assigned_to === user?.name)
      )
    }
    setLoading(false)
  }

  useEffect(() => { load() }, [user?.name, workspace])

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

  const allCalendarTasks = [
    ...tasks.filter(t => t.status !== 'done'),
    ...assignedPoolTasks.filter(t => t.status !== 'done').map(t => ({ ...t, _household: true, _poolEmoji: poolEmoji })),
  ]
  const visibleTasks = allCalendarTasks.filter(t => shownPriorities.includes(t.priority))

  // Merge personal + shared pool events; tag pool ones for CalendarGrid display
  const allEvents = [
    ...events,
    ...(showPool ? poolEvents.map(e => ({ ...e, _household: true, _poolEmoji: poolEmoji })) : []),
  ]

  const isPoolEv = editEvent?._household === true

  return (
    <div className="w-full max-w-4xl mx-auto space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h1 className="text-2xl font-bold">Calendar</h1>
        <div className="flex items-center gap-2 flex-wrap">
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
            <button
              onClick={() => setShowPool(h => !h)}
              className={`text-xs px-2.5 py-1 rounded-full border font-medium transition-colors ${
                showPool ? POOL_ON : POOL_OFF
              }`}
            >
              {poolEmoji}
            </button>
          </div>
          <button
            onClick={() => { setEditEvent(null); setShowEventModal(true) }}
            className="btn-primary"
          >
            + Event
          </button>
          <button
            onClick={() => { setEditTask(null); setShowModal(true) }}
            className="btn-ghost"
          >
            + Task
          </button>
        </div>
      </div>

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
          tasks={allCalendarTasks}
          visibleTasks={visibleTasks}
          events={allEvents}
          year={year}
          month={month}
          selectedDay={selected}
          onSelectDay={ds => setSelected(ds ?? todayStr())}
          onEditTask={task => { setEditTask(task); setShowModal(true) }}
          onEditEvent={ev => {
            if (ev._household && !isAdmin) return
            setEditEvent(ev)
            setShowEventModal(true)
          }}
          onAddTask={() => { setEditTask(null); setShowModal(true) }}
          onAddEvent={() => { setEditEvent(null); setShowEventModal(true) }}
        />
      </div>

      {showModal && (
        <TaskModal
          task={editTask}
          onClose={() => { setShowModal(false); setEditTask(null) }}
          onSave={() => { setShowModal(false); setEditTask(null); load() }}
          onDelete={() => { setShowModal(false); setEditTask(null); load() }}
        />
      )}
      {showEventModal && (
        <EventModal
          event={editEvent}
          defaultDate={selected || undefined}
          saveApi={isPoolEv ? poolEventApi : undefined}
          poolSaveApi={!isPoolEv ? poolEventApi : undefined}
          poolLabel={poolLabel}
          isHouseholdEvent={isPoolEv}
          onClose={() => { setShowEventModal(false); setEditEvent(null) }}
          onSave={() => { setShowEventModal(false); setEditEvent(null); load() }}
        />
      )}
    </div>
  )
}
