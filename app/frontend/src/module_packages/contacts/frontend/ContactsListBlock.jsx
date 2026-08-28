import { BlockActionButtons } from '../../../components/dashboard/blocks'

function Empty({ text }) {
  return <p className="text-sm text-charcoal-400 dark:text-charcoal-500">{text}</p>
}

// New block type (2026-08-15) — the dashboard had no general "list of
// contacts" block before this; linked_deals/linked_assets are scoped to one
// contact/asset's own related records, not a standalone contacts list.
export default function ContactsListBlock({ data, actions, onAction }) {
  const contacts = data?.contacts || []
  if (!contacts.length) return <Empty text="No contacts." />
  return (
    <div className="space-y-1.5">
      {contacts.map(c => (
        <div key={c.id} className="flex items-center gap-2 text-sm">
          <span className="shrink-0">{c.type === 'company' ? '🏢' : '🧑'}</span>
          <span className="truncate flex-1">{c.name}</span>
          <BlockActionButtons actions={actions} recordKind="contact" recordId={c.id} onDone={onAction} />
        </div>
      ))}
    </div>
  )
}
