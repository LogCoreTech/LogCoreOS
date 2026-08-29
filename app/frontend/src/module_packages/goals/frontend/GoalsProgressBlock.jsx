function Empty({ text }) {
  return <p className="text-sm text-charcoal-400 dark:text-charcoal-500">{text}</p>
}

export default function GoalsProgressBlock({ data }) {
  const goals = data?.goals || []
  if (!goals.length) return <Empty text="No goals yet." />
  return (
    <div className="space-y-3">
      {goals.map(g => {
        const pct = g.progress?.pct ?? 0
        return (
          <div key={g.id}>
            <div className="flex items-center justify-between text-sm mb-1">
              <span className="truncate">{g.title}</span>
              <span className="text-orange-500 font-semibold shrink-0 ml-2">{pct}%</span>
            </div>
            <div className="h-1.5 bg-charcoal-200 dark:bg-charcoal-700 rounded-full overflow-hidden">
              <div className="h-full bg-orange-500 rounded-full transition-all duration-500" style={{ width: `${pct}%` }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}
