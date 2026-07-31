import { useNavigate } from 'react-router-dom'

export default function SettingsPageHeader({ title, backTo, backLabel = 'Back' }) {
  const navigate = useNavigate()
  return (
    <div className="mb-1">
      <button
        onClick={() => (backTo ? navigate(backTo) : navigate(-1))}
        className="text-sm text-charcoal-500 hover:text-orange-500 transition-colors mb-1"
      >
        ← {backLabel}
      </button>
      <h1 className="text-2xl font-bold">{title}</h1>
    </div>
  )
}
