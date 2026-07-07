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

from services.auth_service import get_user_by_name, get_user_timezone, list_users
from services.file_service import (
    asset_templates_path,
    assets_files_path,
    assets_path,
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


def _load_templates() -> dict:
    return read_json(asset_templates_path(), default={"templates": []})


def list_templates() -> list[dict]:
    return _load_templates().get("templates", [])


def get_template(key: str) -> dict | None:
    return next((t for t in list_templates() if t["key"] == key), None)


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


def create_template(data: dict) -> dict:
    key = (data.get("key") or "").strip()
    if not _KEY_RE.match(key):
        raise ValueError(f"Invalid template key {key!r} — use a-z, 0-9, _ (max 40 chars)")
    store = _load_templates()
    if any(t["key"] == key for t in store["templates"]):
        raise ValueError(f"Template {key!r} already exists")
    template = {
        "key": key,
        "label": (data.get("label") or key).strip()[:80],
        "icon": (data.get("icon") or "").strip()[:8],
        "fields": _validate_field_defs(data.get("fields") or []),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    store["templates"].append(template)
    write_json(asset_templates_path(), store)
    return template


def update_template(key: str, updates: dict) -> dict | None:
    """Replace label/icon/fields. The key is immutable (asset records reference it)."""
    store = _load_templates()
    for i, t in enumerate(store["templates"]):
        if t["key"] != key:
            continue
        if "label" in updates and updates["label"]:
            t["label"] = str(updates["label"]).strip()[:80]
        if "icon" in updates:
            t["icon"] = str(updates["icon"] or "").strip()[:8]
        if "fields" in updates:
            t["fields"] = _validate_field_defs(updates["fields"] or [])
        store["templates"][i] = t
        write_json(asset_templates_path(), store)
        return t
    return None


def template_reference_count(key: str) -> int:
    count = 0
    for store_user, workspace in _all_stores():
        count += sum(1 for a in list_assets(store_user, workspace) if a.get("template") == key)
    return count


def delete_template(key: str) -> bool:
    refs = template_reference_count(key)
    if refs:
        raise ValueError(
            f"{refs} asset(s) still use template {key!r} — delete or archive them first"
        )
    store = _load_templates()
    before = len(store["templates"])
    store["templates"] = [t for t in store["templates"] if t["key"] != key]
    if len(store["templates"]) == before:
        return False
    write_json(asset_templates_path(), store)
    return True


def insert_example_template() -> dict:
    """Optional starter for the empty state — created only on explicit admin click."""
    key = "example"
    n = 2
    while get_template(key) is not None:
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


def _is_archived(asset: dict, by_id: dict[str, dict]) -> bool:
    return any(n.get("archived") for n in _self_and_ancestors(asset, by_id))


def _is_hidden_from(asset: dict, by_id: dict[str, dict], viewer: str) -> bool:
    return any(viewer in (n.get("hidden_from") or []) for n in _self_and_ancestors(asset, by_id))


def _share_access(asset: dict, by_id: dict[str, dict], viewer: str, workspace: str) -> str | None:
    """Best share grant ('edit' > 'read') found on the asset or any ancestor."""
    best: str | None = None
    group = "team" if workspace == "business" else "household"
    for node in _self_and_ancestors(asset, by_id):
        for share in node.get("shared_with") or []:
            if share.get("target") in (viewer, group):
                access = share.get("access", "read")
                if access == "edit":
                    return "edit"
                best = best or "read"
    return best


# ---------------------------------------------------------------------------
# Asset CRUD
# ---------------------------------------------------------------------------


def create_asset(
    store_user: str,
    data: dict,
    workspace: str = "personal",
    created_by: str = "",
) -> dict:
    template = get_template(data.get("template") or "")
    if template is None:
        valid = [t["key"] for t in list_templates()]
        raise ValueError(f"Unknown template {data.get('template')!r}. Valid: {valid or '(none)'}")
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("Asset name is required")

    store = _load(store_user, workspace)
    parent_id = data.get("parent_id")
    if parent_id and not any(a["id"] == parent_id for a in store["assets"]):
        raise ValueError(f"Parent asset {parent_id!r} not found")

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
        "template": template["key"],
        "name": name[:200],
        "parent_id": parent_id,
        "fields": fields,
        "notes": data.get("notes"),
        "archived": False,
        "shared_with": [],
        "hidden_from": [],
        "attachments": [],
        "history": [],
        "created_at": now,
        "updated_at": now,
        "created_by": created_by,
    }
    _push_history(asset, created_by, "create")
    store["assets"].append(asset)
    _save(store_user, workspace, store)
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
        template = get_template(asset["template"])
        if template is None:
            raise ValueError(f"Template {asset['template']!r} no longer exists")
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


def set_archived(
    store_user: str, asset_id: str, archived: bool, workspace: str = "personal", by: str = ""
) -> dict | None:
    store = _load(store_user, workspace)
    asset = _by_id(store["assets"]).get(asset_id)
    if asset is None:
        return None
    if bool(asset.get("archived")) != archived:
        asset["archived"] = archived
        asset["updated_at"] = _now_iso(by or store_user)
        _push_history(asset, by, "archive" if archived else "unarchive")
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
) -> dict | None:
    """Replace shared_with and/or hidden_from. asset_workspace is the workspace the
    asset logically belongs to (pool stores are physically 'personal')."""
    store = _load(store_user, workspace)
    asset = _by_id(store["assets"]).get(asset_id)
    if asset is None:
        return None

    if shared_with is not None:
        group = "team" if asset_workspace == "business" else "household"
        cleaned = []
        for share in shared_with:
            target = (share.get("target") or "").strip()
            access = share.get("access", "read")
            if access not in ("read", "edit"):
                raise ValueError(f"Invalid access {access!r} — use 'read' or 'edit'")
            if target != group and get_user_by_name(target) is None:
                raise ValueError(f"Unknown share target {target!r}")
            cleaned.append({"target": target, "access": access})
        asset["shared_with"] = cleaned

    if hidden_from is not None:
        for name in hidden_from:
            if get_user_by_name(name) is None:
                raise ValueError(f"Unknown user {name!r} in hidden_from")
        asset["hidden_from"] = list(dict.fromkeys(hidden_from))

    asset["updated_at"] = _now_iso(by or store_user)
    _push_history(asset, by, "access_update")
    _save(store_user, workspace, store)
    return asset


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
    own_by_id = _by_id(own)
    for asset in own:
        if include_archived or not _is_archived(asset, own_by_id):
            result.append(asset)

    pool_user = POOL_USERS[workspace]
    pool_label = POOL_LABEL[pool_user]
    pool_assets = list_assets(pool_user)
    pool_by_id = _by_id(pool_assets)
    can_edit_pool = is_admin or pool_label in (pool_edit or [])
    for asset in pool_assets:
        if not is_admin and _is_hidden_from(asset, pool_by_id, viewer):
            continue
        if not include_archived and _is_archived(asset, pool_by_id):
            continue
        result.append(
            {**asset, "_owner": pool_label, "_access": "edit" if can_edit_pool else "read"}
        )

    for user in list_users():
        owner = user["name"]
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
            if not include_archived and _is_archived(asset, theirs_by_id):
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
            "can_delete": is_admin,
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

    for user in list_users():
        owner = user["name"]
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
