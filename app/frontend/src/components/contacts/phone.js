// Shared phone display formatting — a stored phone is always
// {country_code, number, extension}, number digits-only capped to 10
// (contacts_service.py::_validate_phones). Used by both the contact detail
// card and the Contacts list row preview, which previously showed the raw
// undashed digits (bug found 2026-08-15).
export function formatPhone(p) {
  if (!p) return ''
  const d = p.number || ''
  const formatted = d.length === 10 ? `${d.slice(0, 3)}-${d.slice(3, 6)}-${d.slice(6)}` : d
  let out = `(+${p.country_code || '1'}) ${formatted}`
  if (p.extension) out += ` ext. ${p.extension}`
  return out
}
