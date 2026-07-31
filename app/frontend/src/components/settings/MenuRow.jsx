import { Link } from 'react-router-dom'

export default function MenuRow({ icon, label, subtitle, to, onClick, disabled, trailing }) {
  const classes = `w-full flex items-center gap-3 px-4 py-3 text-left transition-colors ${
    disabled
      ? 'opacity-50 cursor-not-allowed'
      : 'hover:bg-charcoal-50 dark:hover:bg-charcoal-800'
  }`

  const content = (
    <>
      <span className="text-base leading-none shrink-0">{icon}</span>
      <span className="flex-1 min-w-0">
        <span className="block text-sm font-medium truncate">{label}</span>
        {subtitle && (
          <span className="block text-xs text-charcoal-500 dark:text-charcoal-400 truncate">
            {subtitle}
          </span>
        )}
      </span>
      {trailing}
      {!disabled && (to || onClick) && (
        <span className="text-charcoal-300 dark:text-charcoal-600 shrink-0">›</span>
      )}
    </>
  )

  if (to && !disabled) {
    return (
      <Link to={to} className={classes}>
        {content}
      </Link>
    )
  }

  return (
    <button type="button" onClick={disabled ? undefined : onClick} disabled={disabled} className={classes}>
      {content}
    </button>
  )
}
