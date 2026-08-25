import { BlockActionButtons } from '../../../components/dashboard/blocks'

function Empty({ text }) {
  return <p className="text-sm text-charcoal-400 dark:text-charcoal-500">{text}</p>
}

export default function UpcomingEventsBlock({ data, actions, onAction }) {
  const events = data?.events || []
  if (!events.length) return <Empty text="No upcoming events." />
  return (
    <div className="space-y-2">
      {events.map(e => (
        <div key={e.id} className="flex items-center justify-between text-sm gap-2">
          <span className="truncate flex-1">{e.title}</span>
          <span className="text-xs text-charcoal-400 shrink-0">{e.date}</span>
          <BlockActionButtons actions={actions} recordKind="event" recordId={e.id} onDone={onAction} />
        </div>
      ))}
    </div>
  )
}
