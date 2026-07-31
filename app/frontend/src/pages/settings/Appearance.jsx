import { useRef, useState } from 'react'
import { auth as authApi } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { applyAccentColor, applyDarkMode, applyBackground, applyDensity, applyCornerStyle, getSystemDarkPreference, BACKGROUND_PRESETS } from '../../lib/theme'
import SettingsPageHeader from '../../components/settings/SettingsPageHeader'

const DEFAULT_ACCENT = '#f97316'
const PRESET_COLORS = ['#f97316', '#3b82f6', '#8b5cf6', '#10b981', '#ef4444', '#ec4899', '#f59e0b', '#06b6d4']
const HEX_RE = /^#[0-9a-fA-F]{6}$/

export default function Appearance() {
  const { user, updateUserField } = useAuth()

  const [accentColor, setAccentColor]       = useState(() => user?.accentColor  || DEFAULT_ACCENT)
  const [hexInput, setHexInput]             = useState(() => user?.accentColor  || DEFAULT_ACCENT)
  const [darkMode, setDarkMode]             = useState(() => user?.darkMode     || 'system')
  const [background, setBackground]         = useState(() => user?.background   || null)
  const [density, setDensity]               = useState(() => user?.density      || 'comfortable')
  const [cornerStyle, setCornerStyle]       = useState(() => user?.cornerStyle  || 'rounded')
  const [saved, setSaved]                   = useState(false)
  const [bgUploading, setBgUploading]       = useState(false)
  const [bgError, setBgError]               = useState('')
  const bgInputRef = useRef(null)

  function flash() {
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  function previewAccent(hex) {
    setAccentColor(hex)
    setHexInput(hex)
    applyAccentColor(hex)
  }

  function handleHexInput(raw) {
    setHexInput(raw)
    const normalized = raw.length === 4
      ? '#' + raw.slice(1).split('').map(c => c + c).join('')
      : raw
    if (HEX_RE.test(normalized)) previewAccent(normalized)
  }

  function previewDarkMode(mode) {
    setDarkMode(mode)
    applyDarkMode(mode, getSystemDarkPreference())
  }

  function previewBackground(value) {
    setBackground(value)
    applyBackground(value)
  }

  async function save() {
    const updates = { accent_color: accentColor, dark_mode: darkMode, density, corner_style: cornerStyle }
    if (background !== 'uploaded') updates.background = background || 'none'
    try {
      await authApi.updateMe(updates)
      updateUserField('accentColor', accentColor)
      updateUserField('darkMode', darkMode)
      updateUserField('density', density)
      updateUserField('cornerStyle', cornerStyle)
      if (background !== 'uploaded') updateUserField('background', background || null)
      flash()
    } catch (e) {
      alert(e.message || 'Failed to save appearance')
    }
  }

  async function handleBgUpload(file) {
    setBgUploading(true)
    setBgError('')
    try {
      await authApi.uploadBackground(file)
      setBackground('uploaded')
      applyBackground('uploaded')
      updateUserField('background', 'uploaded')
    } catch (e) {
      setBgError(e.message || 'Upload failed')
    } finally {
      setBgUploading(false)
    }
  }

  async function handleRemoveBackground() {
    try {
      await authApi.deleteBackground()
    } catch { /* ignore if no file exists */ }
    setBackground(null)
    applyBackground(null)
    updateUserField('background', null)
  }

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <SettingsPageHeader title="Appearance" backTo="/settings" backLabel="Settings" />

      <div className="card p-5 space-y-5">
        <div className="flex items-center justify-end">
          {saved && <span className="text-green-500 text-sm">Saved ✓</span>}
        </div>

        {/* Dark mode */}
        <div>
          <p className="text-xs font-medium text-charcoal-500 dark:text-charcoal-400 mb-2">Dark Mode</p>
          <div className="flex rounded-lg border border-charcoal-200 dark:border-charcoal-700 overflow-hidden">
            {['system', 'light', 'dark'].map(mode => (
              <button
                key={mode}
                onClick={() => previewDarkMode(mode)}
                className={`flex-1 py-1.5 text-sm font-medium capitalize transition-colors ${
                  darkMode === mode
                    ? 'bg-orange-500 text-white'
                    : 'text-charcoal-600 dark:text-charcoal-300 hover:bg-charcoal-100 dark:hover:bg-charcoal-700'
                }`}
              >
                {mode}
              </button>
            ))}
          </div>
        </div>

        {/* Accent color */}
        <div>
          <p className="text-xs font-medium text-charcoal-500 dark:text-charcoal-400 mb-2">Accent Color</p>
          <div className="flex flex-wrap gap-2 mb-3">
            {PRESET_COLORS.map(color => (
              <button
                key={color}
                onClick={() => previewAccent(color)}
                title={color}
                className="w-8 h-8 rounded-full transition-transform hover:scale-110 focus:outline-none"
                style={{
                  backgroundColor: color,
                  boxShadow: accentColor === color ? `0 0 0 2px white, 0 0 0 4px ${color}` : 'none',
                }}
              />
            ))}
          </div>
          <div className="flex items-center gap-2">
            <input
              type="color"
              value={accentColor}
              onChange={e => previewAccent(e.target.value)}
              className="w-9 h-9 rounded cursor-pointer border border-charcoal-300 dark:border-charcoal-600 bg-transparent p-0.5"
              title="Pick custom color"
            />
            <input
              type="text"
              value={hexInput}
              onChange={e => handleHexInput(e.target.value)}
              placeholder="#f97316"
              maxLength={7}
              className="input w-28 font-mono text-sm"
            />
          </div>
        </div>

        {/* Background */}
        <div>
          <p className="text-xs font-medium text-charcoal-500 dark:text-charcoal-400 mb-2">Background</p>
          <div className="grid grid-cols-4 gap-2 mb-3">
            {BACKGROUND_PRESETS.map(preset => {
              const isNone = preset.id === 'none'
              const isSelected = isNone
                ? (!background || background === 'none')
                : background === `gradient:${preset.id}`
              return (
                <button
                  key={preset.id}
                  onClick={() => previewBackground(isNone ? null : `gradient:${preset.id}`)}
                  title={preset.label}
                  className={`h-12 rounded-lg border-2 transition-all text-xs font-medium overflow-hidden ${
                    isSelected
                      ? 'border-orange-500 ring-1 ring-orange-500'
                      : 'border-charcoal-200 dark:border-charcoal-700 hover:border-orange-400'
                  }`}
                  style={isNone ? {} : { background: preset.css }}
                >
                  {isNone && (
                    <span className="text-charcoal-400 dark:text-charcoal-500 text-xs">None</span>
                  )}
                </button>
              )
            })}
          </div>

          {/* Custom upload */}
          <div className="flex items-center gap-2">
            <input
              ref={bgInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp,image/avif"
              className="hidden"
              onChange={e => { if (e.target.files?.[0]) handleBgUpload(e.target.files[0]); e.target.value = '' }}
            />
            <button
              onClick={() => bgInputRef.current?.click()}
              disabled={bgUploading}
              className="btn-ghost text-xs px-3 py-1.5 disabled:opacity-50"
            >
              {bgUploading ? 'Uploading…' : background === 'uploaded' ? 'Replace image' : 'Upload image'}
            </button>
            {(background && background !== 'none') && (
              <button
                onClick={handleRemoveBackground}
                className="text-xs text-red-500 hover:text-red-600 font-medium"
              >
                Remove
              </button>
            )}
            {background === 'uploaded' && !bgUploading && (
              <span className="text-xs text-green-500">Custom image active</span>
            )}
          </div>
          {bgError && <p className="text-xs text-red-500 mt-1">{bgError}</p>}
        </div>

        {/* Density */}
        <div>
          <p className="text-xs font-medium text-charcoal-500 dark:text-charcoal-400 mb-2">Density</p>
          <div className="flex rounded-lg border border-charcoal-200 dark:border-charcoal-700 overflow-hidden">
            {['comfortable', 'compact'].map(opt => (
              <button
                key={opt}
                onClick={() => { setDensity(opt); applyDensity(opt) }}
                className={`flex-1 py-1.5 text-sm font-medium capitalize transition-colors ${
                  density === opt
                    ? 'bg-orange-500 text-white'
                    : 'text-charcoal-600 dark:text-charcoal-300 hover:bg-charcoal-100 dark:hover:bg-charcoal-700'
                }`}
              >
                {opt}
              </button>
            ))}
          </div>
        </div>

        {/* Corners */}
        <div>
          <p className="text-xs font-medium text-charcoal-500 dark:text-charcoal-400 mb-2">Corners</p>
          <div className="flex gap-3">
            {[
              { id: 'rounded', label: 'Rounded', cls: 'rounded-xl' },
              { id: 'sharp',   label: 'Sharp',   cls: 'rounded-md'  },
            ].map(({ id, label, cls }) => (
              <button
                key={id}
                onClick={() => { setCornerStyle(id); applyCornerStyle(id) }}
                className={`flex-1 flex flex-col items-center gap-2 py-3 border-2 transition-colors ${
                  cornerStyle === id
                    ? 'border-orange-500'
                    : 'border-charcoal-200 dark:border-charcoal-700 hover:border-orange-400'
                } ${cls}`}
              >
                <div className={`w-8 h-5 bg-charcoal-300 dark:bg-charcoal-600 ${cls}`} />
                <span className="text-xs font-medium text-charcoal-600 dark:text-charcoal-300">{label}</span>
              </button>
            ))}
          </div>
        </div>

        <button onClick={save} className="btn-primary w-full">
          Save Appearance
        </button>
      </div>
    </div>
  )
}
