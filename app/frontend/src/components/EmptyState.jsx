// Shared empty-state (item #2, 2026-09-04 UX Polish Batch) — a consistent
// icon + message + optional CTA button, replacing each module's own
// hand-rolled "No X yet" text. Always-on, no user setting (unlike #12's
// module-visibility toggle, this is copy/UI, not a feature to opt into).
export default function EmptyState({ icon, title, description, ctaLabel, onCta }) {
  return (
    <div className="card p-8 text-center text-charcoal-500 dark:text-charcoal-400">
      {icon && (
        <p className="text-4xl mb-2" aria-hidden>
          {icon}
        </p>
      )}
      <p className="font-medium text-charcoal-700 dark:text-charcoal-200">{title}</p>
      {description && <p className="text-sm mt-1">{description}</p>}
      {ctaLabel && onCta && (
        <button type="button" onClick={onCta} className="btn-primary mt-4">
          {ctaLabel}
        </button>
      )}
    </div>
  )
}
