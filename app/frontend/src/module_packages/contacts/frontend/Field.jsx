// Tiny labeled-field wrapper shared across ContactModal.jsx and its
// extracted sub-components (e.g. CareerRoleFields.jsx) — split into its own
// module so both can import it without ContactModal.jsx and its extracted
// pieces importing each other.
export default function Field({ label, children }) {
  return (
    <label className="block text-sm font-medium mb-1">{label}
      {children}
    </label>
  )
}
