"""Admin user-deletion orchestration.

Deleting a user who owns items already shared with someone else needs a
deliberate decision per item — transfer to another user, transfer to the
workspace pool, or delete outright — instead of silently destroying shared
data. This module builds that review (owned+shared items, plus what the
departing user will separately lose access to elsewhere), validates a fully
resolved decision set, and executes it: run every transfer/delete, scrub
dangling references to the departing user from every other store, rebuild the
derived share-index caches, notify new owners, and only then delete the
account + Brain folder. See docs/AGENTS.md "Admin — User Deletion".
"""

import logging

from services import (
    assets_index,
    assets_service,
    auth_service,
    contacts_index,
    contacts_service,
    finance_index,
    finance_service,
    notes_index,
    notes_service,
)

logger = logging.getLogger("logcore.user_deletion")

_POOL_FOR_WORKSPACE = {"personal": "_household", "business": "_team"}


# ---------------------------------------------------------------------------
# Preview — owned+shared items (the decision surface) + blast radius (read-only)
# ---------------------------------------------------------------------------


def _assets_eligible(name: str, workspaces: list[str]) -> list[dict]:
    out = []
    for ws in workspaces:
        assets = assets_service.list_assets(name, ws)
        by_id = {a["id"]: a for a in assets}
        for root in (a for a in assets if a.get("parent_id") is None):
            subtree_ids = assets_service.collect_subtree_ids(assets, root["id"])
            shared = any(
                (by_id[i].get("shared_with") or by_id[i].get("contributors"))
                for i in subtree_ids
                if i in by_id
            )
            if not shared:
                continue
            out.append(
                {
                    "module": "assets",
                    "workspace": ws,
                    "item_id": root["id"],
                    "label": root.get("name", "(unnamed)"),
                    "shared_with": root.get("shared_with") or [],
                    "contributors": root.get("contributors") or [],
                }
            )
    return out


def _finance_eligible(name: str, workspaces: list[str]) -> list[dict]:
    out = []
    for ws in workspaces:
        for book in finance_service.list_books(name, ws):
            shared = bool(book.get("shared_with") or book.get("contributors"))
            if not shared:
                shared = any(
                    a.get("shared_with") or a.get("contributors") for a in book.get("accounts", [])
                )
            if not shared:
                continue
            out.append(
                {
                    "module": "finance",
                    "workspace": ws,
                    "item_id": book["id"],
                    "label": book.get("name", "(unnamed)"),
                    "shared_with": book.get("shared_with") or [],
                    "contributors": book.get("contributors") or [],
                }
            )
    return out


def _contacts_eligible(name: str, workspaces: list[str]) -> list[dict]:
    out = []
    for ws in workspaces:
        for c in contacts_service.list_contacts(name, ws):
            if c.get("self_of"):
                # A user's own contact dies with their account like today —
                # it can never be transferred/deleted independently (enforced
                # in contacts_service too), so it must never surface here as
                # something needing a decision.
                continue
            if not (c.get("shared_with") or c.get("contributors")):
                continue
            out.append(
                {
                    "module": "contacts",
                    "workspace": ws,
                    "item_id": c["id"],
                    "label": c.get("name", "(unnamed)"),
                    "shared_with": c.get("shared_with") or [],
                    "contributors": c.get("contributors") or [],
                }
            )
    return out


def _notes_eligible(name: str, workspaces: list[str]) -> list[dict]:
    out = []
    for ws in workspaces:
        shares = notes_service.load_shares(name, ws)
        keys = set(shares.keys())
        for path, entry in shares.items():
            if not (entry.get("shared_with") or entry.get("contributors")):
                continue
            # Skip entries nested under another shared ancestor — the whole
            # tree travels with its parent as one atomic unit (decision #2).
            parent = path.rsplit("/", 1)[0] if "/" in path else None
            nested = False
            while parent:
                if parent in keys:
                    nested = True
                    break
                parent = parent.rsplit("/", 1)[0] if "/" in parent else None
            if nested:
                continue
            item_type = "note" if notes_service.get_note(name, path, ws) is not None else "folder"
            out.append(
                {
                    "module": "notes",
                    "workspace": ws,
                    "item_id": path,
                    "item_type": item_type,
                    "label": path,
                    "shared_with": entry.get("shared_with") or [],
                    "contributors": entry.get("contributors") or [],
                }
            )
    return out


def _blast(entries: list[dict], module: str, ws: str, id_key: str, label_key: str) -> list[dict]:
    out = []
    for entry in entries:
        owner = entry.get("_owner")
        if not owner:
            continue  # own item, not something they'll lose
        out.append(
            {
                "module": module,
                "workspace": ws,
                "owner": owner,
                "item_id": entry[id_key],
                "label": entry.get(label_key, "(unnamed)"),
                "access": entry.get("_access"),
            }
        )
    return out


def _blast_radius(name: str, role: str, workspaces: list[str]) -> list[dict]:
    """What the departing user will separately lose access to elsewhere —
    read-only context, no admin decision needed. Reuses each module's real
    list_visible* resolver (is_admin=False deliberately: a blanket admin-role
    view isn't a personal grant worth reporting as "lost")."""
    out: list[dict] = []
    for ws in workspaces:
        out += _blast(
            assets_service.list_visible(name, ws, is_admin=False, viewer_role=role),
            "assets",
            ws,
            "id",
            "name",
        )
        out += _blast(
            finance_service.list_visible_books(name, role, False, ws), "finance", ws, "id", "name"
        )
        out += _blast(
            contacts_service.list_visible_contacts(name, role, False, ws),
            "contacts",
            ws,
            "id",
            "name",
        )
        out += _blast(
            notes_service.list_visible_notes(name, role, False, ws), "notes", ws, "path", "path"
        )
    return out


def build_preview(target_user: dict) -> dict:
    name = target_user["name"]
    role = target_user.get("feature_role", "member")
    workspaces = target_user.get("workspaces") or ["personal"]

    eligible = (
        _assets_eligible(name, workspaces)
        + _finance_eligible(name, workspaces)
        + _contacts_eligible(name, workspaces)
        + _notes_eligible(name, workspaces)
    )
    blast = _blast_radius(name, role, workspaces)
    candidates = []
    for u in auth_service.list_users():
        if u["id"] == target_user["id"]:
            continue
        full = auth_service.get_user_by_id(u["id"]) or {}
        candidates.append(
            {"id": u["id"], "name": u["name"], "workspaces": full.get("workspaces", ["personal"])}
        )

    return {"eligible_items": eligible, "blast_radius": blast, "candidate_users": candidates}


# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------


def _item_key(item: dict) -> tuple:
    return (item["module"], item["workspace"], item["item_id"])


def validate_decisions(target_user: dict, decisions: list[dict]) -> None:
    """Recompute the eligible set fresh from disk and confirm every item has a
    decision. Never trusts a client-supplied set — the server is the sole
    source of truth for what's eligible right now."""
    preview = build_preview(target_user)
    eligible_keys = {_item_key(i) for i in preview["eligible_items"]}
    decided_keys = set()
    for d in decisions:
        key = (d["module"], d["workspace"], d["item_id"])
        if key not in eligible_keys:
            continue  # stale/unknown item — ignored, not an error
        if d["action"] == "transfer_user" and not d.get("target_user_id"):
            raise ValueError(f"Missing target user for {key[0]}:{key[2]}")
        decided_keys.add(key)
    missing = eligible_keys - decided_keys
    if missing:
        raise ValueError(
            "Missing a decision for: " + ", ".join(f"{m[0]}:{m[2]}" for m in sorted(missing))
        )


def _delete_asset_tree(store_user: str, root_id: str, workspace: str) -> None:
    """Permanently delete a whole asset subtree, children first — delete_asset
    blocks on any node that still has children."""
    ids = assets_service.collect_subtree_ids(
        assets_service.list_assets(store_user, workspace), root_id
    )
    remaining = set(ids)
    while remaining:
        assets = assets_service.list_assets(store_user, workspace)
        parent_ids = {a.get("parent_id") for a in assets if a["id"] in remaining}
        leaves = [aid for aid in remaining if aid not in parent_ids]
        if not leaves:
            break  # malformed tree guard — should never happen
        for aid in leaves:
            assets_service.delete_asset(store_user, aid, workspace)
        remaining -= set(leaves)


def _delete_item(store_user: str, d: dict) -> None:
    module, ws, item_id = d["module"], d["workspace"], d["item_id"]
    if module == "assets":
        _delete_asset_tree(store_user, item_id, ws)
    elif module == "finance":
        finance_service.delete_book(store_user, ws, item_id)
    elif module == "contacts":
        contacts_service.delete_contact(store_user, ws, item_id)
    elif module == "notes":
        if notes_service.get_note(store_user, item_id, ws) is not None:
            notes_service.delete_note(store_user, item_id, ws)
        else:
            notes_service.delete_folder(store_user, item_id, ws)
    else:
        raise ValueError(f"Unknown module {module!r}")


def _transfer_item(store_user: str, d: dict, new_owner: str, executed_by: str) -> str:
    """Execute a transfer and return the item's label, for the batched
    new-owner notification."""
    module, ws, item_id = d["module"], d["workspace"], d["item_id"]
    if module == "assets":
        result = assets_service.transfer_ownership(
            store_user, item_id, ws, new_owner=new_owner, by=executed_by
        )
        return result.get("name", "an asset")
    if module == "finance":
        result = finance_service.transfer_ownership(
            store_user, ws, item_id, new_owner=new_owner, by=executed_by
        )
        return result.get("name", "a finance book")
    if module == "contacts":
        result = contacts_service.transfer_ownership(
            store_user, ws, item_id, new_owner=new_owner, by=executed_by
        )
        return result.get("name", "a contact")
    if module == "notes":
        item_type = (
            "note" if notes_service.get_note(store_user, item_id, ws) is not None else "folder"
        )
        notes_service.transfer_ownership(
            store_user, ws, item_id, item_type, new_owner=new_owner, by=executed_by
        )
        return item_id
    raise ValueError(f"Unknown module {module!r}")


def execute(target_user: dict, decisions: list[dict], executed_by: str) -> None:
    validate_decisions(target_user, decisions)
    name = target_user["name"]
    notify_map: dict[str, list[str]] = {}

    for d in decisions:
        if d["action"] == "delete":
            _delete_item(name, d)
        elif d["action"] == "transfer_pool":
            new_owner = _POOL_FOR_WORKSPACE[d["workspace"]]
            _transfer_item(name, d, new_owner, executed_by)
        elif d["action"] == "transfer_user":
            target = auth_service.get_user_by_id(d["target_user_id"])
            if not target:
                raise ValueError(f"Unknown target user {d['target_user_id']!r}")
            if d["workspace"] not in (target.get("workspaces") or ["personal"]):
                raise ValueError(
                    f"{target['name']} doesn't have the {d['workspace']} workspace enabled"
                )
            label = _transfer_item(name, d, target["name"], executed_by)
            notify_map.setdefault(target["name"], []).append(label)
        else:
            raise ValueError(f"Unknown action {d['action']!r}")

    # Reference cleanup — strip the departing user from every OTHER store,
    # then rebuild the derived share-index caches (cheap full rescan).
    assets_service.strip_user_references(name)
    finance_service.strip_user_references(name)
    contacts_service.strip_user_references(name)
    notes_service.strip_user_references(name)

    assets_index.rebuild_share_index()
    finance_index.rebuild_share_index()
    contacts_index.rebuild_share_index()
    notes_index.rebuild_share_index()

    # Batched notifications — one per recipient, not per item.
    from services import suggestions_service

    for recipient, labels in notify_map.items():
        try:
            titles = ", ".join(labels[:3]) + (", …" if len(labels) > 3 else "")
            suggestions_service.notify_user(
                recipient,
                title=(
                    f"{executed_by} transferred {len(labels)} item"
                    f"{'s' if len(labels) != 1 else ''} to you"
                ),
                body=titles,
                source="admin",
            )
        except Exception:
            logger.warning("Ownership-transfer notification to %s failed", recipient, exc_info=True)

    # Only now: delete the account + Brain folder. If anything above raised,
    # this is never reached — the account/folder stay intact and retryable
    # (no cross-store transaction exists anywhere in this codebase, so
    # "destroy last" is the safety net, matching convert_to_pool's precedent).
    import shutil

    from services.file_service import user_path

    auth_service.delete_user(target_user["id"])
    brain_dir = user_path(name)
    if brain_dir.exists():
        shutil.rmtree(brain_dir)
