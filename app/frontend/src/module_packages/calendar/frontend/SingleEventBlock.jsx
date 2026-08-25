import { BlockActionButtons } from '../../../components/dashboard/blocks'

export default function SingleEventBlock({ data, actions, onAction }) {
  const e = data?.event
  if (!e) return <p className="text-sm text-charcoal-400 dark:text-charcoal-500">Event not found.</p>
  return (
    <div className="flex items-start justify-between gap-2">
      <div className="min-w-0">
        <p className="text-sm font-medium truncate">{e.title}</p>
        <p className="text-xs text-charcoal-400">{e.date}</p>
        {e.notes && <p className="text-xs text-charcoal-500 mt-1">{e.notes}</p>}
      </div>
      <BlockActionButtons actions={actions} recordKind="event" recordId={e.id} onDone={onAction} />
    </div>
  )
}
