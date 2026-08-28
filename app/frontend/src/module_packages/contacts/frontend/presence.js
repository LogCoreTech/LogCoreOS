// Shared by ContactAvatar's presence popover — a coarse "last seen" label.
// Owner spec (2026-08-17): the first hour counts by the minute, then once
// it's past an hour switch to hours only (no more minutes), then once it's
// past a day switch to days only and just keep counting days forever — no
// upper cap, no falling back to an absolute date.
export function formatLastSeen(isoString) {
  if (!isoString) return 'Never online'
  const seen = new Date(isoString)
  if (Number.isNaN(seen.getTime())) return 'Never online'
  const seconds = Math.max(0, Math.floor((Date.now() - seen.getTime()) / 1000))
  const minutes = Math.floor(seconds / 60)
  if (minutes < 1) return 'Online just now'
  if (minutes < 60) return `Last seen ${minutes} min ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `Last seen ${hours} hr ago`
  const days = Math.floor(hours / 24)
  return `Last seen ${days} day${days === 1 ? '' : 's'} ago`
}
