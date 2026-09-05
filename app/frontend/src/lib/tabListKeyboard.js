// Accessibility audit remainder, 2026-09-05 — Goals' ME/pool tabs and
// Finance's view tabs were reachable via Tab+Enter (real <button> elements)
// but had none of the enhanced ARIA Tabs pattern: no role="tablist"/"tab",
// no arrow-key navigation. This is the shared keyboard half of that pattern
// — roving-tabindex arrow-key navigation (Left/Right moves AND activates
// the adjacent tab; Home/End jump to the ends), the standard interaction
// for a simple, non-scrolling tablist per the ARIA Authoring Practices.
//
// Not a hook — each caller already owns its own `activeTab`/`setActiveTab`
// state and ref array; this is just the pure keydown-to-new-index logic,
// called from each tab button's own onKeyDown.
export function handleTabListKeyDown(e, { tabs, activeIndex, onActivate, refs }) {
  let next = null
  if (e.key === 'ArrowRight') next = (activeIndex + 1) % tabs.length
  else if (e.key === 'ArrowLeft') next = (activeIndex - 1 + tabs.length) % tabs.length
  else if (e.key === 'Home') next = 0
  else if (e.key === 'End') next = tabs.length - 1
  else return
  e.preventDefault()
  onActivate(tabs[next])
  refs.current[next]?.focus()
}
