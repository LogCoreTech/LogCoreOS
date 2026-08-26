function priorityDot(p) {
  return p === 'High' ? 'bg-red-500' : p === 'Medium' ? 'bg-yellow-500' : 'bg-charcoal-400'
}

function Empty({ text }) {
  return <p className="text-sm text-charcoal-400 dark:text-charcoal-500">{text}</p>
}

export default function TeamTasksBlock({ data }) {
  const tasks = data?.tasks || []
  if (!tasks.length) return <Empty text="No pending pool tasks." />
  return (
    <div className="space-y-2">
      {tasks.map(t => (
        <div key={t.id} className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full shrink-0 ${priorityDot(t.priority)}`} />
          <span className="text-sm truncate flex-1">{t.title}</span>
          {t.assigned_to && <span className="text-xs text-charcoal-400 shrink-0">{t.assigned_to}</span>}
        </div>
      ))}
    </div>
  )
}
