"""Assets module — admin-curated templates, hierarchical assets, sharing, pools.

Templates live instance-wide in brain/_system/asset_templates.json (admin-only writes)
so every viewer and n8n workflow sees the same field structure. Asset records live
per user per workspace in ws_path/Assets/assets.json; pool objects live under the
_household/_team pseudo-users so they survive account deletion. Attachment files are
stored as Assets/files/{asset_id}/{attachment_id}.{ext} — disk names are never
user-controlled.
"""

import re
import shutil
import uuid
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from services import assets_index
from services.auth_service import get_user_by_name, get_user_timezone, list_users
from services.file_service import (
    asset_templates_path,
    assets_files_path,
    assets_path,
    personal_templates_path,
    read_json,
    write_json,
)

FIELD_TYPES = {"text", "number", "date", "boolean", "select"}
ATTACHMENT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/avif": "avif",
    "application/pdf": "pdf",
}
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_ATTACHMENTS = 20
_HISTORY_CAP = 50
_KEY_RE = re.compile(r"^[a-z0-9_]{1,40}$")
_TEXT_MAX = 2000

# Pool pseudo-user per workspace. Pool stores always use the personal base path.
POOL_USERS = {"personal": "_household", "business": "_team"}
POOL_LABEL = {"_household": "household", "_team": "team"}


def _now_iso(user_name: str) -> str:
    try:
        tz = ZoneInfo(get_user_timezone(user_name))
    except Exception:
        tz = timezone.utc
    return datetime.now(tz).isoformat()


# ---------------------------------------------------------------------------
# Templates (instance-level, admin-curated)
# ---------------------------------------------------------------------------


GLOBAL_OWNER = "_global"


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
    fallback to the legacy global-by-key reference for pre-Phase-2 assets."""
    tid = asset.get("template_id")
    if tid:
        return get_template_by_id(tid)
    return get_global_template(asset.get("template") or "")


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
    raise ValueError(f"Unknown field type {ftype!r}")


def _validate_fields(template: dict, incoming: dict) -> dict:
    """Validate incoming values against the template.

    Returns {key: value} where None means "unset this key". Unknown keys may only be
    unset (orphaned values from removed template fields stay readable/deletable but
    can never be set).
    """
    defs = {f["key"]: f for f in template.get("fields", [])}
    cleaned: dict[str, Any] = {}
    for key, value in (incoming or {}).items():
        if value is None or (isinstance(value, str) and value.strip() == ""):
            cleaned[key] = None
            continue
        fdef = defs.get(key)
        if fdef is None:
            raise ValueError(
                f"Unknown field {key!r} for template {template['key']!r}. "
                f"Valid fields: {sorted(defs) or '(none)'}"
            )
        cleaned[key] = _validate_value(fdef, value)
    return cleaned


# ---------------------------------------------------------------------------
# Asset store primitives
# ---------------------------------------------------------------------------


def _load(store_user: str, workspace: str = "personal") -> dict:
    return read_json(assets_path(store_user, workspace), default={"assets": []})


def _save(store_user: str, workspace: str, data: dict) -> None:
    write_json(assets_path(store_user, workspace), data)


def list_assets(store_user: str, workspace: str = "personal") -> list[dict]:
    return _load(store_user, workspace).get("assets", [])


def get_asset(store_user: str, asset_id: str, workspace: str = "personal") -> dict | None:
    return next((a for a in list_assets(store_user, workspace) if a["id"] == asset_id), None)


def _all_stores() -> list[tuple[str, str]]:
    stores: list[tuple[str, str]] = []
    for u in list_users():
        stores.append((u["name"], "personal"))
        stores.append((u["name"], "business"))
    stores.extend([("_household", "personal"), ("_team", "personal")])
    return stores


def _push_history(asset: dict, by: str, action: str, changes: dict | None = None) -> None:
    entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "by": by,
        "action": action,
        "changes": changes or {},
    }
    asset.setdefault("history", []).append(entry)
    asset["history"] = asset["history"][-_HISTORY_CAP:]


def _by_id(assets: list[dict]) -> dict[str, dict]:
    return {a["id"]: a for a in assets}


def _self_and_ancestors(asset: dict, by_id: dict[str, dict]):
    """Yield the asset then each ancestor, guarding against malformed cycles."""
    seen: set[str] = set()
    node: dict | None = asset
    while node is not None and node["id"] not in seen:
        seen.add(node["id"])
        yield node
        node = by_id.get(node.get("parent_id") or "")


def collect_subtree_ids(assets: list[dict], root_id: str) -> set[str]:
    children: dict[str | None, list[str]] = {}
    for a in assets:
        children.setdefault(a.get("parent_id"), []).append(a["id"])
    ids: set[str] = set()
    stack = [root_id]
    while stack:
        current = stack.pop()
        if current in ids:
            continue
        ids.add(current)
        stack.extend(children.get(current, []))
    return ids


def _is_archived(asset: dict) -> bool:
    # Per-node: an asset is hidden only if its OWN flag is set. An archived
    # parent's active children stay visible (they float to top level in the tree
    # because their parent is no longer in the visible set).
    return bool(asset.get("archived"))


def _is_hidden_from(asset: dict, by_id: dict[str, dict], viewer: str) -> bool:
    # Per-node: hiding is set explicitly on each node (children created under a
    # hidden node inherit it at creation time; cascade re-applies to a subtree).
    return viewer in (asset.get("hidden_from") or [])


def _share_access(asset: dict, by_id: dict[str, dict], viewer: str, workspace: str) -> str | None:
    """Best share grant ('edit' > 'read') on THIS node (per-node, not inherited).

    Request-based: a new-style entry carries an `accepted` list and grants only to
    viewers who accepted. A legacy entry (no `accepted` key) is open to whoever the
    target resolves to — keeps pre-Phase-2 shares working until re-shared.
    """
    best: str | None = None
    group = "team" if workspace == "business" else "household"
    for share in asset.get("shared_with") or []:
        if "accepted" in share:
            if viewer not in (share.get("accepted") or []):
                continue
        elif share.get("target") not in (viewer, group):
            continue
        access = share.get("access", "read")
        if access == "edit":
            return "edit"
        best = best or "read"
    return best


def _all_user_names() -> list[str]:
    return [u["name"] for u in list_users()]


def _resolve_targets(target: str) -> list[str]:
    """Expand a share target (user | 'team' | 'household' | role) to member names."""
    if target == "household":
        return _all_user_names()
    if target == "team":
        return [
            u["name"]
            for u in list_users()
            if "business" in (get_user_by_name(u["name"]) or {}).get("workspaces", ["personal"])
        ]
    from services.features_service import load_features

    if target in (load_features().get("roles") or {}):
        return [
            u["name"]
            for u in list_users()
            if (get_user_by_name(u["name"]) or {}).get("feature_role", "member") == target
        ]
    return [target] if get_user_by_name(target) else []


def _notify_share_targets(
    recipients: list[str], sharer: str, kind: str, label: str, payload: dict
) -> None:
    """Send an accept/decline request notification to each recipient (best-effort)."""
    from services import suggestions_service

    noun = "template" if kind == "template_share" else "item"
    for name in recipients:
        if name == sharer:
            continue
        try:
            suggestions_service.add_notification(
                name,
                title=f"{sharer} shared a {noun} with you",
                body=f"“{label}” — accept to add it to your assets.",
                source="assets",
                delivery="in_app",
                action={"type": kind, **payload},
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Asset CRUD
# ---------------------------------------------------------------------------


def create_asset(
    store_user: str,
    data: dict,
    workspace: str = "personal",
    created_by: str = "",
) -> dict:
    # Resolve template by id (global or personal) or the legacy global key.
    tid = data.get("template_id")
    if tid:
        template = get_template_by_id(tid)
    else:
        template = get_global_template(data.get("template") or "")
    if template is None:
        raise ValueError(f"Unknown template {(tid or data.get('template'))!r}")
    template_key = template.get("key")
    template_id = template.get("id")
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("Asset name is required")

    store = _load(store_user, workspace)
    parent_id = data.get("parent_id")
    parent = next((a for a in store["assets"] if a["id"] == parent_id), None) if parent_id else None
    if parent_id and parent is None:
        raise ValueError(f"Parent asset {parent_id!r} not found")

    # Inherit the parent's audience so a child added under a shared asset is
    # automatically shared with (and hidden from) the same people — this is how a
    # shared subtree grows into a "group". Deep-copy so the child's `accepted`
    # list is independent of the parent's.
    inherited_shares = (
        [
            {k: (list(v) if isinstance(v, list) else v) for k, v in s.items()}
            for s in (parent.get("shared_with") or [])
        ]
        if parent
        else []
    )
    inherited_hidden = list(parent.get("hidden_from") or []) if parent else []

    fields: dict[str, Any] = {
        f["key"]: f["default"] for f in template.get("fields", []) if "default" in f
    }
    for key, value in _validate_fields(template, data.get("fields") or {}).items():
        if value is None:
            fields.pop(key, None)
        else:
            fields[key] = value

    now = _now_iso(created_by or store_user)
    asset: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "template": template_key,
        "template_id": template_id,
        "name": name[:200],
        "parent_id": parent_id,
        "fields": fields,
        "notes": data.get("notes"),
        "archived": False,
        "shared_with": inherited_shares,
        "hidden_from": inherited_hidden,
        "attachments": [],
        "history": [],
        "created_at": now,
        "updated_at": now,
        "created_by": created_by,
    }
    _push_history(asset, created_by, "create")
    store["assets"].append(asset)
    _save(store_user, workspace, store)
    if inherited_shares:  # child carries an audience → refresh the share index
        assets_index.reindex_owner(store_user, workspace)
    return asset


def update_asset(
    store_user: str,
    asset_id: str,
    updates: dict,
    workspace: str = "personal",
    by: str = "",
) -> dict | None:
    store = _load(store_user, workspace)
    by_id = _by_id(store["assets"])
    asset = by_id.get(asset_id)
    if asset is None:
        return None

    changes: dict[str, list] = {}

    if "name" in updates and updates["name"]:
        new_name = str(updates["name"]).strip()[:200]
        if new_name != asset["name"]:
            changes["name"] = [asset["name"], new_name]
            asset["name"] = new_name

    if "notes" in updates and updates["notes"] != asset.get("notes"):
        changes["notes"] = [asset.get("notes"), updates["notes"]]
        asset["notes"] = updates["notes"]

    if "parent_id" in updates and updates["parent_id"] != asset.get("parent_id"):
        new_parent = updates["parent_id"]
        if new_parent is not None:
            if new_parent not in by_id:
                raise ValueError(f"Parent asset {new_parent!r} not found")
            if new_parent in collect_subtree_ids(store["assets"], asset_id):
                raise ValueError("Cannot move an asset under itself or its own descendant")
        changes["parent_id"] = [asset.get("parent_id"), new_parent]
        asset["parent_id"] = new_parent

    if "fields" in updates:
        template = resolve_template(asset)
        if template is None:
            raise ValueError(f"Template {asset.get('template')!r} no longer exists")
        for key, value in _validate_fields(template, updates["fields"]).items():
            old = asset["fields"].get(key)
            if value is None:
                if key in asset["fields"]:
                    changes[f"fields.{key}"] = [old, None]
                    asset["fields"].pop(key)
            elif old != value:
                changes[f"fields.{key}"] = [old, value]
                asset["fields"][key] = value

    if changes:
        asset["updated_at"] = _now_iso(by or store_user)
        _push_history(asset, by, "update", changes)
        _save(store_user, workspace, store)
    return asset


def count_active_descendants(store_user: str, asset_id: str, workspace: str = "personal") -> int:
    """Non-archived descendants (excludes the node itself) — drives the archive prompt."""
    assets = list_assets(store_user, workspace)
    ids = collect_subtree_ids(assets, asset_id) - {asset_id}
    return sum(1 for a in assets if a["id"] in ids and not a.get("archived"))


def set_archived(
    store_user: str,
    asset_id: str,
    archived: bool,
    workspace: str = "personal",
    by: str = "",
    cascade: bool = False,
) -> dict | None:
    store = _load(store_user, workspace)
    by_id = _by_id(store["assets"])
    asset = by_id.get(asset_id)
    if asset is None:
        return None
    targets = collect_subtree_ids(store["assets"], asset_id) if cascade else {asset_id}
    changed = False
    for aid in targets:
        node = by_id.get(aid)
        if node is not None and bool(node.get("archived")) != archived:
            node["archived"] = archived
            node["updated_at"] = _now_iso(by or store_user)
            _push_history(node, by, "archive" if archived else "unarchive")
            changed = True
    if changed:
        _save(store_user, workspace, store)
    return asset


def delete_asset(store_user: str, asset_id: str, workspace: str = "personal") -> bool:
    store = _load(store_user, workspace)
    if not any(a["id"] == asset_id for a in store["assets"]):
        return False
    children = [a for a in store["assets"] if a.get("parent_id") == asset_id]
    if children:
        raise ValueError(
            f"This asset has {len(children)} child asset(s) — delete or move them first"
        )
    store["assets"] = [a for a in store["assets"] if a["id"] != asset_id]
    _save(store_user, workspace, store)
    assets_index.reindex_owner(store_user, workspace)
    files_dir = assets_files_path(store_user, workspace) / asset_id
    if files_dir.exists():
        shutil.rmtree(files_dir)
    return True


def update_access(
    store_user: str,
    asset_id: str,
    workspace: str = "personal",
    shared_with: list[dict] | None = None,
    hidden_from: list[str] | None = None,
    by: str = "",
    asset_workspace: str = "personal",
    cascade: bool = True,
) -> dict | None:
    """Replace shared_with and/or hidden_from on the node (and, when cascade,
    on all descendants). asset_workspace is the workspace the asset logically
    belongs to (pool stores are physically 'personal')."""
    store = _load(store_user, workspace)
    asset = _by_id(store["assets"]).get(asset_id)
    if asset is None:
        return None

    group = "team" if asset_workspace == "business" else "household"
    valid_targets = {"team", "household"} | set((_load_features_roles()))

    # Preserve the `accepted` list per target from the current entries, and detect
    # which targets are NEW (only those trigger accept/decline request notifications).
    prev_accepted: dict[str, list[str]] = {
        s.get("target"): list(s.get("accepted") or [])
        for s in (asset.get("shared_with") or [])
        if "accepted" in s
    }
    prev_targets = {s.get("target") for s in (asset.get("shared_with") or [])}

    cleaned_shares: list[dict] | None = None
    new_targets: list[str] = []
    if shared_with is not None:
        cleaned_shares = []
        for share in shared_with:
            target = (share.get("target") or "").strip()
            access = share.get("access", "read")
            if access not in ("read", "edit"):
                raise ValueError(f"Invalid access {access!r} — use 'read' or 'edit'")
            if target not in valid_targets and get_user_by_name(target) is None:
                raise ValueError(f"Unknown share target {target!r}")
            cleaned_shares.append(
                {"target": target, "access": access, "accepted": prev_accepted.get(target, [])}
            )
            if target not in prev_targets:
                new_targets.append(target)

    cleaned_hidden: list[str] | None = None
    if hidden_from is not None:
        for name in hidden_from:
            if get_user_by_name(name) is None:
                raise ValueError(f"Unknown user {name!r} in hidden_from")
        cleaned_hidden = list(dict.fromkeys(hidden_from))

    target_ids = collect_subtree_ids(store["assets"], asset_id) if cascade else {asset_id}
    by_id = _by_id(store["assets"])
    for aid in target_ids:
        node = by_id.get(aid)
        if node is None:
            continue
        if cleaned_shares is not None:
            node["shared_with"] = [dict(s, accepted=list(s["accepted"])) for s in cleaned_shares]
        if cleaned_hidden is not None:
            node["hidden_from"] = list(cleaned_hidden)
        node["updated_at"] = _now_iso(by or store_user)
        _push_history(node, by, "access_update")

    _save(store_user, workspace, store)
    assets_index.reindex_owner(store_user, workspace)

    # Send accept/decline requests to members of newly-added targets (not the owner,
    # not anyone who already accepted).
    already = set(sum(prev_accepted.values(), []))
    recipients: set[str] = set()
    for target in new_targets:
        for name in _resolve_targets(target):
            if name != (by or store_user) and name not in already:
                recipients.add(name)
    if recipients:
        _notify_share_targets(
            list(recipients),
            by or store_user,
            "asset_share",
            asset.get("name", "an item"),
            {"owner": store_user, "workspace": workspace, "asset_id": asset_id},
        )
    return asset


def _load_features_roles() -> list[str]:
    from services.features_service import load_features

    return list((load_features().get("roles") or {}).keys())


def _apply_share_response(
    store_user: str, asset_id: str, viewer: str, accept: bool, workspace: str = "personal"
) -> bool:
    """Add/remove `viewer` in the `accepted` list of every node in the shared subtree
    that carries a request-based share. Returns True if anything changed."""
    store = _load(store_user, workspace)
    changed = False
    for aid in collect_subtree_ids(store["assets"], asset_id):
        node = _by_id(store["assets"]).get(aid)
        if node is None:
            continue
        node["shared_with"], node_changed = _respond_shares(
            node.get("shared_with") or [], viewer, accept
        )
        changed = changed or node_changed
    if changed:
        _save(store_user, workspace, store)
        assets_index.reindex_owner(store_user, workspace)
    return changed


def _respond_shares(shares: list[dict], viewer: str, accept: bool) -> tuple[list[dict], bool]:
    """Apply an accept/decline to a shared_with list. Accept adds the viewer to the
    matching entry's `accepted`; decline removes them — and if the entry targets the
    viewer directly (a per-user share), the whole entry is dropped so the owner no
    longer lists them. Group/role entries just lose the viewer from `accepted`."""
    out: list[dict] = []
    changed = False
    for share in shares:
        if "accepted" not in share:
            out.append(share)
            continue
        if not accept and share.get("target") == viewer:
            changed = True  # per-user share declined/left → drop the entry entirely
            continue
        accepted = share["accepted"]
        if accept and viewer not in accepted:
            accepted.append(viewer)
            changed = True
        elif not accept and viewer in accepted:
            accepted.remove(viewer)
            changed = True
        out.append(share)
    return out, changed


def respond_to_asset_share(viewer: str, payload: dict, accept: bool) -> bool:
    return _apply_share_response(
        payload["owner"], payload["asset_id"], viewer, accept, payload.get("workspace", "personal")
    )


def leave_asset_share(viewer: str, owner: str, asset_id: str, workspace: str = "personal") -> bool:
    return _apply_share_response(owner, asset_id, viewer, False, workspace)


# ---------------------------------------------------------------------------
# Visibility resolution and cross-store lookup
# ---------------------------------------------------------------------------


def list_visible(
    viewer: str,
    workspace: str = "personal",
    include_archived: bool = False,
    is_admin: bool = False,
    pool_edit: tuple | list = (),
) -> list[dict]:
    """Own assets + workspace pool assets + assets shared to the viewer."""
    result: list[dict] = []

    own = list_assets(viewer, workspace)
    for asset in own:
        if include_archived or not _is_archived(asset):
            result.append(asset)

    pool_user = POOL_USERS[workspace]
    pool_label = POOL_LABEL[pool_user]
    pool_assets = list_assets(pool_user)
    pool_by_id = _by_id(pool_assets)
    can_edit_pool = is_admin or pool_label in (pool_edit or [])
    for asset in pool_assets:
        if not is_admin and _is_hidden_from(asset, pool_by_id, viewer):
            continue
        if not include_archived and _is_archived(asset):
            continue
        result.append(
            {**asset, "_owner": pool_label, "_access": "edit" if can_edit_pool else "read"}
        )

    # Only owners who actually share with this viewer (share index routing) —
    # avoids scanning every user's file on each request.
    for owner in assets_index.sharers_for(viewer, workspace):
        if owner == viewer:
            continue
        theirs = list_assets(owner, workspace)
        theirs_by_id = _by_id(theirs)
        for asset in theirs:
            if _is_hidden_from(asset, theirs_by_id, viewer):
                continue
            access = _share_access(asset, theirs_by_id, viewer, workspace)
            if access is None:
                continue
            if not include_archived and _is_archived(asset):
                continue
            result.append({**asset, "_owner": owner, "_access": access})

    return result


def find_asset(
    viewer: str,
    workspace: str,
    asset_id: str,
    is_admin: bool = False,
    pool_edit: tuple | list = (),
) -> dict | None:
    """Locate an asset across own → pool → sharing owners, with viewer permissions.

    Returns {store, store_workspace, asset, relation, can_edit, can_manage, can_delete}
    or None when the asset doesn't exist or is hidden from the viewer.
    """
    own = get_asset(viewer, asset_id, workspace)
    if own is not None:
        return {
            "store": viewer,
            "store_workspace": workspace,
            "asset": own,
            "relation": "own",
            "can_edit": True,
            "can_manage": True,
            "can_delete": True,  # owners can delete their own personal assets
        }

    pool_user = POOL_USERS[workspace]
    pool_assets = list_assets(pool_user)
    pool_by_id = _by_id(pool_assets)
    pool_asset = pool_by_id.get(asset_id)
    if pool_asset is not None:
        if not is_admin and _is_hidden_from(pool_asset, pool_by_id, viewer):
            return None
        can_edit = is_admin or POOL_LABEL[pool_user] in (pool_edit or [])
        return {
            "store": pool_user,
            "store_workspace": "personal",
            "asset": pool_asset,
            "relation": "pool",
            "can_edit": can_edit,
            "can_manage": can_edit,
            "can_delete": is_admin,
        }

    for owner in assets_index.sharers_for(viewer, workspace):
        if owner == viewer:
            continue
        theirs = list_assets(owner, workspace)
        theirs_by_id = _by_id(theirs)
        asset = theirs_by_id.get(asset_id)
        if asset is None:
            continue
        if _is_hidden_from(asset, theirs_by_id, viewer):
            return None
        access = _share_access(asset, theirs_by_id, viewer, workspace)
        if access is None:
            return None
        return {
            "store": owner,
            "store_workspace": workspace,
            "asset": asset,
            "relation": "shared",
            "can_edit": access == "edit",
            "can_manage": False,
            "can_delete": False,
        }
    return None


def convert_to_pool(owner: str, asset_id: str, workspace: str = "personal", by: str = "") -> dict:
    """Move an asset subtree (records + attachment dirs) into the workspace pool store."""
    store = _load(owner, workspace)
    if not any(a["id"] == asset_id for a in store["assets"]):
        raise ValueError("Asset not found")

    ids = collect_subtree_ids(store["assets"], asset_id)
    moving = [a for a in store["assets"] if a["id"] in ids]
    store["assets"] = [a for a in store["assets"] if a["id"] not in ids]

    pool_user = POOL_USERS[workspace]
    for asset in moving:
        asset["shared_with"] = []
        if asset["id"] == asset_id:
            asset["parent_id"] = None
            _push_history(asset, by, "convert_to_pool")

    pool_store = _load(pool_user)
    pool_store["assets"].extend(moving)
    _save(owner, workspace, store)
    _save(pool_user, "personal", pool_store)
    # subtree left the owner's store (shares stripped) → refresh their index entry
    assets_index.reindex_owner(owner, workspace)

    src_base = assets_files_path(owner, workspace)
    dst_base = assets_files_path(pool_user)
    for moved_id in ids:
        src = src_base / moved_id
        if src.exists():
            dst_base.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst_base / moved_id))

    return next(a for a in moving if a["id"] == asset_id)


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------


def _sanitize_filename(raw: str, ext: str) -> str:
    from pathlib import Path as _P

    name = _P(raw or "").name
    name = "".join(c for c in name if c.isprintable()).strip()
    return name[:120] or f"file.{ext}"


def add_attachment(
    store_user: str,
    asset_id: str,
    filename: str,
    mime: str,
    content: bytes,
    workspace: str = "personal",
    by: str = "",
) -> dict:
    ext = ATTACHMENT_TYPES.get(mime)
    if ext is None:
        raise ValueError(f"Unsupported file type {mime!r}")
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise ValueError("File too large (max 10 MB)")

    store = _load(store_user, workspace)
    asset = _by_id(store["assets"]).get(asset_id)
    if asset is None:
        raise ValueError("Asset not found")
    if len(asset.get("attachments") or []) >= MAX_ATTACHMENTS:
        raise ValueError(f"Attachment limit reached (max {MAX_ATTACHMENTS} per asset)")

    att_id = str(uuid.uuid4())
    files_dir = assets_files_path(store_user, workspace) / asset_id
    files_dir.mkdir(parents=True, exist_ok=True)
    (files_dir / f"{att_id}.{ext}").write_bytes(content)

    attachment = {
        "id": att_id,
        "filename": _sanitize_filename(filename, ext),
        "mime": mime,
        "size": len(content),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    asset.setdefault("attachments", []).append(attachment)
    asset["updated_at"] = _now_iso(by or store_user)
    _push_history(asset, by, "attachment_add", {"filename": [None, attachment["filename"]]})
    _save(store_user, workspace, store)
    return attachment


def get_attachment(
    store_user: str, asset_id: str, file_id: str, workspace: str = "personal"
) -> dict | None:
    asset = get_asset(store_user, asset_id, workspace)
    if asset is None:
        return None
    meta = next((f for f in asset.get("attachments") or [] if f["id"] == file_id), None)
    if meta is None:
        return None
    ext = ATTACHMENT_TYPES.get(meta["mime"], "bin")
    path = assets_files_path(store_user, workspace) / asset_id / f"{file_id}.{ext}"
    if not path.exists():
        return None
    return {"path": path, "mime": meta["mime"], "filename": meta["filename"]}


def delete_attachment(
    store_user: str, asset_id: str, file_id: str, workspace: str = "personal", by: str = ""
) -> bool:
    store = _load(store_user, workspace)
    asset = _by_id(store["assets"]).get(asset_id)
    if asset is None:
        return False
    attachments = asset.get("attachments") or []
    meta = next((f for f in attachments if f["id"] == file_id), None)
    if meta is None:
        return False
    asset["attachments"] = [f for f in attachments if f["id"] != file_id]
    asset["updated_at"] = _now_iso(by or store_user)
    _push_history(asset, by, "attachment_delete", {"filename": [meta["filename"], None]})
    _save(store_user, workspace, store)
    ext = ATTACHMENT_TYPES.get(meta["mime"], "bin")
    path = assets_files_path(store_user, workspace) / asset_id / f"{file_id}.{ext}"
    path.unlink(missing_ok=True)
    return True
