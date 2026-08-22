// Persistent (non-dismissible) notice shown only when the backend reports
// demo_mode: true (DEMO_MODE=true in docker/.env — never set on a personal
// or managed-hosting instance). Deliberately not dismissible: this is a
// standing data-loss disclosure, not a one-time announcement — a visitor
// who dismisses it and comes back tomorrow should still know why their
// data is gone, not just the first time they see the app.
export default function DemoBanner() {
  return (
    <div className="shrink-0 bg-amber-50 dark:bg-amber-900/20 border-b border-amber-200 dark:border-amber-800 px-4 py-2 text-center text-sm text-amber-700 dark:text-amber-400 font-medium">
      This is a public demo — data resets nightly. Don&apos;t store anything you want to keep.{' '}
      <a href="https://logcoretech.com/privacy/" target="_blank" rel="noopener noreferrer" className="underline">
        Privacy
      </a>{' '}
      ·{' '}
      <a href="https://logcoretech.com/terms/" target="_blank" rel="noopener noreferrer" className="underline">
        Terms
      </a>
    </div>
  )
}
