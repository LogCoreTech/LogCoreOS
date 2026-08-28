import { AttachmentThumb } from '../../../components/assetDisplay'

function Empty({ text }) {
  return <p className="text-sm text-charcoal-400 dark:text-charcoal-500">{text}</p>
}

export default function DocumentsBlock({ data }) {
  const files = data?.attachments || []
  if (!files.length) return <Empty text="No attachments." />
  return (
    <div className="grid grid-cols-3 gap-2">
      {files.map(f => (
        <AttachmentThumb key={f.id} assetId={data.asset_id} file={f} canEdit={false} onDelete={() => {}} />
      ))}
    </div>
  )
}
