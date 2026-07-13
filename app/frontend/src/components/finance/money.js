// Money display/input helpers — amounts are ALWAYS integer cents in the API.

export function fmtMoney(cents, currency = 'USD') {
  if (typeof cents !== 'number' || Number.isNaN(cents)) return '—'
  try {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(cents / 100)
  } catch {
    return `$${(cents / 100).toFixed(2)}`
  }
}

// "1,234.56" | "$1234.56" | "1234" → integer cents (NaN when unparseable)
export function toCents(input) {
  const cleaned = String(input ?? '').replace(/[$,\s]/g, '')
  if (!cleaned || !/^-?\d*\.?\d{0,2}$/.test(cleaned)) return NaN
  const value = parseFloat(cleaned)
  if (Number.isNaN(value)) return NaN
  return Math.round(value * 100)
}

// cents → "1234.56" for pre-filling inputs (absolute value)
export function centsToInput(cents) {
  if (typeof cents !== 'number' || Number.isNaN(cents)) return ''
  return (Math.abs(cents) / 100).toFixed(2)
}

export function todayStr() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function monthStr(date = new Date()) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
}
