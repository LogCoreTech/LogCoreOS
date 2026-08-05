import { useEffect, useState } from 'react'
import { Responsive, WidthProvider } from 'react-grid-layout'
import 'react-grid-layout/css/styles.css'
import 'react-resizable/css/styles.css'
import BlockRenderer from './BlockRenderer'

const ResponsiveGridLayout = WidthProvider(Responsive)

// Drag/resize is intentionally disabled below the `sm` breakpoint — this app has a
// documented history of iOS-standalone-PWA-only layout bugs (see docs/MEMORY.md); a
// full touch-drag grid is a strictly harder version of that bug class. Mobile gets a
// read-only, single-column stacked rendering of the same blocks instead.
const MOBILE_BREAKPOINT = 768

export default function DashboardGrid({ blocks, editing, onRemoveBlock, onLayoutChange }) {
  const [isMobile, setIsMobile] = useState(
    typeof window !== 'undefined' ? window.innerWidth < MOBILE_BREAKPOINT : false
  )

  useEffect(() => {
    function onResize() { setIsMobile(window.innerWidth < MOBILE_BREAKPOINT) }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  if (!blocks.length) {
    return (
      <div className="card p-8 text-center text-charcoal-400 dark:text-charcoal-500">
        <p className="text-sm">This dashboard is empty.</p>
        {editing && <p className="text-xs mt-1">Use "+ Add Block" to get started.</p>}
      </div>
    )
  }

  const layouts = {
    lg: blocks.map(b => ({ i: b.id, ...(b.layout?.lg || { x: 0, y: 0, w: 4, h: 3 }) })),
    sm: blocks.map((b, i) => ({ x: 0, y: i * 3, w: 2, h: 3, i: b.id })),
  }

  return (
    <ResponsiveGridLayout
      className="layout"
      layouts={layouts}
      breakpoints={{ lg: 768, sm: 0 }}
      cols={{ lg: 12, sm: 2 }}
      rowHeight={80}
      margin={[12, 12]}
      isDraggable={editing && !isMobile}
      isResizable={editing && !isMobile}
      onLayoutChange={(_current, all) => onLayoutChange?.(all)}
      draggableHandle=".block-drag-handle"
    >
      {blocks.map(b => (
        <div key={b.id} className={editing && !isMobile ? 'block-drag-handle cursor-move' : ''}>
          <BlockRenderer block={b} onRemove={onRemoveBlock} editing={editing} />
        </div>
      ))}
    </ResponsiveGridLayout>
  )
}
