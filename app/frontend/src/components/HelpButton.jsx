import { Link } from 'react-router-dom'

// Small ⓘ affordance placed next to a page title. Deep-links to that module's
// section in the Help guide (Help.jsx scrolls to the matching #id).
export default function HelpButton({ section, className = '' }) {
  return (
    <Link
      to={`/help#${section}`}
      title="How to use this"
      aria-label="How to use this"
      className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-charcoal-400 hover:text-orange-500 hover:bg-orange-500/10 transition-colors ${className}`}
    >
      ⓘ
    </Link>
  )
}
