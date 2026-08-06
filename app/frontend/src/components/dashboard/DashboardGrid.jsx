import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Responsive, WidthProvider } from 'react-grid-layout'
import 'react-grid-layout/css/styles.css'
import 'react-resizable/css/styles.css'
import BlockRenderer from './BlockRenderer'

const ResponsiveGridLayout = WidthProvider(Responsive)

// Mobile now gets full drag/resize too, same as desktop — owner-confirmed
// choice, made knowing this app has a documented history of iOS-standalone-
// PWA-only touch/scroll bugs (see docs/MEMORY.md) that Chromium/Playwright
// has never been able to verify.
export const MOBILE_COLS = 12

// Floor so a drag-resize can't shrink a block below its own header chrome
// (icon + label + edit/remove buttons) at the finer grid scale. Same floor
// works for both breakpoints — see MOBILE_COLS's sibling comment in the plan
// this shipped from for the per-column-pixel-width parity reasoning.
const MIN_W = 4
const MIN_H = 3

const ROW_HEIGHT = 24
const MARGIN = [6, 6]
const COLS = { lg: 36, sm: MOBILE_COLS }
const LG_BREAKPOINT = 768

// Touch dragging is hand-rolled instead of using react-grid-layout's own
// (mouse-only-in-practice) instant drag: on touch, an editing block's whole
// card is the drag surface, and react-draggable has no concept of a start
// delay — it treats the first pixel of movement as a drag. That makes a
// normal swipe-to-scroll indistinguishable from "move this block" the moment
// edit mode is on (owner report, 2026-08-05: "so users can still swipe the
// whole screen to scroll while in edit mode"). Mouse is entirely unaffected
// by any of this — isDraggable={editing} below still drives instant mouse
// dragging through react-grid-layout exactly as before; this only intercepts
// `touchstart` (see onTouchStartCapture) and runs its own press-and-hold
// state machine in parallel. See docs/MEMORY.md for why react-draggable
// can't simply be "armed" mid-gesture (it decides handle/disabled at the
// original touchstart and never re-checks for the rest of that gesture).
const LONG_PRESS_MS = 550
const MOVE_CANCEL_PX = 10

export default function DashboardGrid({ blocks, editing, onRemoveBlock, onEditBlock, onBlockAction, onLayoutChange }) {
  const containerRef = useRef(null)
  const gestureRef = useRef(null)
  const [dragVisual, setDragVisual] = useState(null) // { id, dx, dy } while held/dragging

  // A committed touch-drag only ever reaches the parent as onLayoutChange ->
  // pendingLayouts (Dashboard.jsx doesn't apply it to `blocks` until "Save
  // Layout" is clicked) — so without a local echo here, `layouts` below still
  // reflects the pre-drag position and the block visually snaps back the
  // instant the drag ends. react-grid-layout's own mouse drag never has this
  // problem because it holds the dropped position in its own internal state;
  // this hand-rolled touch path needs to do that itself. Cleared whenever
  // `blocks` changes (Save Layout persisting, or switching dashboards) since
  // the server-authoritative data has caught up by then.
  const [localOverrides, setLocalOverrides] = useState({}) // { [bp]: { [blockId]: {x,y} } }
  useEffect(() => { setLocalOverrides({}) }, [blocks])

  const layouts = useMemo(() => {
    const build = (bp, defaultW, defaultH) => blocks.map(b => {
      const entry = {
        i: b.id,
        minW: MIN_W,
        minH: MIN_H,
        ...(b.layout?.[bp] || { x: 0, y: 0, w: defaultW, h: defaultH }),
      }
      const override = localOverrides[bp]?.[b.id]
      return override ? { ...entry, x: override.x, y: override.y } : entry
    })
    return { lg: build('lg', 12, 9), sm: build('sm', MOBILE_COLS, 9) }
  }, [blocks, localOverrides])

  const clearGesture = useCallback(() => {
    if (gestureRef.current?.timer) clearTimeout(gestureRef.current.timer)
    gestureRef.current = null
    setDragVisual(null)
  }, [])

  const commitDrag = useCallback(() => {
    const g = gestureRef.current
    if (!g || !g.armed) {
      clearGesture()
      return
    }
    const { breakpoint: bp } = g
    const list = layouts[bp]
    const moved = list.find(l => l.i === g.blockId)
    if (!moved) {
      clearGesture()
      return
    }
    const cols = COLS[bp]
    const deltaCols = Math.round(g.dx / g.colStep)
    const deltaRows = Math.round(g.dy / g.rowStep)
    const nextX = Math.min(Math.max(g.startX + deltaCols, 0), Math.max(cols - moved.w, 0))
    const nextY = Math.max(g.startY + deltaRows, 0)
    const overlaps = list.some(l => (
      l.i !== g.blockId &&
      nextX < l.x + l.w && nextX + moved.w > l.x &&
      nextY < l.y + l.h && nextY + moved.h > l.y
    ))
    if (!overlaps && (nextX !== g.startX || nextY !== g.startY)) {
      setLocalOverrides(prev => ({
        ...prev,
        [bp]: { ...prev[bp], [g.blockId]: { x: nextX, y: nextY } },
      }))
      const nextList = list.map(l => (l.i === g.blockId ? { ...l, x: nextX, y: nextY } : l))
      onLayoutChange?.({ ...layouts, [bp]: nextList })
    }
    clearGesture()
  }, [layouts, onLayoutChange, clearGesture])

  useEffect(() => {
    const el = containerRef.current
    if (!el || !editing) return undefined

    function onTouchStartCapture(e) {
      if (e.target.closest('.react-resizable-handle')) return
      const handleEl = e.target.closest('.block-drag-handle')
      if (!handleEl) return
      // Keep react-draggable from ever seeing this touch — it has no start
      // delay of its own, so letting it through would drag instantly.
      e.stopPropagation()
      if (e.touches.length !== 1) {
        clearGesture()
        return
      }
      const blockId = handleEl.dataset.blockId
      const rect = el.getBoundingClientRect()
      const breakpoint = rect.width >= LG_BREAKPOINT ? 'lg' : 'sm'
      const cols = COLS[breakpoint]
      const colWidth = (rect.width - MARGIN[0] * (cols - 1) - MARGIN[0] * 2) / cols
      const entry = layouts[breakpoint].find(l => l.i === blockId)
      if (!entry) return
      const touch = e.touches[0]
      gestureRef.current = {
        blockId,
        breakpoint,
        colStep: colWidth + MARGIN[0],
        rowStep: ROW_HEIGHT + MARGIN[1],
        startX: entry.x,
        startY: entry.y,
        startClientX: touch.clientX,
        startClientY: touch.clientY,
        dx: 0,
        dy: 0,
        armed: false,
        timer: setTimeout(() => {
          if (!gestureRef.current) return
          gestureRef.current.armed = true
          navigator.vibrate?.(15)
          setDragVisual({ id: blockId, dx: 0, dy: 0 })
        }, LONG_PRESS_MS),
      }
    }

    function onTouchMove(e) {
      const g = gestureRef.current
      if (!g) return
      const touch = e.touches[0]
      if (!touch) return
      const dx = touch.clientX - g.startClientX
      const dy = touch.clientY - g.startClientY
      if (!g.armed) {
        // Still deciding: enough movement before the hold completed means
        // this was a scroll, not a long-press — bail out and leave the
        // gesture alone so the browser's own native scroll (never blocked,
        // since touch-action stays auto until armed) handles it.
        if (Math.hypot(dx, dy) > MOVE_CANCEL_PX) clearGesture()
        return
      }
      e.preventDefault()
      g.dx = dx
      g.dy = dy
      setDragVisual({ id: g.blockId, dx, dy })
    }

    function onTouchEnd() {
      const g = gestureRef.current
      if (!g) return
      if (g.armed) commitDrag()
      else clearGesture()
    }

    el.addEventListener('touchstart', onTouchStartCapture, { capture: true, passive: true })
    el.addEventListener('touchmove', onTouchMove, { passive: false })
    el.addEventListener('touchend', onTouchEnd)
    el.addEventListener('touchcancel', clearGesture)
    return () => {
      el.removeEventListener('touchstart', onTouchStartCapture, { capture: true })
      el.removeEventListener('touchmove', onTouchMove)
      el.removeEventListener('touchend', onTouchEnd)
      el.removeEventListener('touchcancel', clearGesture)
      clearGesture()
    }
  }, [editing, layouts, commitDrag, clearGesture])

  if (!blocks.length) {
    return (
      <div className="card p-8 text-center text-charcoal-400 dark:text-charcoal-500">
        <p className="text-sm">This dashboard is empty.</p>
        {editing && <p className="text-xs mt-1">Use &quot;+ Add Block&quot; to get started.</p>}
      </div>
    )
  }

  return (
    <div ref={containerRef}>
      <ResponsiveGridLayout
        className="layout dashboard-grid"
        layouts={layouts}
        breakpoints={{ lg: LG_BREAKPOINT, sm: 0 }}
        cols={COLS}
        rowHeight={ROW_HEIGHT}
        margin={MARGIN}
        compactType={null}
        preventCollision={true}
        isDraggable={editing}
        isResizable={editing}
        onLayoutChange={(_current, all) => onLayoutChange?.(all)}
        draggableHandle=".block-drag-handle"
      >
        {blocks.map(b => {
          const dragging = dragVisual?.id === b.id
          return (
            <div
              key={b.id}
              data-block-id={b.id}
              className={editing ? `block-drag-handle cursor-move${dragging ? ' touch-drag-armed' : ''}` : ''}
              // react-grid-layout clones this exact node and overwrites its own
              // `transform`/width/height/position via inline style (see
              // GridItem.createStyle) — so the finger-follow offset below has
              // to live on an inner wrapper instead, or it'd be clobbered.
              style={dragging ? { zIndex: 50 } : undefined}
            >
              <div
                className="h-full w-full"
                style={dragging ? { transform: `translate(${dragVisual.dx}px, ${dragVisual.dy}px)` } : undefined}
              >
                <BlockRenderer block={b} onRemove={onRemoveBlock} onEdit={onEditBlock} onAction={onBlockAction} editing={editing} />
              </div>
            </div>
          )
        })}
      </ResponsiveGridLayout>
    </div>
  )
}
