// Simple inline-SVG line chart for a dated numeric series (a goal's manual
// metric log: [{date, value}], already sorted by date server-side). No
// charting library — this app has none, and a few dozen points don't need
// one. Points are evenly spaced by index (not date-proportional) so
// irregular logging gaps don't compress the line into an unreadable corner.

const WIDTH = 300
const HEIGHT = 120
const PAD_X = 8
const PAD_Y = 12

function formatShortDate(dateStr) {
  const d = new Date(`${dateStr}T00:00:00`)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export default function MetricGraph({ entries = [], target }) {
  if (entries.length < 2) {
    return (
      <p className="text-xs text-charcoal-400 py-4 text-center">
        Log a few values to see a trend line.
      </p>
    )
  }

  const values = entries.map(e => e.value)
  const allValues = target != null ? [...values, target] : values
  const rawMin = Math.min(...allValues)
  const rawMax = Math.max(...allValues)
  const span = rawMax - rawMin || 1
  const min = rawMin - span * 0.1
  const max = rawMax + span * 0.1

  const innerW = WIDTH - PAD_X * 2
  const innerH = HEIGHT - PAD_Y * 2

  function x(i) {
    return PAD_X + (entries.length === 1 ? innerW / 2 : (i / (entries.length - 1)) * innerW)
  }
  function y(v) {
    return PAD_Y + innerH - ((v - min) / (max - min)) * innerH
  }

  const linePoints = entries.map((e, i) => `${x(i)},${y(e.value)}`).join(' ')

  return (
    <div>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full" preserveAspectRatio="none" style={{ height: '120px' }}>
        {/* reference lines: max / mid / min */}
        {[max - span * 0.1, (min + max) / 2, min + span * 0.1].map((v, i) => (
          <line key={i} x1={PAD_X} x2={WIDTH - PAD_X} y1={y(v)} y2={y(v)} className="stroke-charcoal-100 dark:stroke-charcoal-700" strokeWidth="1" />
        ))}

        {target != null && (
          <line
            x1={PAD_X} x2={WIDTH - PAD_X} y1={y(target)} y2={y(target)}
            className="stroke-orange-400"
            strokeWidth="1"
            strokeDasharray="3,3"
          />
        )}

        <polyline points={linePoints} fill="none" className="stroke-orange-500" strokeWidth="2" />

        {entries.map((e, i) => (
          <circle key={e.date} cx={x(i)} cy={y(e.value)} r="2.5" className="fill-orange-500">
            <title>{`${e.date} — ${e.value}`}</title>
          </circle>
        ))}
      </svg>
      <div className="flex items-center justify-between text-[10px] text-charcoal-400 mt-1">
        <span>{formatShortDate(entries[0].date)}</span>
        {target != null && <span className="text-orange-400">- - - target: {target}</span>}
        <span>{formatShortDate(entries[entries.length - 1].date)}</span>
      </div>
    </div>
  )
}
