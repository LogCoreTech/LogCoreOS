// Pairs with lib/usePullToRefresh.js — a small spinner area that grows in
// from the top of a page as the user pulls down, then spins while the
// refresh is in flight. Purely presentational; each page passes through the
// values its own usePullToRefresh() call returns.
export default function PullToRefreshIndicator({ pullDistance, refreshing, threshold }) {
  const height = refreshing ? threshold : pullDistance
  if (height <= 0) return null

  const progress = Math.min(1, height / threshold)

  return (
    <div
      className="flex items-center justify-center overflow-hidden transition-[height] duration-200"
      style={{ height }}
      aria-hidden={!refreshing}
      role={refreshing ? 'status' : undefined}
      aria-label={refreshing ? 'Refreshing' : undefined}
    >
      <span
        className={`inline-block w-5 h-5 border-2 border-orange-500 rounded-full ${
          refreshing ? 'animate-spin border-t-transparent' : ''
        }`}
        style={refreshing ? undefined : { opacity: progress, transform: `rotate(${progress * 360}deg)`, borderTopColor: 'transparent' }}
      />
    </div>
  )
}
