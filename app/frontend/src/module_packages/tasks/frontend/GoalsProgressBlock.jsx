import { TaskRow } from '../../../components/dashboard/blocks'

function Empty({ text }) {
  return <p className="text-sm text-charcoal-400 dark:text-charcoal-500">{text}</p>
}

export default function GoalsProgressBlock({ data, actions, onAction }) {
  const goals = data?.goals || []
  if (!goals.length) return <Empty text="No goals yet." />
  return <div className="space-y-2">{goals.map(g => <TaskRow key={g.id} task={g} actions={actions} onAction={onAction} />)}</div>
}
