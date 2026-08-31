// Structured recurrence editor — mirrors the backend's RecurrenceRule shape
// (routers/_task_models.py): {freq, interval, weekdays?, month_day?, month_week?, month?}.
// Recurrence is create-only (see TaskModal.jsx — an existing recurring task shows its
// pattern read-only via describeRecurrence() instead of this picker), so this component
// only ever needs to handle "build a fresh rule," never "reconcile an in-flight edit."

import { useEffect } from 'react'

const FREQS = ['daily', 'weekly', 'monthly', 'yearly']
const WEEKDAYS = ['MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU']
const WEEKDAY_LABELS = { MO: 'Mon', TU: 'Tue', WE: 'Wed', TH: 'Thu', FR: 'Fri', SA: 'Sat', SU: 'Sun' }
const ORDINALS = [
  { value: 1, label: '1st' },
  { value: 2, label: '2nd' },
  { value: 3, label: '3rd' },
  { value: 4, label: '4th' },
  { value: -1, label: 'Last' },
]
const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

function toLocalDate(dateStr) {
  return dateStr ? new Date(`${dateStr}T00:00:00`) : new Date()
}

// JS Date.getDay(): 0=Sun..6=Sat — convert to our MO-first WEEKDAYS index.
function weekdayCodeFor(date) {
  return WEEKDAYS[(date.getDay() + 6) % 7]
}

function defaultRuleForFreq(freq, dueDate) {
  const d = toLocalDate(dueDate)
  if (freq === 'daily') return { freq: 'daily', interval: 1 }
  if (freq === 'weekly') return { freq: 'weekly', interval: 1, weekdays: [weekdayCodeFor(d)] }
  if (freq === 'monthly') return { freq: 'monthly', interval: 1, month_day: d.getDate() }
  return { freq: 'yearly', interval: 1, month: d.getMonth() + 1, month_day: d.getDate() }
}

export function describeRecurrence(rule) {
  if (!rule || !rule.freq) return ''
  const n = rule.interval || 1
  const every = n === 1 ? '' : `${n} `

  if (rule.freq === 'daily') return n === 1 ? 'Every day' : `Every ${n} days`

  if (rule.freq === 'weekly') {
    const days = (rule.weekdays || []).map(d => WEEKDAY_LABELS[d]).join(', ')
    return `Every ${every}week${n === 1 ? '' : 's'}${days ? ` on ${days}` : ''}`
  }

  const unit = rule.freq === 'monthly' ? `month${n === 1 ? '' : 's'}` : `year${n === 1 ? '' : 's'}`
  const monthPrefix = rule.freq === 'yearly' && rule.month ? `${MONTHS[rule.month - 1]}, ` : ''
  if (rule.month_week) {
    const ord = ORDINALS.find(o => o.value === rule.month_week.ordinal)?.label || ''
    return `Every ${every}${unit}, ${monthPrefix}on the ${ord} ${WEEKDAY_LABELS[rule.month_week.weekday]}`
  }
  if (rule.month_day != null) {
    const day = rule.month_day === -1 ? 'the last day' : `day ${rule.month_day}`
    return `Every ${every}${unit}, ${monthPrefix}on ${day}`
  }
  return `Every ${every}${unit}`
}

export default function RecurrencePicker({ value, onChange, dueDate }) {
  const rule = value || defaultRuleForFreq('daily', dueDate)

  // The picker always displays a real rule (falling back to a computed default), but
  // the parent form's own state must actually hold that default too — otherwise a user
  // who never touches a control still sees "Every day" on screen while submit() sends
  // null. Sync once, on mount, only when nothing's been set yet.
  useEffect(() => {
    if (!value) onChange(rule)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function patch(fields) {
    onChange({ ...rule, ...fields })
  }

  function toggleWeekday(code) {
    const current = rule.weekdays || []
    const next = current.includes(code) ? current.filter(w => w !== code) : [...current, code]
    patch({ weekdays: next })
  }

  const monthMode = rule.month_week ? 'week' : 'day'

  function setMonthMode(mode) {
    if (mode === 'day') patch({ month_week: null, month_day: rule.month_day ?? 1 })
    else patch({ month_day: null, month_week: rule.month_week || { ordinal: 1, weekday: 'MO' } })
  }

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-2">
        <select
          value={rule.freq}
          onChange={e => onChange(defaultRuleForFreq(e.target.value, dueDate))}
          className="input"
        >
          {FREQS.map(f => <option key={f} value={f}>{f[0].toUpperCase() + f.slice(1)}</option>)}
        </select>
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-charcoal-500 dark:text-charcoal-400 shrink-0">Every</span>
          <input
            type="number"
            min={1}
            max={365}
            value={rule.interval || 1}
            onChange={e => patch({ interval: Math.max(1, parseInt(e.target.value, 10) || 1) })}
            className="input !w-16 text-center"
          />
          <span className="text-xs text-charcoal-500 dark:text-charcoal-400 shrink-0">
            {rule.freq === 'daily' && 'day(s)'}
            {rule.freq === 'weekly' && 'week(s)'}
            {rule.freq === 'monthly' && 'month(s)'}
            {rule.freq === 'yearly' && 'year(s)'}
          </span>
        </div>
      </div>

      {rule.freq === 'weekly' && (
        <div className="flex gap-1">
          {WEEKDAYS.map(code => (
            <button
              key={code}
              type="button"
              onClick={() => toggleWeekday(code)}
              title={WEEKDAY_LABELS[code]}
              className={`flex-1 py-1 rounded-md text-[11px] font-medium transition-colors ${
                (rule.weekdays || []).includes(code)
                  ? 'bg-orange-500 text-white'
                  : 'bg-charcoal-100 dark:bg-charcoal-700 text-charcoal-600 dark:text-charcoal-300'
              }`}
            >
              {WEEKDAY_LABELS[code][0]}
            </button>
          ))}
        </div>
      )}

      {(rule.freq === 'monthly' || rule.freq === 'yearly') && (
        <>
          {rule.freq === 'yearly' && (
            <select
              value={rule.month || 1}
              onChange={e => patch({ month: parseInt(e.target.value, 10) })}
              className="input"
            >
              {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
            </select>
          )}

          <div className="flex gap-1 text-xs">
            <button
              type="button"
              onClick={() => setMonthMode('day')}
              className={`flex-1 py-1 rounded-md font-medium transition-colors ${
                monthMode === 'day'
                  ? 'bg-orange-500 text-white'
                  : 'bg-charcoal-100 dark:bg-charcoal-700 text-charcoal-600 dark:text-charcoal-300'
              }`}
            >
              On day
            </button>
            <button
              type="button"
              onClick={() => setMonthMode('week')}
              className={`flex-1 py-1 rounded-md font-medium transition-colors ${
                monthMode === 'week'
                  ? 'bg-orange-500 text-white'
                  : 'bg-charcoal-100 dark:bg-charcoal-700 text-charcoal-600 dark:text-charcoal-300'
              }`}
            >
              On the Nth weekday
            </button>
          </div>

          {monthMode === 'day' ? (
            <div className="flex items-center gap-2">
              <input
                type="number"
                min={1}
                max={31}
                disabled={rule.month_day === -1}
                value={rule.month_day === -1 ? '' : (rule.month_day || 1)}
                onChange={e =>
                  patch({ month_day: Math.min(31, Math.max(1, parseInt(e.target.value, 10) || 1)) })
                }
                className="input !w-16 text-center disabled:opacity-50"
              />
              <label className="flex items-center gap-1 text-xs text-charcoal-500 dark:text-charcoal-400">
                <input
                  type="checkbox"
                  checked={rule.month_day === -1}
                  onChange={e => patch({ month_day: e.target.checked ? -1 : 1 })}
                />
                Last day of month
              </label>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              <select
                value={rule.month_week?.ordinal ?? 1}
                onChange={e =>
                  patch({ month_week: { ...rule.month_week, ordinal: parseInt(e.target.value, 10) } })
                }
                className="input"
              >
                {ORDINALS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
              <select
                value={rule.month_week?.weekday || 'MO'}
                onChange={e => patch({ month_week: { ...rule.month_week, weekday: e.target.value } })}
                className="input"
              >
                {WEEKDAYS.map(code => <option key={code} value={code}>{WEEKDAY_LABELS[code]}</option>)}
              </select>
            </div>
          )}
        </>
      )}

      <p className="text-xs text-charcoal-500 dark:text-charcoal-400">{describeRecurrence(rule)}</p>
    </div>
  )
}
