export default function InboxSummaryBlock({ data }) {
  return (
    <div className="text-sm">
      <p><span className="text-orange-500 font-semibold">{data?.new_count ?? 0}</span> new item{(data?.new_count ?? 0) === 1 ? '' : 's'}</p>
      <p className="text-charcoal-400 text-xs">{data?.total ?? 0} total in inbox</p>
    </div>
  )
}
