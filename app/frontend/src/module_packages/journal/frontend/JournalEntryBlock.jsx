function Empty({ text }) {
  return <p className="text-sm text-charcoal-400 dark:text-charcoal-500">{text}</p>
}

export default function JournalEntryBlock({ data }) {
  if (!data?.preview) return <Empty text="No entry for this date." />
  return (
    <div>
      <p className="text-xs text-charcoal-400 mb-1">{data.date}</p>
      <p className="text-sm whitespace-pre-wrap line-clamp-6">{data.preview}</p>
    </div>
  )
}
