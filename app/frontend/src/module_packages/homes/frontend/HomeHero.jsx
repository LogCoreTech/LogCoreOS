// A real banner, not a compact card — deliberately more visual weight than
// dashboard/frontend/DashboardHero.jsx (that one's a minimal subject-banner
// for a different purpose). Owner feedback on the first design pass: Homes
// shouldn't read as "a dashboard with a list on it" — this is the piece
// that gives each house its own identity at a glance.
export default function HomeHero({ home }) {
  const isRent = home.ownership_type === 'rent'

  return (
    <div className="card p-5 flex items-center gap-4 bg-gradient-to-br from-orange-50 to-transparent dark:from-orange-900/10">
      <span className="w-16 h-16 rounded-2xl bg-orange-500 text-white flex items-center justify-center text-3xl shrink-0">
        {home.icon || '🏘️'}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <h1 className="text-xl font-bold truncate">{home.name}</h1>
          <span
            className={`text-xs px-2 py-0.5 rounded-full font-medium shrink-0 ${
              isRent
                ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
                : 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
            }`}
          >
            {isRent ? '🔑 Renting' : '🏡 Owned'}
          </span>
        </div>
        {home.address && (
          <p className="text-sm text-charcoal-500 dark:text-charcoal-400 truncate mt-0.5">{home.address}</p>
        )}
      </div>
    </div>
  )
}
