import { TaskRow } from '../../../components/dashboard/blocks'

function Empty({ text }) {
  return <p className="text-sm text-charcoal-400 dark:text-charcoal-500">{text}</p>
}

export default function DueTodayBlock({ data, actions, onAction }) {
  const tasks = data?.tasks || []
  if (!tasks.length) return <Empty text="Nothing due today." />
  return <div className="space-y-2">{tasks.map(t => <TaskRow key={t.id} task={t} actions={actions} onAction={onAction} />)}</div>
}
