"""Asset templates — admin-curated, instance-wide field-structure definitions
that every Asset record is built from, plus the field-definition/value
validation shared by both a real Template and a blank asset's own ad-hoc
custom field defs.

Templates live instance-wide in brain/_system/asset_templates.json (admin-only
writes) so every viewer and n8n workflow sees the same field structure;
personal templates live per-owner via `personal_templates_path()`.

Extracted out of `assets_service.py` (2026-09-16, R6) — that file had grown
past 1750 lines mixing asset-record CRUD with template CRUD/sharing/
validation, two largely independent concerns. `assets_service.py` re-exports
every public name below (`from services.assets_templates_service import
*`-equivalent explicit imports), so every existing `assets_service.
create_template(...)`-style caller (routers, agent_tools, dashboard blocks,
tests — all of which go through the `assets_service` module object, never a
direct `from services.assets_service import create_template`) keeps working
unchanged; a handful of asset-record functions there
(`create_asset`/`update_asset`/`attach_template`) import the validation
helpers directly from here since they call them themselves.

A few functions here (`template_reference_count`, `share_template`,
`respond_to_template_share`) need Asset-record data or assets_service's
sharing-notification internals (`_all_stores`/`list_assets`/
`_load_features_roles`/`_resolve_targets`/`_notify_share_targets`/
`_respond_shares`) that legitimately belong on the asset side (shared with
asset sharing, not template-specific). Those are imported lazily, inside the
function bodies, to avoid a module-load-time import cycle with
assets_service.py (which imports this module's names at its own top level).
"""

import re
import uuid
from datetime import date, datetime, timezone
from typing import Any

from services.auth_service import get_user_by_name, list_users
from services.file_service import (
    asset_templates_path,
    personal_templates_path,
    read_json,
    write_json,
)

FIELD_TYPES = {"text", "number", "date", "boolean", "select", "contact"}
_KEY_RE = re.compile(r"^[a-z0-9_]{1,40}$")
_TEXT_MAX = 2000

GLOBAL_OWNER = "_global"


# ---------------------------------------------------------------------------
# Templates (instance-level, admin-curated)
# ---------------------------------------------------------------------------


def _template_store_path(owner: str):
    return asset_templates_path() if owner == GLOBAL_OWNER else personal_templates_path(owner)


def _load_template_store(owner: str) -> dict:
    return read_json(_template_store_path(owner), default={"templates": []})


def _save_template_store(owner: str, data: dict) -> None:
    write_json(_template_store_path(owner), data)


def list_global_templates() -> list[dict]:
    return _load_template_store(GLOBAL_OWNER).get("templates", [])


def list_personal_templates(owner: str) -> list[dict]:
    return _load_template_store(owner).get("templates", [])


def _all_personal_templates() -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for u in list_users():
        for t in list_personal_templates(u["name"]):
            out.append((u["name"], t))
    return out


def get_global_template(key: str) -> dict | None:
    return next((t for t in list_global_templates() if t.get("key") == key), None)


def get_template_by_id(tid: str) -> dict | None:
    for t in list_global_templates():
        if t.get("id") == tid:
            return t
    for _owner, t in _all_personal_templates():
        if t.get("id") == tid:
            return t
    return None


def _find_template(tid: str) -> tuple[str, dict] | None:
    """Return (owner, template) for a template id — owner is GLOBAL_OWNER or a user."""
    for t in list_global_templates():
        if t.get("id") == tid:
            return GLOBAL_OWNER, t
    for owner, t in _all_personal_templates():
        if t.get("id") == tid:
            return owner, t
    return None


def all_templates_by_id() -> dict:
    """id → template for global + every personal store (one scan, for bulk attach)."""
    m = {t["id"]: t for t in list_global_templates() if t.get("id")}
    for _owner, t in _all_personal_templates():
        if t.get("id"):
            m[t["id"]] = t
    return m


def attach_templates(assets: list[dict]) -> list[dict]:
    """Return copies of assets with their resolved template embedded as `_template`
    so a viewer can render icon/label/fields even for a shared asset whose template
    they don't own."""
    by_id = all_templates_by_id()
    by_key = {t.get("key"): t for t in list_global_templates()}
    out = []
    for a in assets:
        tmpl = by_id.get(a.get("template_id")) or by_key.get(a.get("template"))
        out.append({**a, "_template": tmpl})
    return out


def resolve_template(asset: dict) -> dict | None:
    """Resolve an asset's template — by id (global or any owner's personal) with a
    fallback to the legacy global-by-key reference for pre-Phase-2 assets.

    Returns `{}` for a genuinely blank asset (no template_id and no template
    key at all — 2026-08-17). `None` specifically means a STALE reference —
    a template_id/key that used to exist and was deleted — which callers
    correctly treat as an error. Before this distinction, a blank asset's
    `update_asset()` call raised "Template None no longer exists" on every
    single save (any edit sends `fields`, even an empty `{}`), since a blank
    asset's `template` key is also `None` and `get_global_template(None or
    "")` finds nothing — blank assets couldn't be saved at all post-create."""
    tid = asset.get("template_id")
    if tid:
        return get_template_by_id(tid)
    key = asset.get("template")
    if not key:
        return {}
    return get_global_template(key)


# Backward-compat: some callers still resolve global templates by key.
def get_template(key: str) -> dict | None:
    return get_global_template(key)


def list_templates() -> list[dict]:
    """Legacy: global templates only (used by reference counting)."""
    return list_global_templates()


def visible_templates(
    viewer: str, is_admin: bool = False, feature_role: str = "member"
) -> list[dict]:
    """Templates a viewer can build from: role-permitted global + own personal +
    personal templates shared to and accepted by the viewer."""
    out: list[dict] = []
    for t in list_global_templates():
        rr = t.get("restrict_roles") or []
        if not rr or is_admin or feature_role in rr:
            out.append({**t, "_scope": "global"})
    for t in list_personal_templates(viewer):
        out.append({**t, "_scope": "own"})
    for owner, t in _all_personal_templates():
        if owner == viewer:
            continue
        for s in t.get("shared_with") or []:
            if "accepted" in s and viewer in (s.get("accepted") or []):
                out.append({**t, "_scope": "shared", "_owner": owner})
                break
    return out


def _validate_field_defs(fields: list[dict]) -> list[dict]:
    """Normalize and validate an ordered field-definition list."""
    cleaned: list[dict] = []
    seen: set[str] = set()
    for f in fields:
        key = (f.get("key") or "").strip()
        if not _KEY_RE.match(key):
            raise ValueError(f"Invalid field key {key!r} — use a-z, 0-9, _ (max 40 chars)")
        if key in seen:
            raise ValueError(f"Duplicate field key {key!r}")
        seen.add(key)
        ftype = f.get("type")
        if ftype not in FIELD_TYPES:
            raise ValueError(
                f"Invalid field type {ftype!r} for {key!r}. Valid: {sorted(FIELD_TYPES)}"
            )
        entry: dict[str, Any] = {
            "key": key,
            "label": (f.get("label") or key).strip()[:80],
            "type": ftype,
        }
        if ftype == "select":
            options = [str(o).strip() for o in (f.get("options") or []) if str(o).strip()]
            if not options:
                raise ValueError(f"Select field {key!r} needs at least one option")
            entry["options"] = options
        default = f.get("default")
        if default not in (None, ""):
            entry["default"] = _validate_value(entry, default)
        cleaned.append(entry)
    return cleaned


def create_template(data: dict, owner: str = GLOBAL_OWNER) -> dict:
    key = (data.get("key") or "").strip()
    if not _KEY_RE.match(key):
        raise ValueError(f"Invalid template key {key!r} — use a-z, 0-9, _ (max 40 chars)")
    store = _load_template_store(owner)
    if any(t.get("key") == key for t in store["templates"]):
        raise ValueError(f"Template {key!r} already exists")
    template = {
        "id": str(uuid.uuid4()),
        "key": key,
        "label": (data.get("label") or key).strip()[:80],
        "icon": (data.get("icon") or "").strip()[:8],
        "fields": _validate_field_defs(data.get("fields") or []),
        "owner": owner,
        "shared_with": [],
        "restrict_roles": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    store["templates"].append(template)
    _save_template_store(owner, store)
    return template


def update_template(tid: str, updates: dict) -> dict | None:
    """Replace label/icon/fields (+ restrict_roles for global). Key is immutable."""
    found = _find_template(tid)
    if found is None:
        return None
    owner, _ = found
    store = _load_template_store(owner)
    for i, t in enumerate(store["templates"]):
        if t.get("id") != tid:
            continue
        if "label" in updates and updates["label"]:
            t["label"] = str(updates["label"]).strip()[:80]
        if "icon" in updates:
            t["icon"] = str(updates["icon"] or "").strip()[:8]
        if "fields" in updates:
            t["fields"] = _validate_field_defs(updates["fields"] or [])
        if "restrict_roles" in updates and owner == GLOBAL_OWNER:
            t["restrict_roles"] = [str(r).strip() for r in (updates["restrict_roles"] or [])]
        store["templates"][i] = t
        _save_template_store(owner, store)
        return t
    return None


def template_reference_count(tid: str) -> int:
    # Lazy import — needs the asset-record store, which lives in
    # assets_service.py; a module-level import would cycle back here.
    from services.assets_service import _all_stores, list_assets

    found = _find_template(tid)
    key = found[1].get("key") if found else None
    count = 0
    for store_user, workspace in _all_stores():
        for a in list_assets(store_user, workspace):
            if a.get("template_id") == tid or (
                key and not a.get("template_id") and a.get("template") == key
            ):
                count += 1
    return count


def delete_template(tid: str) -> bool:
    found = _find_template(tid)
    if found is None:
        return False
    owner, tmpl = found
    refs = template_reference_count(tid)
    if refs:
        raise ValueError(
            f"{refs} asset(s) still use template {tmpl.get('label', tmpl.get('key'))!r} — "
            "delete or archive them first"
        )
    store = _load_template_store(owner)
    before = len(store["templates"])
    store["templates"] = [t for t in store["templates"] if t.get("id") != tid]
    if len(store["templates"]) == before:
        return False
    _save_template_store(owner, store)
    return True


def insert_example_template(owner: str = GLOBAL_OWNER) -> dict:
    """Optional starter for the empty state — created only on explicit user click."""
    existing = {t.get("key") for t in _load_template_store(owner).get("templates", [])}
    key = "example"
    n = 2
    while key in existing:
        key = f"example_{n}"
        n += 1
    return create_template(
        {
            "key": key,
            "label": "Example",
            "icon": "📦",
            "fields": [
                {
                    "key": "status",
                    "label": "Status",
                    "type": "select",
                    "options": ["active", "inactive"],
                    "default": "active",
                },
                {"key": "value", "label": "Value", "type": "number"},
                {"key": "location", "label": "Location", "type": "text"},
                {"key": "acquired", "label": "Acquired", "type": "date"},
                {"key": "in_use", "label": "In Use", "type": "boolean"},
            ],
        }
    )


# ---------------------------------------------------------------------------
# Template sharing (request-based, same handshake as assets)
# ---------------------------------------------------------------------------


def share_template(owner: str, tid: str, shared_with: list[dict], by: str) -> dict | None:
    """Replace a personal template's shared_with (request-based) and notify new
    targets. Global templates are managed via restrict_roles, not shares."""
    # Lazy import — these are asset-sharing internals shared with
    # assets_service's own update_access()/_apply_share_response(), not
    # template-specific; a module-level import would cycle back here.
    from services.assets_service import (
        _load_features_roles,
        _notify_share_targets,
        _resolve_targets,
    )

    store = _load_template_store(owner)
    tmpl = next((t for t in store["templates"] if t.get("id") == tid), None)
    if tmpl is None:
        return None

    prev_accepted = {
        s.get("target"): list(s.get("accepted") or [])
        for s in (tmpl.get("shared_with") or [])
        if "accepted" in s
    }
    prev_targets = {s.get("target") for s in (tmpl.get("shared_with") or [])}
    valid_targets = {"team", "household"} | set(_load_features_roles())

    cleaned = []
    new_targets = []
    for share in shared_with or []:
        target = (share.get("target") or "").strip()
        if target not in valid_targets and get_user_by_name(target) is None:
            raise ValueError(f"Unknown share target {target!r}")
        cleaned.append({"target": target, "accepted": prev_accepted.get(target, [])})
        if target not in prev_targets:
            new_targets.append(target)

    tmpl["shared_with"] = cleaned
    _save_template_store(owner, store)

    already = set(sum(prev_accepted.values(), []))
    recipients: set[str] = set()
    for target in new_targets:
        for name in _resolve_targets(target):
            if name != by and name not in already:
                recipients.add(name)
    if recipients:
        _notify_share_targets(
            list(recipients),
            by,
            "template_share",
            tmpl.get("label", tmpl.get("key", "a template")),
            {"owner": owner, "template_id": tid},
        )
    return tmpl


def respond_to_template_share(viewer: str, payload: dict, accept: bool) -> bool:
    # Lazy import — see share_template's comment above.
    from services.assets_service import _respond_shares

    owner, tid = payload["owner"], payload["template_id"]
    store = _load_template_store(owner)
    tmpl = next((t for t in store["templates"] if t.get("id") == tid), None)
    if tmpl is None:
        return False
    tmpl["shared_with"], changed = _respond_shares(tmpl.get("shared_with") or [], viewer, accept)
    if changed:
        _save_template_store(owner, store)
    return changed


def leave_template_share(viewer: str, owner: str, tid: str) -> bool:
    return respond_to_template_share(viewer, {"owner": owner, "template_id": tid}, False)


# ---------------------------------------------------------------------------
# Field-value validation
# ---------------------------------------------------------------------------


def _validate_value(fdef: dict, value: Any) -> Any:
    key, ftype = fdef["key"], fdef["type"]
    if ftype == "text":
        if not isinstance(value, str):
            raise ValueError(f"Field {key!r} must be text")
        if len(value) > _TEXT_MAX:
            raise ValueError(f"Field {key!r} is too long (max {_TEXT_MAX} chars)")
        return value
    if ftype == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Field {key!r} must be a number")
        return value
    if ftype == "date":
        try:
            date.fromisoformat(str(value))
        except ValueError:
            raise ValueError(f"Field {key!r} must be a date in YYYY-MM-DD format")
        return str(value)
    if ftype == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"Field {key!r} must be true or false")
        return value
    if ftype == "select":
        if value not in fdef.get("options", []):
            raise ValueError(f"Field {key!r} must be one of: {', '.join(fdef.get('options', []))}")
        return value
    if ftype == "contact":
        # Stores a CRM contact id. No cross-store existence check — the UI
        # validates at pick time; stale ids render as "(contact)" (same
        # tolerance as deals' linked_asset_ids).
        if not isinstance(value, str) or not value.strip() or len(value) > 64:
            raise ValueError(f"Field {key!r} must be a contact id")
        return value.strip()
    raise ValueError(f"Unknown field type {ftype!r}")


def _validate_fields(template: dict, incoming: dict, custom_defs: list[dict] | None = None) -> dict:
    """Validate incoming values against the template.

    Returns {key: value} where None means "unset this key". Unknown keys may only be
    unset (orphaned values from removed template fields stay readable/deletable but
    can never be set) — UNLESS this is a genuinely blank asset (`template` has no
    `key` at all, not just an empty `fields` list — a real template with zero
    fields, like the seeded Folder template, keeps rejecting unknown keys as
    before). A blank asset has no admin-defined field list to validate
    against, so instead it accepts freeform label/value pairs typed directly
    on the asset (owner report, 2026-08-17: a blank asset needs SOME way to
    hold custom data, not just name+notes) — the typed label IS the key
    (trimmed, capped, no slugification — same free-typed-string treatment
    Contacts' own `tags` already get), capped to 40 fields per asset.

    `custom_defs` (2026-08-18) is the blank asset's OWN field-definition list
    — the same typed key/label/type/options shape _validate_field_defs()
    already validates for a real Template, just scoped to one asset instead
    of being reusable. A key with a matching def gets the same type-checked
    treatment a templated field would (via _validate_value); anything else
    still falls back to the freeform behavior above, so a value can be set
    before its def exists. Ignored (has no effect) for a templated asset —
    only ever consulted when `is_blank`.
    """
    defs = {f["key"]: f for f in template.get("fields", [])}
    is_blank = not template.get("key")
    if is_blank and custom_defs:
        defs = {f["key"]: f for f in custom_defs}
    cleaned: dict[str, Any] = {}
    for key, value in (incoming or {}).items():
        if value is None or (isinstance(value, str) and value.strip() == ""):
            cleaned[str(key).strip()[:60] if is_blank else key] = None
            continue
        fdef = defs.get(key)
        if fdef is None:
            if is_blank:
                clean_key = str(key).strip()[:60]
                if clean_key and len(cleaned) < 40:
                    cleaned[clean_key] = str(value).strip()[:2000]
                continue
            raise ValueError(
                f"Unknown field {key!r} for template {template.get('key', '(blank asset)')!r}. "
                f"Valid fields: {sorted(defs) or '(none)'}"
            )
        cleaned[key] = _validate_value(fdef, value)
    return cleaned
