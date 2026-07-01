import { useRef } from 'react'
import { EVENT_COLORS } from './EventModal'
import { catColor } from '../lib/constants'

// ── Holiday engine ────────────────────────────────────────────────────────────

function _fmt(y, m, d) {
  return `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`
}

// Nth occurrence of weekday (0=Sun…6=Sat) in month (1-indexed). n=1 = first, n=4 = fourth.
function nthWeekday(year, month, n, weekday) {
  const firstDow = new Date(year, month - 1, 1).getDay()
  let offset = weekday - firstDow
  if (offset < 0) offset += 7
  return _fmt(year, month, 1 + offset + (n - 1) * 7)
}

// Last occurrence of weekday in month (1-indexed).
function lastWeekday(year, month, weekday) {
  const dim = new Date(year, month, 0).getDate()
  const lastDow = new Date(year, month - 1, dim).getDay()
  let offset = lastDow - weekday
  if (offset < 0) offset += 7
  return _fmt(year, month, dim - offset)
}

// Meeus/Jones/Butcher Easter algorithm. Returns { month, day } (1-indexed).
function easterMD(year) {
  const a = year % 19
  const b = Math.floor(year / 100)
  const c = year % 100
  const d = Math.floor(b / 4)
  const e = b % 4
  const f = Math.floor((b + 8) / 25)
  const g = Math.floor((b - f + 1) / 3)
  const h = (19 * a + b - d - g + 15) % 30
  const i = Math.floor(c / 4)
  const k = c % 4
  const l = (32 + 2 * e + 2 * i - h - k) % 7
  const m = Math.floor((a + 11 * h + 22 * l) / 451)
  const month = Math.floor((h + l - 7 * m + 114) / 31)
  const day   = ((h + l - 7 * m + 114) % 31) + 1
  return { month, day }
}

function getHolidays(year) {
  const { month: em, day: ed } = easterMD(year)
  const easter   = new Date(year, em - 1, ed)
  const goodFri  = new Date(easter); goodFri.setDate(easter.getDate() - 2)
  const gfStr    = _fmt(goodFri.getFullYear(), goodFri.getMonth() + 1, goodFri.getDate())

  return [
    // Fixed-date
    { date: _fmt(year,  1,  1), name: "New Year's Day" },
    { date: _fmt(year,  2, 14), name: "Valentine's Day" },
    { date: _fmt(year,  3, 17), name: "St. Patrick's Day" },
    { date: _fmt(year,  7,  4), name: "Independence Day" },
    { date: _fmt(year, 10, 31), name: "Halloween" },
    { date: _fmt(year, 11, 11), name: "Veterans Day" },
    { date: _fmt(year, 12, 24), name: "Christmas Eve" },
    { date: _fmt(year, 12, 25), name: "Christmas" },
    { date: _fmt(year, 12, 31), name: "New Year's Eve" },
    // Floating
    { date: nthWeekday(year, 2, 3, 1),  name: "Presidents' Day" },
    { date: nthWeekday(year, 5, 2, 0),  name: "Mother's Day" },
    { date: lastWeekday(year, 5, 1),    name: "Memorial Day" },
    { date: nthWeekday(year, 6, 3, 0),  name: "Father's Day" },
    { date: nthWeekday(year, 9, 1, 1),  name: "Labor Day" },
    { date: nthWeekday(year, 11, 4, 4), name: "Thanksgiving" },
    // Religious
    { date: _fmt(year, em, ed), name: "Easter Sunday" },
    { date: gfStr,              name: "Good Friday" },
  ]
}

function buildHolidayMap(year) {
  const map = {}
  // Cover leading/trailing days from adjacent years shown in boundary months
  for (const y of [year - 1, year, year + 1]) {
    getHolidays(y).forEach(h => { map[h.date] = h.name })
  }
  return map
}

// ─────────────────────────────────────────────────────────────────────────────

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const LANE_H    = 22   // px per event lane
const MAX_LANES = 3
const MAX_PILLS = 2
const DAY_NUM_H = 28   // px reserved for the day-number row at the top of each cell

const PRI_CLS = {
  High:   'bg-orange-500 text-white',
  Medium: 'bg-yellow-400 text-charcoal-900',
  Low:    'bg-charcoal-300 dark:bg-charcoal-600 text-charcoal-700 dark:text-charcoal-200',
}

function todayStr() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function getWeekRows(year, month) {
  const firstDay = new Date(year, month, 1).getDay()
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const lastDay = new Date(year, month, daysInMonth).getDay()

  function fmt(y, m, d) {
    const dt = new Date(y, m, d)
    return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`
  }

  const allDates = []
  for (let i = 0; i < firstDay; i++) allDates.push(fmt(year, month, 1 - firstDay + i))
  for (let d = 1; d <= daysInMonth; d++) allDates.push(fmt(year, month, d))
  for (let i = 1; i <= (6 - lastDay); i++) allDates.push(fmt(year, month, daysInMonth + i))

  const rows = []
  for (let i = 0; i < allDates.length; i += 7) {
    const dates = allDates.slice(i, i + 7)
    rows.push({ rowStart: dates[0], rowEnd: dates[6], dates })
  }
  return rows
}

function assignLanes(events, rowStart, rowEnd) {
  const rowEvts = events.filter(ev => {
    const end = ev.end_date || ev.start_date
    return ev.start_date <= rowEnd && end >= rowStart
  })
  rowEvts.sort((a, b) => {
    const aEnd = a.end_date || a.start_date
    const bEnd = b.end_date || b.start_date
    const aSpan = new Date(aEnd) - new Date(a.start_date)
    const bSpan = new Date(bEnd) - new Date(b.start_date)
    if (bSpan !== aSpan) return bSpan - aSpan
    return a.start_date.localeCompare(b.start_date)
  })
  const laneEnds = []
  return rowEvts.map(ev => {
    const evEnd = ev.end_date || ev.start_date
    let lane = laneEnds.findIndex(e => e < ev.start_date)
    if (lane === -1) lane = laneEnds.length
    laneEnds[lane] = evEnd
    return { ...ev, _lane: lane }
  })
}

function WeekRow({ dates, events, visibleTasks, year, month, selectedDay, onSelectDay, onEditEvent, onEditTask, holidayMap }) {
  const rowStart     = dates[0]
  const rowEnd       = dates[6]
  const today        = todayStr()
  const mm           = String(month + 1).padStart(2, '0')
  const lastTaskClick = useRef({})

  const laned      = assignLanes(events, rowStart, rowEnd)
  const shownBars  = laned.filter(ev => ev._lane < MAX_LANES)
  const hiddenBars = laned.filter(ev => ev._lane >= MAX_LANES)

  // Row-wide spacer: height of the absolute bar container (tallest lane in this row)
  const usedLanes = shownBars.length > 0
    ? Math.min(MAX_LANES, Math.max(...shownBars.map(ev => ev._lane + 1)))
    : 0
  const spacerH = usedLanes > 0 ? usedLanes * LANE_H + 2 : 0

  // Per-cell spacer: only count lanes that actually touch this date
  function daySpacerH(ds) {
    const barsOnDay = shownBars.filter(ev => {
      const evEnd = ev.end_date || ev.start_date
      return ev.start_date <= ds && evEnd >= ds
    })
    if (barsOnDay.length === 0) return 0
    return Math.max(...barsOnDay.map(ev => ev._lane + 1)) * LANE_H + 2
  }

  return (
    <div className="relative">
      {/* Absolute event bar layer — starts below the day-number row */}
      <div
        className="absolute inset-x-0 pointer-events-none"
        style={{ top: DAY_NUM_H, height: spacerH }}
      >
        {shownBars.map(ev => {
          const evEnd       = ev.end_date || ev.start_date
          const clampStart  = ev.start_date < rowStart ? rowStart : ev.start_date
          const clampEnd    = evEnd > rowEnd ? rowEnd : evEnd
          const startIdx    = dates.indexOf(clampStart)
          const endIdx      = dates.indexOf(clampEnd)
          if (startIdx === -1 || endIdx === -1) return null

          const left       = (startIdx / 7) * 100
          const width      = ((endIdx - startIdx + 1) / 7) * 100
          const top        = ev._lane * LANE_H + 1
          const startsHere = ev.start_date >= rowStart
          const endsHere   = evEnd <= rowEnd
          const bg         = EVENT_COLORS[ev.color] || EVENT_COLORS.blue

          return (
            <div
              key={`${ev.id}-${rowStart}`}
              className="absolute flex items-center px-1 text-white overflow-hidden pointer-events-auto cursor-pointer select-none"
              style={{
                left: `calc(${left}% + 1px)`,
                width: `calc(${width}% - 2px)`,
                top,
                height: LANE_H - 4,
                backgroundColor: bg,
                borderRadius: `${startsHere ? 3 : 0}px ${endsHere ? 3 : 0}px ${endsHere ? 3 : 0}px ${startsHere ? 3 : 0}px`,
                zIndex: 5,
              }}
              onClick={e => {
                e.stopPropagation()
                onEditEvent?.(ev)
              }}
            >
              {!startsHere && <span className="text-[9px] mr-0.5 opacity-80">◀</span>}
              {ev._household && startsHere && <span className="text-[9px] mr-0.5 opacity-90">{ev._poolEmoji || '🏠'}</span>}
              <span className="text-[11px] leading-none overflow-hidden whitespace-nowrap flex-1 font-medium">{ev.title}</span>
              {!endsHere && <span className="text-[9px] ml-0.5 opacity-80">▶</span>}
            </div>
          )
        })}
      </div>

      {/* Day cells */}
      <div className="grid grid-cols-7">
        {dates.map(ds => {
          const isCurrentMonth = ds.slice(0, 7) === `${year}-${mm}`
          const isToday        = ds === today
          const isSelected     = ds === selectedDay
          const dayNum         = parseInt(ds.slice(8), 10)
          const dayTasks       = visibleTasks.filter(t => t.due_date === ds)
          const hiddenEvtCount = hiddenBars.filter(ev =>
            ev.start_date <= ds && (ev.end_date || ev.start_date) >= ds
          ).length
          const taskSlots = holidayMap[ds] ? MAX_PILLS - 1 : MAX_PILLS
          const overflow = hiddenEvtCount + Math.max(0, dayTasks.length - taskSlots)

          return (
            <button
              key={ds}
              onClick={() => onSelectDay(isSelected ? null : ds)}
              className={`flex flex-col border-l border-charcoal-200 dark:border-charcoal-700 first:border-l-0 text-left transition-colors min-h-[110px] min-w-0 overflow-hidden ${
                isSelected
                  ? 'bg-orange-50 dark:bg-orange-900/20'
                  : 'hover:bg-charcoal-50 dark:hover:bg-charcoal-800/50'
              } ${!isCurrentMonth ? 'opacity-40' : ''}`}
            >
              {/* Day number */}
              <div className="px-1 pt-1 shrink-0" style={{ height: DAY_NUM_H }}>
                <span className={`text-xs font-semibold w-6 h-6 flex items-center justify-center rounded-full ${
                  isToday
                    ? 'bg-orange-500 text-white'
                    : isSelected
                    ? 'text-orange-600 dark:text-orange-400 font-bold'
                    : 'text-charcoal-700 dark:text-charcoal-300'
                }`}>
                  {dayNum}
                </span>
              </div>

              {/* Spacer — only as tall as lanes that touch this specific day */}
              <div style={{ height: daySpacerH(ds) }} className="shrink-0" />

              {/* Holiday + task pills — holiday is always pinned first */}
              <div className="px-0.5 pb-1 w-full flex flex-col gap-y-0.5">
                {holidayMap[ds] && (
                  <div className="text-[11px] leading-tight px-0.5 py-[2px] rounded overflow-hidden whitespace-nowrap bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 font-medium">
                    {holidayMap[ds]}
                  </div>
                )}
                {dayTasks.slice(0, holidayMap[ds] ? MAX_PILLS - 1 : MAX_PILLS).map(t => (
                  <div
                    key={t.id}
                    className={`text-[11px] leading-tight px-0.5 py-[2px] rounded overflow-hidden whitespace-nowrap ${
                      PRI_CLS[t.priority] || 'bg-charcoal-200 dark:bg-charcoal-700 text-charcoal-700 dark:text-charcoal-300'
                    }`}
                    onClick={e => {
                      const now = Date.now()
                      const last = lastTaskClick.current[t.id] || 0
                      lastTaskClick.current[t.id] = now
                      if (now - last < 400) {
                        e.stopPropagation()
                        onEditTask?.(t)
                      }
                    }}
                  >
                    {t.recurrence && '↻ '}
                    {t.type === 'appointment' ? '📅 ' : ''}
                    {t.title}
                  </div>
                ))}
                {overflow > 0 && (
                  <div className="text-[11px] text-charcoal-400 dark:text-charcoal-500 px-0.5 leading-tight">
                    +{overflow} more
                  </div>
                )}
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}

export default function CalendarGrid({
  tasks,
  visibleTasks,
  events,
  year,
  month,
  selectedDay,
  onSelectDay,
  readOnly,
  onEditTask,
  onEditEvent,
  onAddTask,
  onAddEvent,
}) {
  const weekRows   = getWeekRows(year, month)
  const holidayMap = buildHolidayMap(year)

  const selectedEvents  = selectedDay
    ? events.filter(ev => ev.start_date <= selectedDay && (ev.end_date || ev.start_date) >= selectedDay)
    : []
  const selectedTasks   = selectedDay ? tasks.filter(t => t.due_date === selectedDay) : []
  const selectedHoliday = selectedDay ? holidayMap[selectedDay] : null

  return (
    <div>
      {/* Grid frame: outer border + row dividers via divide-y */}
      <div className="border border-charcoal-200 dark:border-charcoal-700 divide-y divide-charcoal-200 dark:divide-charcoal-700 overflow-hidden">
        {/* Day-of-week headers */}
        <div className="grid grid-cols-7">
          {DAYS.map(d => (
            <div key={d} className="text-center text-xs font-medium text-charcoal-400 dark:text-charcoal-500 py-2">
              {d}
            </div>
          ))}
        </div>

        {/* Week rows */}
        {weekRows.map(row => (
          <WeekRow
            key={row.rowStart}
            dates={row.dates}
            events={events}
            visibleTasks={visibleTasks}
            year={year}
            month={month}
            selectedDay={selectedDay}
            onSelectDay={onSelectDay}
            readOnly={readOnly}
            onEditEvent={onEditEvent}
            onEditTask={onEditTask}
            holidayMap={holidayMap}
          />
        ))}
      </div>

      {/* Scrollable day detail panel */}
      {selectedDay && (
        <div className="px-4 md:px-0 border-t-2 border-orange-400 mt-1 pt-3">
          <div className="flex items-center gap-3 mb-3">
            <h3 className="font-semibold text-sm flex-1">
              {new Date(selectedDay + 'T12:00:00').toLocaleDateString('en-US', {
                weekday: 'long', month: 'long', day: 'numeric',
              })}
            </h3>
            {!readOnly && (
              <div className="flex gap-3 shrink-0">
                <button
                  onClick={onAddEvent}
                  className="text-xs font-medium hover:underline"
                  style={{ color: '#3b82f6' }}
                >
                  + Event
                </button>
                <button
                  onClick={onAddTask}
                  className="text-xs text-orange-500 font-medium hover:underline"
                >
                  + Task
                </button>
              </div>
            )}
          </div>

          <div className="overflow-y-auto" style={{ maxHeight: '50vh' }}>
            {!selectedHoliday && selectedEvents.length === 0 && selectedTasks.length === 0 && (
              <p className="text-sm text-charcoal-400 dark:text-charcoal-500">Nothing scheduled this day.</p>
            )}

            {/* Holiday banner */}
            {selectedHoliday && (
              <div className="flex items-center gap-2 mb-3 px-2 py-1.5 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800">
                <span className="text-base">🎉</span>
                <span className="text-sm font-medium text-amber-700 dark:text-amber-400">{selectedHoliday}</span>
              </div>
            )}

            {selectedEvents.length > 0 && (
              <div className="space-y-1 mb-3">
                <p className="text-xs font-medium text-charcoal-400 dark:text-charcoal-500 uppercase tracking-wide">Events</p>
                {selectedEvents.map(ev => (
                  <div
                    key={ev.id}
                    className={`flex items-center gap-3 py-1.5 rounded-lg px-2 -mx-2 ${
                      !readOnly ? 'cursor-pointer hover:bg-charcoal-50 dark:hover:bg-charcoal-800' : ''
                    }`}
                    onClick={!readOnly ? () => onEditEvent?.(ev) : undefined}
                  >
                    <span
                      className="w-2.5 h-2.5 rounded-full shrink-0"
                      style={{ backgroundColor: EVENT_COLORS[ev.color] || '#3b82f6' }}
                    />
                    <span className="flex-1 text-sm">{ev.title}</span>
                    {ev._household && <span className="text-xs shrink-0">{ev._poolEmoji || '🏠'}</span>}
                    {ev.created_by && (
                      <span className="text-xs text-charcoal-400 shrink-0">{ev.created_by}</span>
                    )}
                    {ev.end_date && ev.end_date !== ev.start_date && (
                      <span className="text-xs text-charcoal-400 shrink-0 hidden sm:block">
                        {ev.start_date} – {ev.end_date}
                      </span>
                    )}
                    {!ev.all_day && ev.start_time && (
                      <span className="text-xs text-charcoal-400 shrink-0">{ev.start_time}</span>
                    )}
                  </div>
                ))}
              </div>
            )}

            {selectedTasks.length > 0 && (
              <div className="space-y-1">
                {selectedEvents.length > 0 && (
                  <p className="text-xs font-medium text-charcoal-400 dark:text-charcoal-500 uppercase tracking-wide">Tasks</p>
                )}
                {selectedTasks.map(task => (
                  <div
                    key={task.id}
                    className={`flex items-center gap-3 py-1.5 rounded-lg px-2 -mx-2 ${
                      !readOnly ? 'cursor-pointer hover:bg-charcoal-50 dark:hover:bg-charcoal-800' : ''
                    }`}
                    onClick={!readOnly ? () => onEditTask?.(task) : undefined}
                  >
                    <div className={`w-2 h-2 rounded-full shrink-0 ${
                      task.priority === 'High'   ? 'bg-orange-500' :
                      task.priority === 'Medium' ? 'bg-yellow-400' :
                                                   'bg-charcoal-300 dark:bg-charcoal-600'
                    }`} />
                    <span className={`flex-1 text-sm ${task.status !== 'pending' ? 'line-through text-charcoal-400' : ''}`}>
                      {task.recurrence && '↻ '}{task.title}
                    </span>
                    {task.created_by && (
                      <span className="text-xs text-charcoal-400 shrink-0">{task.created_by}</span>
                    )}
                    {task.priority && (
                      <span className={`text-xs px-1.5 py-0.5 rounded font-medium shrink-0 ${PRI_CLS[task.priority] || ''}`}>
                        {task.priority}
                      </span>
                    )}
                    <span className={`badge text-xs shrink-0 ${catColor(task.category)}`}>{task.category}</span>
                    {task.due_time && (
                      <span className="text-xs text-charcoal-400 shrink-0">{task.due_time}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
