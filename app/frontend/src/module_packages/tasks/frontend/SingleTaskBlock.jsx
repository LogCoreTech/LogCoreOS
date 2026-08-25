import { TaskRow } from '../../../components/dashboard/blocks'

export default function SingleTaskBlock({ data, actions, onAction }) {
  const task = data?.task
  if (!task) return <p className="text-sm text-charcoal-400 dark:text-charcoal-500">Task not found.</p>
  return <TaskRow task={task} actions={actions} onAction={onAction} />
}
