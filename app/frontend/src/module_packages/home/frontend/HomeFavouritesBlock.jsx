export default function HomeFavouritesBlock({ data }) {
  const entities = data?.entities || []
  if (!entities.length) {
    return <p className="text-sm text-charcoal-400 dark:text-charcoal-500">No favourited devices.</p>
  }
  return (
    <div className="grid grid-cols-2 gap-2">
      {entities.map(e => (
        <div key={e.entity_id} className="p-2 rounded-lg border border-charcoal-200 dark:border-charcoal-700 bg-charcoal-50 dark:bg-charcoal-800">
          <p className="text-sm font-medium truncate">{e.attributes?.friendly_name || e.entity_id}</p>
          <p className="text-xs text-charcoal-500 dark:text-charcoal-400">{e.state}</p>
        </div>
      ))}
    </div>
  )
}
