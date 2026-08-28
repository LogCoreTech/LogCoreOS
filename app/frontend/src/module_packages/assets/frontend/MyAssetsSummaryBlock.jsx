function Empty({ text }) {
  return <p className="text-sm text-charcoal-400 dark:text-charcoal-500">{text}</p>
}

export default function MyAssetsSummaryBlock({ data }) {
  const counts = data?.counts || {}
  const entries = Object.entries(counts)
  if (!entries.length) return <Empty text="No assets yet." />
  return (
    <div className="space-y-1.5">
      {entries.map(([key, count]) => (
        <div key={key} className="flex items-center justify-between text-sm">
          <span className="truncate">{key || '(untyped)'}</span>
          <span className="text-charcoal-400 shrink-0">{count}</span>
        </div>
      ))}
    </div>
  )
}
