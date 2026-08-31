import { useState } from 'react'

// Generic, dumb month/year calendar for visualizing dated history data
// (a task's completion_log, a goal's manual-metric log, ...). Knows nothing
// about tasks or goals — callers build entriesByDate entirely themselves.
// Month-grid date math mirrors components/CalendarGrid.jsx's own
// getWeekRows() (Sunday-first, variable row count per month's real layout —
// not a fixed 6-row grid) for visual consistency with the rest of the app.

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

function fmt(y, m, d) {
  const dt = new Date(y, m, d)
  return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`
}

function getWeekRows(year, month) {
  const firstDay = new Date(year, month, 1).getDay()
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const lastDay = new Date(year, month, daysInMonth).getDay()

  const allDates = []
  for (let i = 0; i < firstDay; i++) allDates.push(fmt(year, month, 1 - firstDay + i))
  for (let d = 1; d <= daysInMonth; d++) allDates.push(fmt(year, month, d))
  for (let i = 1; i <= (6 - lastDay); i++) allDates.push(fmt(year, month, daysInMonth + i))

  const rows = []
  for (let i = 0; i < allDates.length; i += 7) rows.push(allDates.slice(i, i + 7))
  return rows
}

// GitHub-contribution-style year strip: 7 rows (Sun-Sat) x ~53 columns (one
// per week), spanning the first Sunday on/before Jan 1 through the last
// Saturday on/after Dec 31 of the given year.
function getYearColumns(year) {
  const jan1 = new Date(year, 0, 1)
  const start = new Date(jan1)
  start.setDate(start.getDate() - jan1.getDay())
  const dec31 = new Date(year, 11, 31)

  const columns = []
  const cursor = new Date(start)
  while (cursor <= dec31) {
    const col = []
    for (let i = 0; i < 7; i++) {
      col.push({ date: fmt(cursor.getFullYear(), cursor.getMonth(), cursor.getDate()), inYear: cursor.getFullYear() === year })
      cursor.setDate(cursor.getDate() + 1)
    }
    columns.push(col)
  }
  return columns
}

function Cell({ date, entriesByDate, dim, size = 'w-full aspect-square' }) {
  const entry = entriesByDate[date]
  const color = entry?.colorClass || 'bg-charcoal-50 dark:bg-charcoal-800'
  return (
    <div
      title={entry?.title || date}
      className={`${size} rounded-sm flex items-center justify-center text-[8px] leading-none ${color} ${dim ? 'opacity-30' : ''}`}
    >
      {entry?.label || ''}
    </div>
  )
}

export default function HistoryCalendar({ entriesByDate = {}, legend }) {
  const today = new Date()
  const [view, setView] = useState('month')
  const [cursor, setCursor] = useState(new Date(today.getFullYear(), today.getMonth(), 1))

  const year = cursor.getFullYear()
  const month = cursor.getMonth()

  function step(delta) {
    setCursor(prev =>
      view === 'month'
        ? new Date(prev.getFullYear(), prev.getMonth() + delta, 1)
        : new Date(prev.getFullYear() + delta, prev.getMonth(), 1)
    )
  }

  const periodLabel =
    view === 'month'
      ? cursor.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
      : String(year)

  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <button type="button" onClick={() => step(-1)} className="text-charcoal-400 hover:text-charcoal-700 dark:hover:text-charcoal-200 px-1">‹</button>
        <span className="text-xs font-medium">{periodLabel}</span>
        <button type="button" onClick={() => step(1)} className="text-charcoal-400 hover:text-charcoal-700 dark:hover:text-charcoal-200 px-1">›</button>
      </div>

      <div className="flex justify-center mb-2">
        <div className="inline-flex bg-charcoal-100 dark:bg-charcoal-700 rounded-full p-0.5 text-[11px]">
          {['month', 'year'].map(v => (
            <button
              key={v}
              type="button"
              onClick={() => setView(v)}
              className={`px-2.5 py-0.5 rounded-full font-medium capitalize transition-colors ${
                view === v
                  ? 'bg-white dark:bg-charcoal-600 text-charcoal-900 dark:text-gray-100 shadow-sm'
                  : 'text-charcoal-500 dark:text-charcoal-400'
              }`}
            >
              {v}
            </button>
          ))}
        </div>
      </div>

      {view === 'month' ? (
        <>
          <div className="grid grid-cols-7 gap-1 text-center text-[10px] text-charcoal-400 mb-1">
            {DAYS.map(d => <div key={d}>{d[0]}</div>)}
          </div>
          <div className="grid grid-cols-7 gap-1">
            {getWeekRows(year, month).flat().map(date => (
              <Cell key={date} date={date} entriesByDate={entriesByDate} dim={date.slice(0, 7) !== `${year}-${String(month + 1).padStart(2, '0')}`} />
            ))}
          </div>
        </>
      ) : (
        <div className="overflow-x-auto">
          <div className="inline-flex gap-[3px]" style={{ minWidth: 'max-content' }}>
            {getYearColumns(year).map((col, i) => (
              <div key={i} className="flex flex-col gap-[3px]">
                {col.map(({ date, inYear }) => (
                  <Cell key={date} date={date} entriesByDate={entriesByDate} dim={!inYear} size="w-2.5 h-2.5" />
                ))}
              </div>
            ))}
          </div>
        </div>
      )}

      {legend && legend.length > 0 && (
        <div className="flex items-center gap-3 mt-2 text-[11px] text-charcoal-500 dark:text-charcoal-400 flex-wrap">
          {legend.map(l => (
            <span key={l.label} className="flex items-center gap-1">
              <span className={`w-2.5 h-2.5 rounded-sm inline-block ${l.colorClass}`} />
              {l.label}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
