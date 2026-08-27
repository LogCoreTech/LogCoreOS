import { BlockActionButtons } from '../../../components/dashboard/blocks'

function Empty({ text }) {
  return <p className="text-sm text-charcoal-400 dark:text-charcoal-500">{text}</p>
}

export default function NoteEmbedBlock({ data, actions, onAction }) {
  if (!data?.preview) return <Empty text="Note is empty." />
  return (
    <div className="flex flex-col gap-2 h-full">
      <p className="text-sm whitespace-pre-wrap line-clamp-6 flex-1">{data.preview}</p>
      {/* `ml-auto` on BlockActionButtons only affects the cross axis in a
          flex-col parent — needs its own row to actually sit right. */}
      <div className="flex justify-end">
        <BlockActionButtons actions={actions} recordKind="note" recordId={data.path} onDone={onAction} />
      </div>
    </div>
  )
}
