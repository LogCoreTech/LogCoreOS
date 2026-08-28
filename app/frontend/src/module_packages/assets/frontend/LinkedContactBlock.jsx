import { Link } from 'react-router-dom'

function Empty({ text }) {
  return <p className="text-sm text-charcoal-400 dark:text-charcoal-500">{text}</p>
}

export default function LinkedContactBlock({ data }) {
  const ids = data?.contact_ids || []
  if (!ids.length) return <Empty text="No linked contact." />
  return (
    <div className="space-y-1">
      {ids.map(id => (
        <Link key={id} to={`/contacts?contact=${id}`} className="text-sm text-orange-500 hover:underline block">
          View contact →
        </Link>
      ))}
    </div>
  )
}
