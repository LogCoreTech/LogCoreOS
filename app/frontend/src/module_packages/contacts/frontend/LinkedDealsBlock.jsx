function Empty({ text }) {
  return <p className="text-sm text-charcoal-400 dark:text-charcoal-500">{text}</p>
}

export default function LinkedDealsBlock({ data }) {
  const deals = data?.deals || []
  if (!deals.length) return <Empty text="No deals." />
  return (
    <div className="space-y-1.5">
      {deals.map(d => (
        <div key={d.id} className="flex items-center justify-between text-sm">
          <span className="truncate">{d.title}</span>
          <span className="badge shrink-0 ml-2">{d.stage}</span>
        </div>
      ))}
    </div>
  )
}
