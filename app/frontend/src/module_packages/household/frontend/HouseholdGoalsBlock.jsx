function Empty({ text }) {
  return <p className="text-sm text-charcoal-400 dark:text-charcoal-500">{text}</p>
}

export default function HouseholdGoalsBlock({ data }) {
  const goals = data?.goals || []
  if (!goals.length) return <Empty text="No household goals yet." />
  return (
    <div className="space-y-2">
      {goals.map(g => (
        <div key={g.id} className="flex items-center gap-2">
          <span className="text-sm truncate flex-1">{g.title}</span>
          <span className="text-xs text-charcoal-400 shrink-0">{g.progress?.pct ?? 0}%</span>
        </div>
      ))}
    </div>
  )
}
