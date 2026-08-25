import { TaskRow } from '../../../components/dashboard/blocks'

function Empty({ text }) {
  return <p className="text-sm text-charcoal-400 dark:text-charcoal-500">{text}</p>
}

export default function Top3TasksBlock({ data, actions, onAction }) {
  const tasks = data?.tasks || []
  if (!tasks.length) return <Empty text="No pending tasks." />
  return (
    <ol className="space-y-2">
      {tasks.map((t, i) => (
        <li key={t.id} className="flex items-center gap-2">
          <span className="text-orange-500 font-bold text-sm w-4 shrink-0">{i + 1}</span>
          <TaskRow task={t} actions={actions} onAction={onAction} />
        </li>
      ))}
    </ol>
  )
}
