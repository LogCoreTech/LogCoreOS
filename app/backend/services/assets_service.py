"""Assets module — admin-curated templates, hierarchical assets, sharing, pools.

Templates live instance-wide in brain/_system/asset_templates.json (admin-only writes)
so every viewer and n8n workflow sees the same field structure. Asset records live
per user per workspace in ws_path/Assets/assets.json; pool objects live under the
_household/_team pseudo-users so they survive account deletion. Attachment files are
stored as Assets/files/{asset_id}/{attachment_id}.{ext} — disk names are never
user-controlled.
"""

import contextlib
import copy
import shutil
import threading
import uuid
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from services import assets_index
from services.auth_service import get_user_by_name, get_user_timezone, list_users
from services.file_service import (
    assets_files_path,
    assets_path,
    read_json,
    user_path,
    write_json,
)

# Templates (CRUD, sharing, field-def/value validation) live in their own
# module (services/assets_templates_service.py, split out 2026-09-16, R6) —
# re-exported here so every existing `assets_service.create_template(...)`
# / `assets_service.GLOBAL_OWNER` / etc. caller (routers, agent_tools,
# dashboard blocks, tests — all going through the `assets_service` module
# object rather than importing these names directly) keeps working
# unchanged. The asset-record functions below (create_asset/update_asset/
# attach_template/list_assets_for_contact) use the validation/lookup helpers
# directly too.
from services.assets_templates_service import (  # noqa: F401
    FIELD_TYPES,
    GLOBAL_OWNER,
    _validate_field_defs,
    _validate_fields,
    _validate_value,
    all_templates_by_id,
    attach_templates,
    create_template,
    delete_template,
    get_global_template,
    get_template,
    get_template_by_id,
    insert_example_template,
    leave_template_share,
    list_global_templates,
    list_personal_templates,
    list_templates,
    resolve_template,
    respond_to_template_share,
    share_template,
    template_reference_count,
    update_template,
    visible_templates,
)

ATTACHMENT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/avif": "avif",
    "application/pdf": "pdf",
}
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_ATTACHMENTS = 20
MAX_COMMENTS = 100
MAX_COMMENT_LEN = 2000
_HISTORY_CAP = 50

# What a "contribute"-level user may ADD to an asset (per-share/contributor caps).
CONTRIBUTE_ADDS = {"comments", "files", "children"}

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
# Asset store primitives
# ---------------------------------------------------------------------------


# Per-(store_user, workspace) lock, held across a full load-mutate-save cycle.
# Originally added to update_access() and _apply_share_response() (fixed
# 2026-09-07) — same unlocked race as auth.json's role-update bug: an admin
# revoking one target's access could have that change silently reverted by a
# DIFFERENT recipient's own concurrent accept/decline on the same assets.json
# file. This ALSO closes the read side of the separate privilege-escalation bug
# in _respond_shares() (a recipient accepting their own share could get
# promoted to a different target's higher grant) against concurrent
# interleaving, though the missing target-membership check itself — the actual
# escalation bug — is a separate fix (see the sharing audit's own consolidation
# item). This file's other ~18 _save() call sites had the same theoretical
# exposure; all of them were migrated to the same lock (2026-09-16, R8).
_assets_locks: dict[tuple[str, str], threading.Lock] = {}
_assets_locks_guard = threading.Lock()


def _assets_lock(store_user: str, workspace: str) -> threading.Lock:
    key = (store_user, workspace)
    with _assets_locks_guard:
        if key not in _assets_locks:
            _assets_locks[key] = threading.Lock()
        return _assets_locks[key]


@contextlib.contextmanager
def _assets_locks_for(*keys: tuple[str, str]):
    """Acquire the per-store locks for MULTIPLE (store_user, workspace) keys at
    once — for the few mutators (convert_to_pool, transfer_ownership) that
    read-modify-write two different stores' assets.json in one call. Keys are
    deduped (a plain threading.Lock isn't reentrant — locking the same key
    twice in one thread would self-deadlock if source and destination ever
    resolved to the same store) and acquired in sorted order so that two
    concurrent calls locking the same pair of stores in opposite directions
    (e.g. a transfer A→B racing a transfer B→A) can never deadlock each other."""
    with contextlib.ExitStack() as stack:
        for key in sorted(set(keys)):
            stack.enter_context(_assets_lock(*key))
        yield


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


def _is_hidden_from(
    asset: dict, by_id: dict[str, dict], viewer: str, viewer_role: str = ""
) -> bool:
    # Per-node: hiding is set explicitly on each node (children created under a
    # hidden node inherit it at creation time; cascade re-applies to a subtree).
    # Entries are user names or dynamic "role:<feature_role>" entries — role
    # entries follow the role (future hires included), unlike snapshot shares.
    hidden = asset.get("hidden_from") or []
    if viewer in hidden:
        return True
    return bool(viewer_role) and f"role:{viewer_role}" in hidden


def normalize_caps(caps: dict | None) -> dict:
    """Clean a contribute-caps object: {fields: [keys...], add: [comments|files|children]}.
    A missing caps object defaults to comment-only (safest useful grant)."""
    if not caps:
        return {"fields": [], "add": ["comments"]}
    fields = [str(k) for k in (caps.get("fields") or []) if str(k).strip()][:50]
    add = [a for a in (caps.get("add") or []) if a in CONTRIBUTE_ADDS]
    return {"fields": fields, "add": add}


def _merge_caps(a: dict | None, b: dict) -> dict:
    if a is None:
        return {"fields": list(b["fields"]), "add": list(b["add"])}
    return {
        "fields": list(dict.fromkeys(a["fields"] + b["fields"])),
        "add": list(dict.fromkeys(a["add"] + b["add"])),
    }


def _resolve_grant(entries: list[dict], viewer: str, group: str) -> tuple[str | None, dict | None]:
    """Specificity-based grant resolution: an entry targeting the viewer BY NAME
    beats any group/role entry — otherwise restricting one member of a group
    (e.g. crew gets contribute while the household has edit) is impossible.
    Within the winning specificity level, the highest access wins
    ('edit' > 'contribute' > 'read'); caps union only across same-level
    contribute entries. Returns (access, caps).
    """
    best: str | None = None
    caps: dict | None = None
    for entry in entries:
        access = entry.get("access", "read")
        if access == "edit":
            return "edit", None
        if access == "contribute":
            best = "contribute"
            caps = _merge_caps(caps, normalize_caps(entry.get("caps")))
        elif best is None:
            best = "read"
    return best, caps if best == "contribute" else None


def _share_access(
    asset: dict, by_id: dict[str, dict], viewer: str, workspace: str
) -> tuple[str | None, dict | None]:
    """Best share grant on THIS node (per-node, not inherited), resolved by
    specificity — see _resolve_grant. Returns (access, caps).

    Request-based: a new-style entry carries an `accepted` list and grants only to
    viewers who accepted. A legacy entry (no `accepted` key) is open to whoever the
    target resolves to — keeps pre-Phase-2 shares working until re-shared.
    """
    group = "team" if workspace == "business" else "household"
    personal: list[dict] = []
    grouped: list[dict] = []
    for share in asset.get("shared_with") or []:
        if "accepted" in share:
            if viewer not in (share.get("accepted") or []):
                continue
        elif share.get("target") not in (viewer, group):
            continue
        (personal if share.get("target") == viewer else grouped).append(share)
    return _resolve_grant(personal or grouped, viewer, group)


def _contributor_caps(
    asset: dict, viewer: str, workspace: str, named_only: bool = False
) -> dict | None:
    """Resolve pool-asset contributor caps for a viewer (no handshake — pool
    assets are already workspace-visible). A by-name entry beats group entries.
    named_only=True considers only by-name entries — used to decide whether a
    pool_edit manager is downgraded to contribute on this specific asset."""
    group = "team" if workspace == "business" else "household"
    personal = [c for c in asset.get("contributors") or [] if c.get("target") == viewer]
    grouped = (
        []
        if named_only
        else [c for c in asset.get("contributors") or [] if c.get("target") == group]
    )
    caps: dict | None = None
    for entry in personal or grouped:
        caps = _merge_caps(caps, normalize_caps(entry.get("caps")))
    return caps


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
    with _assets_lock(store_user, workspace):
        # Resolve template by id (global or personal) or the legacy global key —
        # optional (owner ask, 2026-08-17: standalone assets, mirroring how a
        # Dashboard can start blank instead of from a template). No template_id/
        # template given at all means a genuinely blank asset: no template-
        # derived fields, template stays None on the record.
        tid = data.get("template_id")
        template: dict = {}
        if tid or data.get("template"):
            template = (
                get_template_by_id(tid) if tid else get_global_template(data.get("template") or "")
            )
            if template is None:
                raise ValueError(f"Unknown template {(tid or data.get('template'))!r}")
        template_key = template.get("key")
        template_id = template.get("id")
        name = (data.get("name") or "").strip()
        if not name:
            raise ValueError("Asset name is required")

        # A blank asset's own ad-hoc, per-asset field definitions (2026-08-18) —
        # same typed key/label/type/options shape a real Template uses (owner:
        # "the same picker... so it can create an asset just the same just
        # without a template"). Validated unconditionally (cheap — empty list
        # for a templated asset, where it's never consulted by _validate_fields).
        custom_field_defs = _validate_field_defs(data.get("custom_field_defs") or [])

        store = _load(store_user, workspace)
        parent_id = data.get("parent_id")
        parent = (
            next((a for a in store["assets"] if a["id"] == parent_id), None) if parent_id else None
        )
        if parent_id and parent is None:
            raise ValueError(f"Parent asset {parent_id!r} not found")

        # Inherit the parent's audience so a child added under a shared asset is
        # automatically shared with (and hidden from) the same people — this is how a
        # shared subtree grows into a "group". Deep-copy so the child's `accepted`
        # list and contribute `caps` are independent of the parent's.
        inherited_shares = copy.deepcopy(parent.get("shared_with") or []) if parent else []
        inherited_hidden = list(parent.get("hidden_from") or []) if parent else []
        inherited_contributors = copy.deepcopy(parent.get("contributors") or []) if parent else []

        fields: dict[str, Any] = {
            f["key"]: f["default"] for f in template.get("fields", []) if "default" in f
        }
        for key, value in _validate_fields(
            template, data.get("fields") or {}, custom_field_defs
        ).items():
            if value is None:
                fields.pop(key, None)
            else:
                fields[key] = value

        now = _now_iso(created_by or store_user)
        asset: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "template": template_key,
            "template_id": template_id,
            "custom_field_defs": custom_field_defs,
            "name": name[:200],
            "parent_id": parent_id,
            "fields": fields,
            "notes": data.get("notes"),
            "tags": [
                t.strip() for t in (data.get("tags") or []) if isinstance(t, str) and t.strip()
            ],
            "archived": False,
            "shared_with": inherited_shares,
            "hidden_from": inherited_hidden,
            "contributors": inherited_contributors,
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
        if asset["tags"]:
            from services.tags_service import register_tags

            register_tags(store_user, workspace, asset["tags"])
        return asset


def update_asset(
    store_user: str,
    asset_id: str,
    updates: dict,
    workspace: str = "personal",
    by: str = "",
) -> dict | None:
    with _assets_lock(store_user, workspace):
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

        if "tags" in updates:
            new_tags = [
                t.strip() for t in (updates["tags"] or []) if isinstance(t, str) and t.strip()
            ]
            if new_tags != (asset.get("tags") or []):
                changes["tags"] = [asset.get("tags"), new_tags]
                asset["tags"] = new_tags

        if "parent_id" in updates and updates["parent_id"] != asset.get("parent_id"):
            new_parent = updates["parent_id"]
            if new_parent is not None:
                if new_parent not in by_id:
                    raise ValueError(f"Parent asset {new_parent!r} not found")
                if new_parent in collect_subtree_ids(store["assets"], asset_id):
                    raise ValueError("Cannot move an asset under itself or its own descendant")
            changes["parent_id"] = [asset.get("parent_id"), new_parent]
            asset["parent_id"] = new_parent

        if "custom_field_defs" in updates:
            # Validated and stored before "fields" below runs, deliberately —
            # the frontend edits a blank asset's field defs and its values in
            # the same PATCH, one row at a time, so a value validated against a
            # def added in this very call must see that def, not a stale one.
            new_defs = _validate_field_defs(updates["custom_field_defs"] or [])
            if new_defs != asset.get("custom_field_defs"):
                changes["custom_field_defs"] = [asset.get("custom_field_defs"), new_defs]
                asset["custom_field_defs"] = new_defs

        if "fields" in updates:
            template = resolve_template(asset)
            if template is None:
                raise ValueError(f"Template {asset.get('template')!r} no longer exists")
            for key, value in _validate_fields(
                template, updates["fields"], asset.get("custom_field_defs")
            ).items():
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
            if updates.get("tags"):
                from services.tags_service import register_tags

                register_tags(store_user, workspace, asset["tags"])
        return asset


def attach_template(
    store_user: str, asset_id: str, template_id: str, workspace: str = "personal", by: str = ""
) -> dict | None:
    """Retroactively attach a real Template to a currently-blank asset — the
    second half of "Save as template" (2026-08-18, owner: "it also would
    need a convert to template button as well"). The router creates the
    Template first (a plain create_template() call, from the asset's own
    custom_field_defs) and passes its id here.

    template_id/template are otherwise immutable after creation (AssetUpdate
    has no such field — template choice is create-only everywhere else) —
    this is a deliberate, narrow exception, reachable only through this one
    explicit user-initiated action, not a general PATCH capability. Re-runs
    the asset's existing values through the template's real _validate_value
    checks rather than trusting they already match (the template WAS built
    from these same defs, but a mismatch should still surface as an error,
    not silently corrupt the asset)."""
    with _assets_lock(store_user, workspace):
        store = _load(store_user, workspace)
        by_id = _by_id(store["assets"])
        asset = by_id.get(asset_id)
        if asset is None:
            return None
        if asset.get("template_id"):
            raise ValueError("This asset already uses a template")
        template = get_template_by_id(template_id)
        if template is None:
            raise ValueError(f"Unknown template {template_id!r}")
        validated = _validate_fields(template, asset.get("fields") or {})
        old_template_id = asset.get("template_id")
        asset["template_id"] = template["id"]
        asset["template"] = template.get("key")
        asset["custom_field_defs"] = []
        asset["fields"] = {k: v for k, v in validated.items() if v is not None}
        asset["updated_at"] = _now_iso(by or store_user)
        _push_history(
            asset, by, "attach_template", {"template_id": [old_template_id, template["id"]]}
        )
        _save(store_user, workspace, store)
        return asset


def _comment_audience(store_user: str, asset: dict, asset_workspace: str) -> set[str]:
    """Everyone with edit-level standing on the asset: the owner and accepted
    edit-share users for personal assets; admins + pool_edit grantees for pool
    assets. Comment notifications go to this set (minus the author)."""
    audience: set[str] = set()
    if store_user in POOL_LABEL:
        label = POOL_LABEL[store_user]
        for u in list_users():
            rec = get_user_by_name(u["name"]) or {}
            if rec.get("role") == "admin" or label in (rec.get("pool_edit") or []):
                audience.add(u["name"])
        return audience
    audience.add(store_user)
    for share in asset.get("shared_with") or []:
        if share.get("access") != "edit":
            continue
        if "accepted" in share:
            audience.update(share.get("accepted") or [])
        else:  # legacy open entry — resolve its target
            audience.update(_resolve_targets(share.get("target") or ""))
    return audience


def add_comment(
    store_user: str,
    asset_id: str,
    text: str,
    workspace: str = "personal",
    by: str = "",
    asset_workspace: str = "personal",
) -> dict | None:
    """Append an attributed comment to the asset's log (cap MAX_COMMENTS, oldest
    trimmed) and notify edit-level users with a jump-to-asset action."""
    with _assets_lock(store_user, workspace):
        text = (text or "").strip()
        if not text:
            raise ValueError("Comment text is required")
        if len(text) > MAX_COMMENT_LEN:
            raise ValueError(f"Comment too long (max {MAX_COMMENT_LEN} characters)")
        store = _load(store_user, workspace)
        by_id = _by_id(store["assets"])
        asset = by_id.get(asset_id)
        if asset is None:
            return None
        if asset.get("comments_hidden"):
            raise ValueError("Comments are turned off on this asset")
        comment = {
            "id": str(uuid.uuid4()),
            "by": by,
            "at": _now_iso(by or store_user),
            "text": text,
        }
        comments = list(asset.get("comments") or [])
        comments.append(comment)
        asset["comments"] = comments[-MAX_COMMENTS:]
        asset["updated_at"] = _now_iso(by or store_user)
        _save(store_user, workspace, store)
        _notify_comment(store_user, asset, comment, asset_workspace, by_id)
        return comment


def set_comments_hidden(
    store_user: str, asset_id: str, hidden: bool, workspace: str = "personal", by: str = ""
) -> dict | None:
    """Owner/manager toggle: hide the comments section for ALL users (data kept)."""
    with _assets_lock(store_user, workspace):
        store = _load(store_user, workspace)
        asset = _by_id(store["assets"]).get(asset_id)
        if asset is None:
            return None
        asset["comments_hidden"] = bool(hidden)
        asset["updated_at"] = _now_iso(by or store_user)
        _push_history(asset, by, "comments_off" if hidden else "comments_on")
        _save(store_user, workspace, store)
        return asset


def _notify_comment(
    store_user: str, asset: dict, comment: dict, asset_workspace: str, by_id: dict
) -> None:
    from services import suggestions_service

    author = comment.get("by") or ""
    snippet = comment["text"][:140] + ("…" if len(comment["text"]) > 140 else "")
    for name in sorted(_comment_audience(store_user, asset, asset_workspace) - {author}):
        if _muted_node(name, asset["id"], by_id):
            continue
        try:
            suggestions_service.notify_user(
                name,
                title=f"{author or 'Someone'} commented on “{asset['name']}”",
                body=snippet,
                source="assets",
                action={"type": "open_asset", "asset_id": asset["id"]},
                url=f"/assets?asset={asset['id']}",
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Comment notification mutes — per-user opt-out, applies to a node + its subtree
# ---------------------------------------------------------------------------


def _mutes_path(user_name: str):
    return user_path(user_name) / "Assets" / "comment_mutes.json"


def get_comment_mutes(user_name: str) -> list[str]:
    return read_json(_mutes_path(user_name), default={"muted": []}).get("muted", [])


def set_comment_mute(user_name: str, asset_id: str, muted: bool) -> list[str]:
    mutes = set(get_comment_mutes(user_name))
    if muted:
        mutes.add(asset_id)
    else:
        mutes.discard(asset_id)
    write_json(_mutes_path(user_name), {"muted": sorted(mutes)})
    return sorted(mutes)


def _muted_node(user_name: str, asset_id: str, by_id: dict) -> str | None:
    """Return the id of the node whose mute covers this asset (self or any
    ancestor — muting a parent silences its whole subtree), else None."""
    muted = set(get_comment_mutes(user_name))
    if not muted:
        return None
    seen: set[str] = set()
    cur: str | None = asset_id
    while cur and cur not in seen:
        if cur in muted:
            return cur
        seen.add(cur)
        node = by_id.get(cur)
        cur = node.get("parent_id") if node else None
    return None


def comment_mute_state(
    user_name: str, store_user: str, asset_id: str, workspace: str = "personal"
) -> dict:
    """Effective mute state for the bell popup: muted (self or via ancestor),
    plus which node carries the mute so the UI can explain it."""
    by_id = _by_id(list_assets(store_user, workspace))
    via = _muted_node(user_name, asset_id, by_id)
    return {
        "muted": via is not None,
        "self": asset_id in set(get_comment_mutes(user_name)),
        "via": via,
        "via_name": (by_id.get(via) or {}).get("name") if via else None,
    }


def delete_comment(
    store_user: str, asset_id: str, comment_id: str, workspace: str = "personal"
) -> bool:
    with _assets_lock(store_user, workspace):
        store = _load(store_user, workspace)
        asset = _by_id(store["assets"]).get(asset_id)
        if asset is None:
            return False
        comments = asset.get("comments") or []
        kept = [c for c in comments if c.get("id") != comment_id]
        if len(kept) == len(comments):
            return False
        asset["comments"] = kept
        _save(store_user, workspace, store)
        return True


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
    with _assets_lock(store_user, workspace):
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


def delete_asset(
    store_user: str, asset_id: str, workspace: str = "personal", deleted_by: str = ""
) -> bool:
    with _assets_lock(store_user, workspace):
        store = _load(store_user, workspace)
        asset = next((a for a in store["assets"] if a["id"] == asset_id), None)
        if asset is None:
            return False
        children = [a for a in store["assets"] if a.get("parent_id") == asset_id]
        if children:
            raise ValueError(
                f"This asset has {len(children)} child asset(s) — delete or move them first"
            )

        from module_packages.assets.backend import trash_handlers
        from services import trash_service

        title, subtitle = trash_handlers.describe("asset", asset)
        trash_service.soft_delete(
            store_user=store_user,
            workspace=workspace,
            module="assets",
            record_type="asset",
            original_id=asset_id,
            payload=asset,
            deleted_by=deleted_by,
            title=title,
            subtitle=subtitle,
            move_path=assets_files_path(store_user, workspace) / asset_id,
        )

        store["assets"] = [a for a in store["assets"] if a["id"] != asset_id]
        _save(store_user, workspace, store)
        assets_index.reindex_owner(store_user, workspace)
        return True


def update_access(
    store_user: str,
    asset_id: str,
    workspace: str = "personal",
    shared_with: list[dict] | None = None,
    hidden_from: list[str] | None = None,
    contributors: list[dict] | None = None,
    by: str = "",
    asset_workspace: str = "personal",
    cascade: bool = True,
) -> dict | None:
    """Replace shared_with / hidden_from / contributors on the node (and, when
    cascade, on all descendants). asset_workspace is the workspace the asset
    logically belongs to (pool stores are physically 'personal')."""
    with _assets_lock(store_user, workspace):
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
                if access not in ("read", "contribute", "edit"):
                    raise ValueError(
                        f"Invalid access {access!r} — use 'read', 'contribute' or 'edit'"
                    )
                if target not in valid_targets and get_user_by_name(target) is None:
                    raise ValueError(f"Unknown share target {target!r}")
                entry = {
                    "target": target,
                    "access": access,
                    "accepted": prev_accepted.get(target, []),
                }
                if access == "contribute":
                    entry["caps"] = normalize_caps(share.get("caps"))
                cleaned_shares.append(entry)
                if target not in prev_targets:
                    new_targets.append(target)

        cleaned_hidden: list[str] | None = None
        if hidden_from is not None:
            role_names = set(_load_features_roles())
            for name in hidden_from:
                if name.startswith("role:"):
                    if name[5:] not in role_names:
                        raise ValueError(f"Unknown role {name[5:]!r} in hidden_from")
                elif get_user_by_name(name) is None:
                    raise ValueError(f"Unknown user {name!r} in hidden_from")
            cleaned_hidden = list(dict.fromkeys(hidden_from))

        # Contributors — pool-asset capability grants (no handshake; pool is already
        # workspace-visible). Targets: the workspace group or a named user.
        cleaned_contributors: list[dict] | None = None
        if contributors is not None:
            cleaned_contributors = []
            for entry in contributors:
                target = (entry.get("target") or "").strip()
                if target != group and get_user_by_name(target) is None:
                    raise ValueError(f"Unknown contributor target {target!r}")
                cleaned_contributors.append(
                    {"target": target, "caps": normalize_caps(entry.get("caps"))}
                )

        target_ids = collect_subtree_ids(store["assets"], asset_id) if cascade else {asset_id}
        by_id = _by_id(store["assets"])
        for aid in target_ids:
            node = by_id.get(aid)
            if node is None:
                continue
            if cleaned_shares is not None:
                node["shared_with"] = copy.deepcopy(cleaned_shares)
            if cleaned_hidden is not None:
                node["hidden_from"] = list(cleaned_hidden)
            if cleaned_contributors is not None:
                node["contributors"] = copy.deepcopy(cleaned_contributors)
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
    with _assets_lock(store_user, workspace):
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
    """Apply an accept/decline to a shared_with list — see
    services.sharing.apply_share_response() for the actual logic. Routed
    through the shared helper 2026-09-08: this function previously added the
    viewer to EVERY entry with an `accepted` key regardless of whether that
    entry's own `target` actually named them — a real, live-PoC-confirmed
    privilege-escalation bug (accepting your own household share notification
    could silently promote you to a completely different person's `edit`
    grant on the same asset). Finance's/Contacts'/Notes' own `respond_share()`
    already had the missing target check; this now shares that same logic."""
    from services.sharing import apply_share_response

    return apply_share_response(shares, viewer, accept, _resolve_targets)


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
    viewer_role: str = "",
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
        if not is_admin and _is_hidden_from(asset, pool_by_id, viewer, viewer_role):
            continue
        if not include_archived and _is_archived(asset):
            continue
        # A by-name contributor entry is more specific than the blanket
        # pool_edit grant — it downgrades a (non-admin) manager to contribute
        # on this asset. Group entries never downgrade managers.
        named = None if is_admin else _contributor_caps(asset, viewer, workspace, named_only=True)
        asset_edit = can_edit_pool and named is None
        entry = {**asset, "_owner": pool_label, "_access": "edit" if asset_edit else "read"}
        if not asset_edit:
            caps = named if named is not None else _contributor_caps(asset, viewer, workspace)
            if caps is not None:
                entry["_access"] = "contribute"
                entry["_caps"] = caps
        result.append(entry)

    # Only owners who actually share with this viewer (share index routing) —
    # avoids scanning every user's file on each request.
    for owner in assets_index.sharers_for(viewer, workspace):
        if owner == viewer:
            continue
        theirs = list_assets(owner, workspace)
        theirs_by_id = _by_id(theirs)
        for asset in theirs:
            if _is_hidden_from(asset, theirs_by_id, viewer, viewer_role):
                continue
            access, caps = _share_access(asset, theirs_by_id, viewer, workspace)
            if access is None:
                continue
            if not include_archived and _is_archived(asset):
                continue
            entry = {**asset, "_owner": owner, "_access": access}
            if caps is not None:
                entry["_caps"] = caps
            result.append(entry)

    return result


def asset_links_contact(asset: dict, template: dict | None, contact_id: str) -> bool:
    """True if `asset` references `contact_id` in any contact-type field of
    its own template. Shared by list_assets_for_contact (below) and the
    dashboard Collection block resolver — one implementation of "does this
    asset link to this contact," not two."""
    tmpl = template or {}
    contact_keys = [f["key"] for f in tmpl.get("fields", []) if f.get("type") == "contact"]
    if not contact_keys:
        return False
    fields = asset.get("fields") or {}
    return any(fields.get(k) == contact_id for k in contact_keys)


def list_assets_for_contact(
    viewer: str,
    workspace: str,
    contact_id: str,
    is_admin: bool = False,
    pool_edit: tuple | list = (),
    viewer_role: str = "",
) -> list[dict]:
    """Viewer-visible assets referencing this contact in any contact-type
    template field. Compact records for the contact References section."""
    results: list[dict] = []
    visible = attach_templates(
        list_visible(
            viewer, workspace, is_admin=is_admin, pool_edit=pool_edit, viewer_role=viewer_role
        )
    )
    for a in visible:
        tmpl = a.get("_template") or {}
        if not asset_links_contact(a, tmpl, contact_id):
            continue
        results.append(
            {
                "id": a["id"],
                "name": a.get("name", ""),
                "icon": tmpl.get("icon", ""),
                "template_label": tmpl.get("label", ""),
            }
        )
    return results


def find_asset(
    viewer: str,
    workspace: str,
    asset_id: str,
    is_admin: bool = False,
    pool_edit: tuple | list = (),
    viewer_role: str = "",
) -> dict | None:
    """Locate an asset across own → pool → sharing owners, with viewer permissions.

    Returns {store, store_workspace, asset, relation, can_edit, can_manage,
    can_delete, can_contribute} — can_contribute is the caps dict for a
    contribute-level viewer, else None. None result = doesn't exist / hidden.
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
            "can_contribute": None,
        }

    pool_user = POOL_USERS[workspace]
    pool_assets = list_assets(pool_user)
    pool_by_id = _by_id(pool_assets)
    pool_asset = pool_by_id.get(asset_id)
    if pool_asset is not None:
        if not is_admin and _is_hidden_from(pool_asset, pool_by_id, viewer, viewer_role):
            return None
        # By-name contributor entry downgrades a (non-admin) pool_edit manager
        # to contribute on this asset — see list_visible for the rationale.
        named = (
            None if is_admin else _contributor_caps(pool_asset, viewer, workspace, named_only=True)
        )
        can_edit = (is_admin or POOL_LABEL[pool_user] in (pool_edit or [])) and (
            is_admin or named is None
        )
        return {
            "store": pool_user,
            "store_workspace": "personal",
            "asset": pool_asset,
            "relation": "pool",
            "can_edit": can_edit,
            "can_manage": can_edit,
            "can_delete": is_admin,
            "can_contribute": (
                None
                if can_edit
                else (
                    named if named is not None else _contributor_caps(pool_asset, viewer, workspace)
                )
            ),
        }

    for owner in assets_index.sharers_for(viewer, workspace):
        if owner == viewer:
            continue
        theirs = list_assets(owner, workspace)
        theirs_by_id = _by_id(theirs)
        asset = theirs_by_id.get(asset_id)
        if asset is None:
            continue
        if _is_hidden_from(asset, theirs_by_id, viewer, viewer_role):
            return None
        access, caps = _share_access(asset, theirs_by_id, viewer, workspace)
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
            "can_contribute": caps,
        }
    return None


def convert_to_pool(owner: str, asset_id: str, workspace: str = "personal", by: str = "") -> dict:
    """Move an asset subtree (records + attachment dirs) into the workspace pool store."""
    pool_user = POOL_USERS[workspace]
    with _assets_locks_for((owner, workspace), (pool_user, "personal")):
        store = _load(owner, workspace)
        if not any(a["id"] == asset_id for a in store["assets"]):
            raise ValueError("Asset not found")

        ids = collect_subtree_ids(store["assets"], asset_id)
        moving = [a for a in store["assets"] if a["id"] in ids]
        store["assets"] = [a for a in store["assets"] if a["id"] not in ids]

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


def transfer_ownership(
    owner: str, asset_id: str, workspace: str = "personal", *, new_owner: str, by: str = ""
) -> dict:
    """Move an asset subtree (records + attachment dirs) to another store — a
    named user's store in the SAME workspace, or that workspace's pool.

    Unlike convert_to_pool, share fields are preserved rather than stripped:
    for a named-user destination shared_with/contributors/hidden_from carry over
    unchanged (only the owning store changes). For a pool destination, each
    shared_with entry is converted to an equivalent contributors entry (dropping
    the accept-handshake `accepted` key) since pool assets never read
    shared_with — this keeps the grant functioning instead of silently dying.
    """
    with _assets_locks_for((owner, workspace), (new_owner, workspace)):
        store = _load(owner, workspace)
        if not any(a["id"] == asset_id for a in store["assets"]):
            raise ValueError("Asset not found")

        ids = collect_subtree_ids(store["assets"], asset_id)
        moving = [a for a in store["assets"] if a["id"] in ids]
        store["assets"] = [a for a in store["assets"] if a["id"] not in ids]

        dest_is_pool = new_owner in POOL_USERS.values()
        for asset in moving:
            if dest_is_pool:
                converted = list(asset.get("contributors") or [])
                for share in asset.get("shared_with") or []:
                    entry = {"target": share["target"], "access": share.get("access", "read")}
                    if share.get("access") == "contribute" and "caps" in share:
                        entry["caps"] = share["caps"]
                    converted.append(entry)
                asset["contributors"] = converted
                asset["shared_with"] = []
            if asset["id"] == asset_id:
                asset["parent_id"] = None
                _push_history(asset, by, "transfer_ownership", {"new_owner": [owner, new_owner]})

        dest_store = _load(new_owner, workspace)
        dest_store["assets"].extend(moving)
        _save(owner, workspace, store)
        _save(new_owner, workspace, dest_store)

        assets_index.reindex_owner(owner, workspace)
        if not dest_is_pool:
            assets_index.reindex_owner(new_owner, workspace)

        src_base = assets_files_path(owner, workspace)
        dst_base = assets_files_path(new_owner, workspace)
        for moved_id in ids:
            src = src_base / moved_id
            if src.exists():
                dst_base.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst_base / moved_id))

        return next(a for a in moving if a["id"] == asset_id)


def strip_user_references(user_name: str) -> None:
    """Remove `user_name` from shared_with/contributors/hidden_from/accepted[]
    across every OTHER store (real users + pools). Used when a user account is
    deleted so their name doesn't linger as a dangling reference elsewhere —
    a by-name shared_with entry is dropped entirely (mirrors _respond_shares'
    decline behavior); a group entry just loses them from its accepted[] list."""
    for store_user, workspace in _all_stores():
        if store_user == user_name:
            continue
        with _assets_lock(store_user, workspace):
            store = _load(store_user, workspace)
            changed = False
            for asset in store.get("assets", []):
                kept = []
                for s in asset.get("shared_with") or []:
                    if s.get("target") == user_name:
                        changed = True
                        continue
                    accepted = s.get("accepted")
                    if isinstance(accepted, list) and user_name in accepted:
                        s = {**s, "accepted": [n for n in accepted if n != user_name]}
                        changed = True
                    kept.append(s)
                asset["shared_with"] = kept

                contrib = asset.get("contributors") or []
                new_contrib = [c for c in contrib if c.get("target") != user_name]
                if len(new_contrib) != len(contrib):
                    asset["contributors"] = new_contrib
                    changed = True

                hidden = asset.get("hidden_from") or []
                if user_name in hidden:
                    asset["hidden_from"] = [h for h in hidden if h != user_name]
                    changed = True
            if changed:
                _save(store_user, workspace, store)


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
    with _assets_lock(store_user, workspace):
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
    with _assets_lock(store_user, workspace):
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
