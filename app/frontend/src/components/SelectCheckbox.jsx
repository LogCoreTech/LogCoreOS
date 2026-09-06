// A native checkbox wrapped in a real 44×44px hit target (UX Polish Batch
// #4/#1) — the visible box stays small, but the tappable area meets the
// WCAG/platform touch-target floor this batch's mobile section already
// applies to Toast's dismiss button and ConfirmDialog's buttons.
//
// The wrapper takes its full 44×44px as real space in the flex layout — no
// negative-margin "enlarge without shifting neighbors" trick. That trick
// was tried first and was a real, live-breaking bug: every row this
// mounts into uses a `gap` of 6–12px between flex children, smaller than
// the 20px a `-m-2.5` (-10px/side) margin would need to stay clear of the
// next sibling — on desktop, where this renders unconditionally (not just
// in select-mode), it silently overlapped and intercepted clicks meant for
// whatever came right after it (a row's own open-button, its "···" menu,
// an expand arrow), which is exactly how "the delete button doesn't work"
// actually presented — the click never reached it in the first place.
//
// `className` deliberately carries the wrapper's OWN `display` utility
// (default `inline-flex`) rather than the base class list hardcoding one —
// a caller that needs to conditionally hide this on mobile (`hidden
// md:inline-flex`) would otherwise be fighting Tailwind's generated
// stylesheet order, not the className string's order, to override a
// `display` utility already baked into the base classes; keeping `display`
// as the ONE thing `className` ever sets avoids that class of bug entirely.
export default function SelectCheckbox({ checked, onChange, label, className = 'inline-flex' }) {
  return (
    <span className={`items-center justify-center w-11 h-11 shrink-0 ${className}`}>
      <input
        type="checkbox"
        checked={checked}
        onChange={onChange}
        onClick={(e) => e.stopPropagation()}
        aria-label={label}
        className="w-5 h-5 rounded accent-orange-500 cursor-pointer"
      />
    </span>
  )
}
