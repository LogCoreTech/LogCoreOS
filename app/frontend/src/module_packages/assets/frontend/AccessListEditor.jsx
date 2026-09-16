import TagInput from '../../../components/TagInput'
import { CapsSelector } from '../../../components/assetDisplay'

// Asset sharing/hiding editor — extracted out of AssetModal.jsx's "Access"
// section. Two mutually exclusive audience models depending on ownership:
// a personal asset uses `shared_with` (share requests, any access level;
// a contribute-level entry gets its own CapsSelector for exactly which
// fields/actions it grants), while a pool (household/team) asset uses
// `contributors` instead (individual members granted contribute-level caps
// directly — no accept step, no access-level picker, since it's always
// "contribute"). `hidden_from` and the apply-to-descendants scope toggle are
// common to both branches.
//
// `onChange` is the raw setAccess state setter from AssetModal (React
// setState, so it accepts the same functional-update form `a => ({...a,
// ...})` every call site below already relied on) — passed through as-is
// rather than wrapped, so each handler here is a verbatim copy of the
// original inline ones. Checked module_packages/dashboard/frontend/
// DashboardAccessModal.jsx and finance/frontend/BookSettings.jsx's own
// sharing UIs before writing this: both cover the same shared_with/
// contributors/hidden_from idea, but neither is a near-duplicate of this
// one — Dashboard's is a separate add-row + flat list (no inline per-row
// edit, no caps editor), and Finance's caps are a different flags shape
// entirely (per-book/per-account "scope" dimension, boolean CAP_LABELS
// instead of CapsSelector's fields/add arrays). Generalizing those two in
// with this one would be a materially different, riskier refactor than the
// approved scope here, so this stays Assets-specific.
export default function AccessListEditor({
  isPool,
  access,
  onChange,
  members,
  currentUserName,
  groupTarget,
  roleNames,
  templateFields,
  activeDescendants,
  shareScope,
  onShareScopeChange,
}) {
  const shareTargets = access.shared_with

  return (
    <div className="border-t border-charcoal-100 dark:border-charcoal-800 pt-3 space-y-2">
      <label className="block text-sm font-medium">Access</label>
      {!isPool && (
        <div className="space-y-1">
          {shareTargets.map((s, i) => (
            <div key={i} className="space-y-1">
              <div className="flex items-center gap-2 text-sm">
                <select
                  value={s.target}
                  onChange={e => onChange(a => ({ ...a, shared_with: a.shared_with.map((x, j) => j === i ? { ...x, target: e.target.value } : x) }))}
                  className="input !py-1 flex-1"
                >
                  <option value="">— pick —</option>
                  <option value={groupTarget}>{groupTarget === 'team' ? '🧑‍🤝‍🧑 Whole team' : '🏠 Whole household'}</option>
                  {members.filter(m => m !== currentUserName).map(m => <option key={m} value={m}>{m}</option>)}
                </select>
                <select
                  value={s.access}
                  onChange={e => onChange(a => ({ ...a, shared_with: a.shared_with.map((x, j) => j === i ? { ...x, access: e.target.value, ...(e.target.value === 'contribute' && !x.caps ? { caps: { fields: [], add: ['comments'] } } : {}) } : x) }))}
                  className="input !py-1 !w-28"
                >
                  <option value="read">read</option>
                  <option value="contribute">contribute</option>
                  <option value="edit">edit</option>
                </select>
                <button type="button" onClick={() => onChange(a => ({ ...a, shared_with: a.shared_with.filter((_, j) => j !== i) }))} aria-label="Remove" className="text-red-400 hover:text-red-500">✕</button>
              </div>
              {s.access === 'contribute' && (
                <CapsSelector
                  caps={s.caps}
                  onChange={caps => onChange(a => ({ ...a, shared_with: a.shared_with.map((x, j) => j === i ? { ...x, caps } : x) }))}
                  templateFields={templateFields}
                />
              )}
            </div>
          ))}
          <button type="button" onClick={() => onChange(a => ({ ...a, shared_with: [...a.shared_with, { target: '', access: 'read' }] }))} className="btn-ghost text-xs px-2 py-1">
            ＋ Share with…
          </button>
          <p className="text-[10px] text-charcoal-400">People you add get a request to accept before it appears for them. Contribute = you pick exactly what they can change or add.</p>
        </div>
      )}
      {isPool && (
        <div className="space-y-1">
          <label className="block text-xs text-charcoal-400">Contributors <span className="font-normal">(can update what you pick — without full pool rights)</span></label>
          {(access.contributors || []).map((c, i) => (
            <div key={i} className="space-y-1">
              <div className="flex items-center gap-2 text-sm">
                <select
                  value={c.target}
                  onChange={e => onChange(a => ({ ...a, contributors: a.contributors.map((x, j) => j === i ? { ...x, target: e.target.value } : x) }))}
                  className="input !py-1 flex-1"
                >
                  <option value="">— pick —</option>
                  <option value={groupTarget}>{groupTarget === 'team' ? '🧑‍🤝‍🧑 Whole team' : '🏠 Whole household'}</option>
                  {members.filter(m => m !== currentUserName).map(m => <option key={m} value={m}>{m}</option>)}
                </select>
                <button type="button" onClick={() => onChange(a => ({ ...a, contributors: a.contributors.filter((_, j) => j !== i) }))} aria-label="Remove" className="text-red-400 hover:text-red-500">✕</button>
              </div>
              <CapsSelector
                caps={c.caps}
                onChange={caps => onChange(a => ({ ...a, contributors: a.contributors.map((x, j) => j === i ? { ...x, caps } : x) }))}
                templateFields={templateFields}
              />
            </div>
          ))}
          <button type="button" onClick={() => onChange(a => ({ ...a, contributors: [...(a.contributors || []), { target: '', caps: { fields: [], add: ['comments'] } }] }))} className="btn-ghost text-xs px-2 py-1">
            ＋ Contributor…
          </button>
        </div>
      )}
      <div>
        <label className="block text-xs text-charcoal-400 mb-1">Hide from</label>
        <TagInput
          value={access.hidden_from || []}
          onChange={hidden_from => onChange(a => ({ ...a, hidden_from }))}
          suggestions={[
            ...members.filter(m => m !== currentUserName),
            ...roleNames.map(r => `role:${r}`),
          ]}
          strict
          placeholder="Pick people or role:… to hide this from…"
        />
      </div>
      {activeDescendants > 0 && (
        <div className="flex gap-1 text-xs">
          {[
            { id: 'all', label: 'Apply to everything inside' },
            { id: 'one', label: 'This one only' },
          ].map(o => (
            <button
              key={o.id}
              type="button"
              onClick={() => onShareScopeChange(o.id)}
              className={`flex-1 py-1.5 rounded-md font-medium transition-colors ${
                shareScope === o.id
                  ? 'bg-orange-500 text-white'
                  : 'bg-charcoal-100 dark:bg-charcoal-700 text-charcoal-600 dark:text-charcoal-300'
              }`}
            >
              {o.label}
            </button>
          ))}
        </div>
      )}
      <p className="text-[10px] text-charcoal-400">Sharing is saved when you press Save below.</p>
    </div>
  )
}
