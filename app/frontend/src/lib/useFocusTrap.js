import { useEffect } from 'react'

// Accessibility audit finding, 2026-09-05 (UX Polish Batch item #1's
// keyboard-nav remainder) — no modal in this app trims Tab focus to stay
// inside it; a keyboard user can Tab straight past the last focusable
// element in an open modal into the page behind the overlay. The ARIA
// Authoring Practices' Dialog pattern requires trapping focus inside an
// open modal — this is that, as a hook every modal wires in individually,
// the same shape useEscapeToClose already established (no single shared
// <Modal> wrapper exists in this codebase for either concern to ride on).
//
// `containerRef` must point at the modal's own root element (its
// `.modal-card`, or equivalent) — NOT `.modal-overlay`, which also contains
// nothing focusable outside the card anyway, but scoping to the card keeps
// the querySelectorAll scan small and makes the intent explicit.
export default function useFocusTrap(containerRef, active = true) {
  useEffect(() => {
    if (!active) return
    const container = containerRef.current
    if (!container) return

    function getFocusable() {
      return Array.from(
        container.querySelectorAll(
          'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
        )
      ).filter(el => el.offsetParent !== null) // skip hidden/collapsed elements
    }

    function onKeyDown(e) {
      if (e.key !== 'Tab') return
      const focusable = getFocusable()
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      // Tabbing from outside the trap (e.g. the initial focus lands
      // somewhere the trap doesn't know about) still gets pulled back in,
      // not just the exact first/last boundary case.
      if (e.shiftKey) {
        if (document.activeElement === first || !container.contains(document.activeElement)) {
          e.preventDefault()
          last.focus()
        }
      } else if (document.activeElement === last || !container.contains(document.activeElement)) {
        e.preventDefault()
        first.focus()
      }
    }

    container.addEventListener('keydown', onKeyDown)
    return () => container.removeEventListener('keydown', onKeyDown)
  }, [containerRef, active])
}
