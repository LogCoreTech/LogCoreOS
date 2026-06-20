function hexToHsl(hex) {
  const r = parseInt(hex.slice(1, 3), 16) / 255
  const g = parseInt(hex.slice(3, 5), 16) / 255
  const b = parseInt(hex.slice(5, 7), 16) / 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b)
  let h = 0, s = 0
  const l = (max + min) / 2
  if (max !== min) {
    const d = max - min
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
    switch (max) {
      case r: h = ((g - b) / d + (g < b ? 6 : 0)) / 6; break
      case g: h = ((b - r) / d + 2) / 6; break
      case b: h = ((r - g) / d + 4) / 6; break
    }
  }
  return [h * 360, s * 100, l * 100]
}

function hslToRgbTriplet(h, s, l) {
  h /= 360; s /= 100; l /= 100
  let r, g, b
  if (s === 0) {
    r = g = b = l
  } else {
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s
    const p = 2 * l - q
    const hue2rgb = (p, q, t) => {
      if (t < 0) t += 1
      if (t > 1) t -= 1
      if (t < 1 / 6) return p + (q - p) * 6 * t
      if (t < 1 / 2) return q
      if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6
      return p
    }
    r = hue2rgb(p, q, h + 1 / 3)
    g = hue2rgb(p, q, h)
    b = hue2rgb(p, q, h - 1 / 3)
  }
  return `${Math.round(r * 255)} ${Math.round(g * 255)} ${Math.round(b * 255)}`
}

function hexToRgbTriplet(hex) {
  return `${parseInt(hex.slice(1, 3), 16)} ${parseInt(hex.slice(3, 5), 16)} ${parseInt(hex.slice(5, 7), 16)}`
}

function deriveShades(hex) {
  const [h, s, l] = hexToHsl(hex)
  return {
    '--accent-400': hslToRgbTriplet(h, s, Math.min(90, l + 8)),
    '--accent-500': hexToRgbTriplet(hex),
    '--accent-600': hslToRgbTriplet(h, s, Math.max(5, l - 8)),
  }
}

export function applyAccentColor(hex) {
  if (!hex) return
  const el = document.documentElement
  for (const [key, val] of Object.entries(deriveShades(hex))) {
    el.style.setProperty(key, val)
  }
  const meta = document.querySelector('meta[name="theme-color"]')
  if (meta) meta.setAttribute('content', hex)
}

export function applyDarkMode(mode, systemPrefersDark) {
  const dark = mode === 'dark' || (mode === 'system' && systemPrefersDark)
  document.documentElement.classList.toggle('dark', dark)
}

export function getSystemDarkPreference() {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

export const BACKGROUND_PRESETS = [
  { id: 'none',     label: 'None',     css: 'none' },
  { id: 'midnight', label: 'Midnight', css: 'linear-gradient(135deg, #0f0c29, #302b63, #24243e)' },
  { id: 'sunset',   label: 'Sunset',   css: 'linear-gradient(135deg, #f97316, #ec4899, #8b5cf6)' },
  { id: 'forest',   label: 'Forest',   css: 'linear-gradient(135deg, #134e4a, #065f46, #1e3a2f)' },
  { id: 'ocean',    label: 'Ocean',    css: 'linear-gradient(135deg, #0c4a6e, #164e63, #0e7490)' },
  { id: 'aurora',   label: 'Aurora',   css: 'linear-gradient(135deg, #064e3b, #0f766e, #7c3aed)' },
  { id: 'dusk',     label: 'Dusk',     css: 'linear-gradient(135deg, #1e1b4b, #4c1d95, #831843)' },
]

export function applyBackground(value) {
  const el = document.documentElement
  if (!value || value === 'none') {
    el.style.removeProperty('--bg-image')
    return
  }
  if (value.startsWith('gradient:')) {
    const gradId = value.slice('gradient:'.length)
    const preset = BACKGROUND_PRESETS.find(p => p.id === gradId)
    if (preset && preset.css !== 'none') {
      el.style.setProperty('--bg-image', preset.css)
    } else {
      el.style.removeProperty('--bg-image')
    }
    return
  }
  if (value === 'uploaded') {
    el.style.setProperty('--bg-image', 'url(/api/v1/auth/me/background)')
  }
}
