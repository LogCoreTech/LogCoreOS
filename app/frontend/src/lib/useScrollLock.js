import { useEffect } from 'react'

// Real bug reported 2026-09-05: confirmation dialogs "attach to whatever
// page they're on" instead of staying fixed, and the background keeps
// scrolling while one is open. Locks the app's single scrollable container
// (`<main>`, components/Layout.jsx — the same well-known node
// usePullToRefresh.js already targets) while `active`.
//
// Module-level reference count, not per-hook-instance state: a dialog can
// open on top of an already-open modal (e.g. a "Discard changes?" confirm
// over an edit form), and each independently calls this hook — only the
// LAST one to unmount should actually restore scroll, or closing the inner
// one would silently re-enable scrolling while the outer one is still open.
let lockCount = 0
let previousOverflow = null

function lock() {
  const main = document.querySelector('main')
  if (lockCount === 0 && main) {
    previousOverflow = main.style.overflow
    main.style.overflow = 'hidden'
  }
  lockCount++
}

function unlock() {
  lockCount = Math.max(0, lockCount - 1)
  if (lockCount === 0) {
    const main = document.querySelector('main')
    if (main) main.style.overflow = previousOverflow || ''
    previousOverflow = null
  }
}

export default function useScrollLock(active = true) {
  useEffect(() => {
    if (!active) return
    lock()
    return unlock
  }, [active])
}
