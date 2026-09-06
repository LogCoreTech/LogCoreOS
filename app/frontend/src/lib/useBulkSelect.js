import { useCallback, useState } from 'react'

// Shared multi-select state for list-view bulk actions (UX Polish Batch #4).
// `getId` defaults to `item => item.id` but Notes' own tree needs `path`
// instead — passed explicitly by that caller. `toggleAll` only ever
// operates over the caller's currently-visible/filtered items (mirrors
// BulkConvertContactsModal.jsx's own "caller pre-filters to the eligible
// set" convention) — never a full unfiltered dataset the caller didn't hand
// it directly.
export default function useBulkSelect(getId = (item) => item.id) {
  const [active, setActive] = useState(false)
  const [selected, setSelected] = useState(() => new Set())

  const isSelected = useCallback((item) => selected.has(getId(item)), [selected, getId])

  const toggle = useCallback(
    (item) => {
      const id = getId(item)
      setSelected((prev) => {
        const next = new Set(prev)
        if (next.has(id)) next.delete(id)
        else next.add(id)
        return next
      })
    },
    [getId]
  )

  const toggleAll = useCallback(
    (visibleItems) => {
      const ids = visibleItems.map(getId)
      setSelected((prev) => {
        const allSelected = ids.length > 0 && ids.every((id) => prev.has(id))
        return allSelected ? new Set() : new Set(ids)
      })
    },
    [getId]
  )

  const clear = useCallback(() => setSelected(new Set()), [])

  function stop() {
    setActive(false)
    clear()
  }

  return { active, setActive, stop, selected, toggle, toggleAll, clear, isSelected, count: selected.size }
}
