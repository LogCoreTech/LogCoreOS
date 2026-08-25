import { BlockActionButtons } from '../../../components/dashboard/blocks'

function Empty({ text }) {
  return <p className="text-sm text-charcoal-400 dark:text-charcoal-500">{text}</p>
}

export default function StreaksBlock({ data, actions, onAction }) {
  const tasks = data?.tasks || []
  if (!tasks.length) return <Empty text="No active streaks." />
  return (
    <div className="space-y-2">
      {tasks.map(t => (
        <div key={t.id} className="flex items-center justify-between text-sm">
          <span className="truncate">{t.title}</span>
          <span className="text-orange-500 font-semibold shrink-0 ml-2">{t.streak_count} days</span>
          <BlockActionButtons actions={actions} recordKind="task" recordId={t.id} onDone={onAction} />
        </div>
      ))}
    </div>
  )
}
