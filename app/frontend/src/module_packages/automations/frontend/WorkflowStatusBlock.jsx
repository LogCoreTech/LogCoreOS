export default function WorkflowStatusBlock({ data }) {
  const wf = data?.workflow
  if (!wf) {
    return <p className="text-sm text-charcoal-400 dark:text-charcoal-500">Workflow not found.</p>
  }
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="truncate">{wf.name}</span>
      <span className={`badge shrink-0 ml-2 ${wf.active ? 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300' : ''}`}>
        {wf.active ? 'active' : 'inactive'}
      </span>
    </div>
  )
}
