import { useEffect, useRef, useState } from 'react'

// Pull-to-refresh (item #32's other half, 2026-09-04 UX Polish Batch — the
// diff-based refresh fix itself already shipped; this is the mobile-only
// gesture that was tracked alongside it, since desktop has no equivalent
// input). No gesture library exists in this app and this is a small, well-
// understood amount of touch-event math, so it's hand-rolled rather than a
// new dependency.
//
// `<main>` (components/Layout.jsx) is the single scrollable container for
// most pages — reached via document.querySelector rather than a ref threaded
// through context, the same "well-known singleton DOM node" shortcut
// Toast/ConfirmDialog already take via createPortal(..., document.body). A
// page that manages its own nested scroll region instead of scrolling via
// `<main>` can pass `containerRef` to target that element specifically —
// `main.scrollTop` would otherwise always read 0 there and the gesture would
// fire on nearly every downward drag. `enabled` lets a page turn the gesture
// off while one of its own touch/pointer interactions is active (e.g.
// Dashboard.jsx's own block drag-resize, only while `editing` is true) to
// avoid two gesture recognizers fighting over the same touch.
// Touch-only (touchstart/touchmove/touchend) is what naturally keeps this
// mobile-only — desktop mouse drags never fire these events, so no viewport
// check is needed.
//
// Deliberately NOT wired into Notes.jsx: its file-tree pane already has its
// own pointer-based drag-to-reorder (`onNotePointerDown`), and Pointer/Touch
// events both fire for the same physical gesture — a drag starting at the
// very top of the tree would be ambiguous with a pull-to-refresh attempt.
// Needs its own conflict-resolution design, not a bolted-on fix here.
export default function usePullToRefresh(onRefresh, { threshold = 70, containerRef, enabled = true } = {}) {
  const [pullDistance, setPullDistance] = useState(0)
  const [refreshing, setRefreshing] = useState(false)
  const startYRef = useRef(null)
  const activeRef = useRef(false)
  const distanceRef = useRef(0)
  const refreshingRef = useRef(false)
  // Always the latest onRefresh without re-subscribing listeners mid-gesture.
  const onRefreshRef = useRef(onRefresh)
  onRefreshRef.current = onRefresh

  useEffect(() => {
    if (!enabled) return
    const main = containerRef?.current || document.querySelector('main')
    if (!main) return

    function onTouchStart(e) {
      if (refreshingRef.current || main.scrollTop > 0) {
        activeRef.current = false
        return
      }
      activeRef.current = true
      startYRef.current = e.touches[0].clientY
    }

    function onTouchMove(e) {
      if (!activeRef.current) return
      const delta = e.touches[0].clientY - startYRef.current
      if (delta <= 0) {
        // Stays "active" — a little upward jitter before the real downward
        // pull shouldn't permanently cancel the gesture for the rest of this
        // touch. Only touchend (or starting off the top) truly ends it.
        distanceRef.current = 0
        setPullDistance(0)
        return
      }
      // Elastic resistance (sqrt-damped) so the indicator doesn't track the
      // finger 1:1 — matches the native iOS/Android pull-to-refresh feel.
      const damped = Math.min(threshold * 1.6, Math.sqrt(delta) * 8)
      distanceRef.current = damped
      setPullDistance(damped)
    }

    async function onTouchEnd() {
      if (!activeRef.current) return
      activeRef.current = false
      if (distanceRef.current < threshold) {
        distanceRef.current = 0
        setPullDistance(0)
        return
      }
      refreshingRef.current = true
      setRefreshing(true)
      setPullDistance(threshold)
      try {
        await onRefreshRef.current()
      } finally {
        refreshingRef.current = false
        setRefreshing(false)
        distanceRef.current = 0
        setPullDistance(0)
      }
    }

    main.addEventListener('touchstart', onTouchStart, { passive: true })
    main.addEventListener('touchmove', onTouchMove, { passive: true })
    main.addEventListener('touchend', onTouchEnd)
    return () => {
      main.removeEventListener('touchstart', onTouchStart)
      main.removeEventListener('touchmove', onTouchMove)
      main.removeEventListener('touchend', onTouchEnd)
    }
    // containerRef is a stable ref object across renders (React guarantee),
    // so including it here never causes extra re-subscriptions.
  }, [threshold, enabled, containerRef])

  return { pullDistance, refreshing, threshold }
}
