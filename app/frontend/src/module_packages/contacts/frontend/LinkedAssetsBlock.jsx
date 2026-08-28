import { BlockActionButtons } from '../../../components/dashboard/blocks'

function Empty({ text }) {
  return <p className="text-sm text-charcoal-400 dark:text-charcoal-500">{text}</p>
}

export default function LinkedAssetsBlock({ data, actions, onAction }) {
  const assets = data?.assets || []
  if (!assets.length) return <Empty text="No linked assets." />
  return (
    <div className="space-y-1.5">
      {assets.map(a => (
        <div key={a.id} className="flex items-center gap-2 text-sm">
          <span className="shrink-0">{a.icon}</span>
          <span className="truncate flex-1">{a.name}</span>
          <BlockActionButtons actions={actions} recordKind="asset" recordId={a.id} onDone={onAction} />
        </div>
      ))}
    </div>
  )
}
