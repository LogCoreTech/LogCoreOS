"""Dashboards module — standalone, unlimited, user-created custom dashboards.

Unlike Assets/Finance/Contacts, a dashboard is never owned by a record — it's a
freeform canvas of typed "blocks" a user builds themselves (see
services/dashboard_blocks/ for block resolution). Storage is workspace-scoped via
ws_path, at ws_path/Dashboards/dashboards.json; pool dashboards live under the
_household/_team pseudo-users, mirroring the Assets/Finance/Contacts pool pattern.

Sharing mirrors Assets/Notes exactly (shared_with request-handshake, hidden_from,
pool contributors with no handshake) but without Assets' per-field caps — a
dashboard's only granular unit is the whole block list, so access is just
read < contribute (edit blocks) < edit (also manage sharing/delete).

`owner` is stored explicitly on every record (unlike Assets/Finance, where
ownership = store location) — this is load-bearing for the `share_underlying_data`
exception in dashboard_blocks/render.py, which needs to re-resolve block access
"as the owner" even for pool dashboards that have no store-location owner.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from services import dashboard_index
from services.auth_service import get_user_by_name, list_users
from services.file_service import dashboards_path, read_json, write_json

POOL_HOUSEHOLD = "_household"
POOL_TEAM = "_team"
POOL_USERS = {"personal": POOL_HOUSEHOLD, "business": POOL_TEAM}
POOL_LABEL = {POOL_HOUSEHOLD: "household", POOL_TEAM: "team"}

_NAME_MAX = 80


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_pool(store_user: str) -> bool:
    return store_user in (POOL_HOUSEHOLD, POOL_TEAM)


def pool_for(workspace: str) -> str:
    return POOL_USERS[workspace]


# ---------------------------------------------------------------------------
# Store primitives
# ---------------------------------------------------------------------------


def _load(store_user: str, workspace: str = "personal") -> dict:
    return read_json(dashboards_path(store_user, workspace), default={"dashboards": []})


def _save(store_user: str, workspace: str, data: dict) -> None:
    write_json(dashboards_path(store_user, workspace), data)


def list_dashboards(store_user: str, workspace: str = "personal") -> list[dict]:
    return _load(store_user, workspace).get("dashboards", [])


def get_dashboard(store_user: str, dashboard_id: str, workspace: str = "personal") -> dict | None:
    return next(
        (d for d in list_dashboards(store_user, workspace) if d["id"] == dashboard_id), None
    )


def _by_id(dashboards: list[dict]) -> dict[str, dict]:
    return {d["id"]: d for d in dashboards}


def _all_stores() -> list[tuple[str, str]]:
    stores: list[tuple[str, str]] = []
    for u in list_users():
        stores.append((u["name"], "personal"))
        stores.append((u["name"], "business"))
    stores.extend([(POOL_HOUSEHOLD, "personal"), (POOL_TEAM, "personal")])
    return stores


# ---------------------------------------------------------------------------
# Access resolution — single gate, mirrors finance_service._resolve_book_access
# ---------------------------------------------------------------------------


def _resolve_targets(target: str) -> list[str]:
    """Expand a share target (user | 'team' | 'household' | role:<r>) to member names."""
    if target == "household":
        return [u["name"] for u in list_users()]
    if target == "team":
        return [
            u["name"]
            for u in list_users()
            if "business" in (get_user_by_name(u["name"]) or {}).get("workspaces", ["personal"])
        ]
    if target.startswith("role:"):
        role = target[5:]
        return [
            u["name"]
            for u in list_users()
            if (get_user_by_name(u["name"]) or {}).get("feature_role", "member") == role
        ]
    return [target] if get_user_by_name(target) else []


def _resolve_grant(entries: list[dict]) -> str | None:
    """Specificity-resolved list (caller already filtered to the winning
    specificity level) → best access: edit > contribute > read."""
    best: str | None = None
    for entry in entries:
        access = entry.get("access", "read")
        if access == "edit":
            return "edit"
        if access == "contribute":
            best = "contribute"
        elif best is None:
            best = "read"
    return best


def _share_access(dashboard: dict, viewer: str, workspace: str) -> str | None:
    """Best share grant on this dashboard for a personal (non-pool) store —
    by-name entries fully override group/role entries (matches Assets)."""
    group = "team" if workspace == "business" else "household"
    personal: list[dict] = []
    grouped: list[dict] = []
    for share in dashboard.get("shared_with") or []:
        if viewer not in (share.get("accepted") or []):
            continue
        target = share.get("target")
        (personal if target == viewer else grouped).append(share)
    return _resolve_grant(personal or grouped)


def _hidden_from(dashboard: dict, viewer: str, viewer_role: str = "") -> bool:
    hidden = dashboard.get("hidden_from") or []
    if viewer in hidden:
        return True
    return bool(viewer_role) and f"role:{viewer_role}" in hidden


def _contributor_access(dashboard: dict, viewer: str, workspace: str) -> str | None:
    """Pool dashboards: no handshake — contributors grant is live immediately."""
    group = "team" if workspace == "business" else "household"
    personal = [c for c in dashboard.get("contributors") or [] if c.get("target") == viewer]
    grouped = [c for c in dashboard.get("contributors") or [] if c.get("target") == group]
    return _resolve_grant(personal or grouped)


def resolve_access(
    viewer: str,
    viewer_role: str,
    is_admin: bool,
    store_user: str,
    dashboard: dict,
    workspace: str,
) -> str | None:
    """THE single access gate. Returns 'edit' | 'contribute' | 'read' | None."""
    if is_pool(store_user):
        if is_admin:
            return "edit"
        if _hidden_from(dashboard, viewer, viewer_role):
            return None
        return _contributor_access(dashboard, viewer, workspace)
    if store_user == viewer:
        return "edit"
    if _hidden_from(dashboard, viewer, viewer_role):
        return None
    return _share_access(dashboard, viewer, workspace)


def find_dashboard(
    viewer: str,
    viewer_role: str,
    is_admin: bool,
    workspace: str,
    dashboard_id: str,
) -> dict | None:
    """Locate a dashboard across own → pool → sharing owners.

    Returns {store, store_workspace, dashboard, relation, access} or None.
    """
    own = get_dashboard(viewer, dashboard_id, workspace)
    if own is not None:
        own = _sync_templated_dashboard(viewer, workspace, own)
        return {
            "store": viewer,
            "store_workspace": workspace,
            "dashboard": own,
            "relation": "own",
            "access": "edit",
        }

    pool_user = POOL_USERS[workspace]
    pool_dash = get_dashboard(pool_user, dashboard_id, "personal")
    if pool_dash is not None:
        access = resolve_access(viewer, viewer_role, is_admin, pool_user, pool_dash, workspace)
        if access is None:
            return None
        pool_dash = _sync_templated_dashboard(pool_user, "personal", pool_dash)
        return {
            "store": pool_user,
            "store_workspace": "personal",
            "dashboard": pool_dash,
            "relation": "pool",
            "access": access,
        }

    for owner in dashboard_index.sharers_for(viewer, workspace):
        if owner == viewer:
            continue
        dash = get_dashboard(owner, dashboard_id, workspace)
        if dash is None:
            continue
        access = resolve_access(viewer, viewer_role, is_admin, owner, dash, workspace)
        if access is None:
            return None
        dash = _sync_templated_dashboard(owner, workspace, dash)
        return {
            "store": owner,
            "store_workspace": workspace,
            "dashboard": dash,
            "relation": "shared",
            "access": access,
        }
    return None


def list_visible_dashboards(
    viewer: str, viewer_role: str, is_admin: bool, workspace: str
) -> list[dict]:
    """Own + workspace pool + shared-to-viewer dashboards, annotated _owner/_access."""
    result: list[dict] = []

    for d in list_dashboards(viewer, workspace):
        result.append({**d, "_owner": None, "_access": "edit"})

    pool_user = POOL_USERS[workspace]
    pool_label = POOL_LABEL[pool_user]
    for d in list_dashboards(pool_user, "personal"):
        access = resolve_access(viewer, viewer_role, is_admin, pool_user, d, workspace)
        if access is None:
            continue
        result.append({**d, "_owner": pool_label, "_access": access})

    for owner in dashboard_index.sharers_for(viewer, workspace):
        if owner == viewer:
            continue
        for d in list_dashboards(owner, workspace):
            access = resolve_access(viewer, viewer_role, is_admin, owner, d, workspace)
            if access is None:
                continue
            result.append({**d, "_owner": owner, "_access": access})

    return _attach_template_labels(result)


def _attach_template_labels(items: list[dict]) -> list[dict]:
    """Denormalize each dashboard's template label/icon onto the list item so
    the switcher/picker can group by template without needing per-viewer
    template visibility — a shared dashboard shows its group label even if the
    viewer doesn't own that template themselves (same rationale as
    assets_service.attach_templates)."""
    from services import dashboard_templates_service

    by_id = dashboard_templates_service.all_templates_by_id()
    out = []
    for d in items:
        tmpl = by_id.get(d.get("template_id"))
        out.append(
            {
                **d,
                "_template_label": tmpl.get("label") if tmpl else None,
                "_template_icon": tmpl.get("icon") if tmpl else None,
            }
        )
    return out


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def create_dashboard(
    store_user: str,
    workspace: str,
    owner: str,
    name: str,
    icon: str = "📊",
    template_id: str | None = None,
    subject_id: str | None = None,
) -> dict:
    name = (name or "").strip()[:_NAME_MAX] or "Untitled Dashboard"
    now = _now()
    dashboard: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "name": name,
        "icon": (icon or "📊").strip()[:8],
        "owner": owner,
        "blocks": [],
        "template_id": None,
        "subject_type": None,
        "subject_id": None,
        "shared_with": [],
        "hidden_from": [],
        "contributors": [],
        "share_underlying_data": False,
        "created_at": now,
        "updated_at": now,
    }
    if template_id:
        from services import dashboard_templates_service

        template = dashboard_templates_service.get_template_by_id(template_id)
        if template is None:
            raise ValueError("Template not found")
        if template.get("subject_type") and not subject_id:
            raise ValueError("This template requires a subject")
        dashboard["template_id"] = template_id
        dashboard["subject_type"] = template.get("subject_type")
        dashboard["subject_id"] = subject_id
        dashboard["blocks"] = _sync_blocks_from_template([], template.get("blocks") or [])
    store = _load(store_user, workspace)
    store["dashboards"].append(dashboard)
    _save(store_user, workspace, store)
    return dashboard


# ---------------------------------------------------------------------------
# Templates — block-set sync (live) + per-instance layout independence
# ---------------------------------------------------------------------------


def stacked_layout(existing_blocks: list[dict]) -> dict:
    """A fresh full-width slot stacked below everything already placed — mirrors
    Dashboard.jsx::addBlock()'s nextY() (fixed 2026-08-09 to compute this same
    real integer instead of a y:Infinity sentinel). Not prefixed private since
    agent_service.py's add_dashboard_block tool reuses it directly, so the
    agent's own bottom-stack math can never independently drift from the UI's."""

    def bottom(bp: str) -> int:
        ys = [
            (b.get("layout", {}).get(bp) or {}).get("y", 0)
            + (b.get("layout", {}).get(bp) or {}).get("h", 0)
            for b in existing_blocks
        ]
        return max(ys) if ys else 0

    return {
        "lg": {"x": 0, "y": bottom("lg"), "w": 12, "h": 9},
        "sm": {"x": 0, "y": bottom("sm"), "w": 12, "h": 9},
    }


def _sync_blocks_from_template(
    current_blocks: list[dict], template_blocks: list[dict]
) -> list[dict]:
    """Reconcile an instance's blocks against its template's current blocks,
    keyed by slot id. Type/config/existence are fully template-controlled; an
    EXISTING slot's own stored layout is left untouched — that's the entire
    mechanism behind "block set stays synced, layout goes independent." A new
    slot gets a freshly stacked layout, which immediately becomes that
    instance's own independent layout from then on."""
    existing_by_id = {b["id"]: b for b in current_blocks if b.get("id")}
    synced: list[dict] = []
    for tb in template_blocks:
        slot_id = tb["id"]
        existing = existing_by_id.get(slot_id)
        layout = (
            existing["layout"] if existing and existing.get("layout") else stacked_layout(synced)
        )
        synced.append(
            {
                "id": slot_id,
                "type": tb["type"],
                "config": tb.get("config") or {},
                "layout": layout,
            }
        )
    return synced


def _persist_single(store_user: str, workspace: str, dashboard: dict) -> None:
    store = _load(store_user, workspace)
    for i, d in enumerate(store["dashboards"]):
        if d["id"] == dashboard["id"]:
            store["dashboards"][i] = dashboard
            break
    _save(store_user, workspace, store)


def _sync_templated_dashboard(store_user: str, workspace: str, dashboard: dict) -> dict:
    """Self-healing sync-on-read (same shape as resolve_default_dashboard_id's
    self-healing): if the template's block set has changed since this instance
    was last read, reconcile and persist. A deleted template leaves the
    instance frozen at its last-synced blocks rather than erroring — templates
    can't actually be deleted while referenced (see
    dashboard_templates_service.delete_template), so this is defense in depth,
    not the primary guarantee."""
    tid = dashboard.get("template_id")
    if not tid:
        return dashboard
    from services import dashboard_templates_service

    template = dashboard_templates_service.get_template_by_id(tid)
    if template is None:
        return dashboard
    synced = _sync_blocks_from_template(dashboard.get("blocks") or [], template.get("blocks") or [])
    if synced == dashboard.get("blocks"):
        return dashboard
    dashboard["blocks"] = synced
    dashboard["updated_at"] = _now()
    _persist_single(store_user, workspace, dashboard)
    return dashboard


def set_subject(
    store_user: str, workspace: str, dashboard_id: str, subject_id: str | None, by: str = ""
) -> dict | None:
    store = _load(store_user, workspace)
    dashboard = _by_id(store["dashboards"]).get(dashboard_id)
    if dashboard is None:
        return None
    if not dashboard.get("template_id"):
        raise ValueError("Only a dashboard created from a template has a subject")
    dashboard["subject_id"] = (subject_id or "").strip() or None
    dashboard["updated_at"] = _now()
    _save(store_user, workspace, store)
    return dashboard


def detach_template(
    store_user: str, workspace: str, dashboard_id: str, by: str = ""
) -> dict | None:
    """Escape hatch: freezes the dashboard's currently-synced blocks/layout in
    place as an ordinary freeform dashboard — no more template sync, and its
    blocks become independently addable/removable/editable again."""
    store = _load(store_user, workspace)
    dashboard = _by_id(store["dashboards"]).get(dashboard_id)
    if dashboard is None:
        return None
    dashboard["template_id"] = None
    dashboard["subject_type"] = None
    dashboard["subject_id"] = None
    dashboard["updated_at"] = _now()
    _save(store_user, workspace, store)
    return dashboard


def update_dashboard(
    store_user: str, workspace: str, dashboard_id: str, updates: dict, by: str = ""
) -> dict | None:
    """Update name/icon/blocks (bulk block-array replace)."""
    store = _load(store_user, workspace)
    dashboard = _by_id(store["dashboards"]).get(dashboard_id)
    if dashboard is None:
        return None

    if "name" in updates and updates["name"]:
        dashboard["name"] = str(updates["name"]).strip()[:_NAME_MAX]
    if "icon" in updates:
        dashboard["icon"] = str(updates["icon"] or "📊").strip()[:8]
    if "blocks" in updates:
        if dashboard.get("template_id"):
            dashboard["blocks"] = _apply_layout_only(dashboard["blocks"], updates["blocks"])
        else:
            dashboard["blocks"] = _validate_blocks(updates["blocks"])

    dashboard["updated_at"] = _now()
    _save(store_user, workspace, store)
    dashboard_index.reindex_dashboard(store_user, workspace, dashboard)
    return dashboard


def _apply_layout_only(current_blocks: list[dict], incoming: list[dict]) -> list[dict]:
    """Templated dashboards: the block set (type/config/existence) is
    template-controlled — only position/size can be customized per instance.
    Enforced here regardless of what the client sends, mirroring how e.g.
    assets re-validates contribute-caps server-side rather than trusting the UI."""
    incoming_by_id = {b.get("id"): b for b in incoming or [] if b.get("id")}
    out = []
    for b in current_blocks:
        inc = incoming_by_id.get(b["id"])
        layout = b["layout"]
        if inc and inc.get("layout"):
            layout = {
                "lg": inc["layout"].get("lg") or layout.get("lg"),
                "sm": inc["layout"].get("sm") or layout.get("sm"),
            }
        out.append({**b, "layout": layout})
    return out


def _validate_blocks(blocks: list[dict]) -> list[dict]:
    from services.dashboard_blocks.registry import REGISTRY

    cleaned: list[dict] = []
    for b in blocks or []:
        btype = b.get("type")
        if btype not in REGISTRY:
            raise ValueError(f"Unknown block type {btype!r}")
        block_id = b.get("id") or str(uuid.uuid4())
        layout = b.get("layout") or {}
        cleaned.append(
            {
                "id": block_id,
                "type": btype,
                "config": b.get("config") or {},
                "layout": {
                    "lg": layout.get("lg") or {"x": 0, "y": 0, "w": 12, "h": 9},
                    "sm": layout.get("sm") or {"x": 0, "y": 0, "w": 12, "h": 9},
                },
            }
        )
    return cleaned


def set_share_underlying_data(
    store_user: str, workspace: str, dashboard_id: str, value: bool, by: str
) -> dict | None:
    """Owner-only setter — checked against the `owner` field, NOT edit access,
    since this is the one deliberate access-bypass lever in the whole system."""
    store = _load(store_user, workspace)
    dashboard = _by_id(store["dashboards"]).get(dashboard_id)
    if dashboard is None:
        return None
    if dashboard.get("owner") != by:
        raise PermissionError("Only the dashboard owner can change this setting")
    dashboard["share_underlying_data"] = bool(value)
    dashboard["updated_at"] = _now()
    _save(store_user, workspace, store)
    return dashboard


def update_access(
    store_user: str,
    workspace: str,
    dashboard_id: str,
    shared_with: list[dict] | None = None,
    hidden_from: list[str] | None = None,
    contributors: list[dict] | None = None,
    by: str = "",
) -> dict | None:
    store = _load(store_user, workspace)
    dashboard = _by_id(store["dashboards"]).get(dashboard_id)
    if dashboard is None:
        return None

    if is_pool(store_user):
        if shared_with is not None:
            raise ValueError("Pool dashboards use 'contributors', not 'shared_with'")
    elif contributors is not None:
        raise ValueError("'contributors' only applies to pool dashboards")

    prev_accepted: dict[str, list[str]] = {
        s.get("target"): list(s.get("accepted") or []) for s in (dashboard.get("shared_with") or [])
    }
    prev_targets = {s.get("target") for s in (dashboard.get("shared_with") or [])}

    new_targets: list[str] = []
    if shared_with is not None:
        cleaned = []
        for share in shared_with:
            target = (share.get("target") or "").strip()
            access = share.get("access", "read")
            if access not in ("read", "contribute", "edit"):
                raise ValueError(f"Invalid access {access!r}")
            valid = target in ("team", "household") or get_user_by_name(target) is not None
            if not valid:
                raise ValueError(f"Unknown share target {target!r}")
            cleaned.append(
                {"target": target, "access": access, "accepted": prev_accepted.get(target, [])}
            )
            if target not in prev_targets:
                new_targets.append(target)
        dashboard["shared_with"] = cleaned

    if hidden_from is not None:
        dashboard["hidden_from"] = list(dict.fromkeys(hidden_from))

    if contributors is not None:
        group = "team" if workspace == "business" else "household"
        cleaned_c = []
        for entry in contributors:
            target = (entry.get("target") or "").strip()
            if target != group and get_user_by_name(target) is None:
                raise ValueError(f"Unknown contributor target {target!r}")
            access = entry.get("access", "read")
            if access not in ("read", "contribute", "edit"):
                raise ValueError(f"Invalid access {access!r}")
            cleaned_c.append({"target": target, "access": access})
        dashboard["contributors"] = cleaned_c

    dashboard["updated_at"] = _now()
    _save(store_user, workspace, store)
    dashboard_index.reindex_dashboard(store_user, workspace, dashboard)

    already = set(sum(prev_accepted.values(), []))
    recipients: set[str] = set()
    for target in new_targets:
        for name in _resolve_targets(target):
            if name != (by or store_user) and name not in already:
                recipients.add(name)
    if recipients:
        _notify_share_targets(list(recipients), by or store_user, dashboard)
    return dashboard


def _notify_share_targets(recipients: list[str], sharer: str, dashboard: dict) -> None:
    from services import suggestions_service

    for name in recipients:
        if name == sharer:
            continue
        try:
            suggestions_service.add_notification(
                name,
                title=f"{sharer} shared a dashboard with you",
                body=f"“{dashboard.get('name', 'a dashboard')}” — accept to add it to your dashboards.",
                source="dashboards",
                delivery="in_app",
                action={
                    "type": "dashboard_share",
                    "owner": sharer,
                    "dashboard_id": dashboard["id"],
                },
            )
        except Exception:
            pass


def _respond_shares(shares: list[dict], viewer: str, accept: bool) -> tuple[list[dict], bool]:
    out: list[dict] = []
    changed = False
    for share in shares:
        if not accept and share.get("target") == viewer:
            changed = True
            continue
        accepted = share.get("accepted") or []
        if accept and viewer not in accepted:
            accepted = accepted + [viewer]
            changed = True
        elif not accept and viewer in accepted:
            accepted = [n for n in accepted if n != viewer]
            changed = True
        out.append({**share, "accepted": accepted})
    return out, changed


def respond_to_share(
    viewer: str, owner: str, workspace: str, dashboard_id: str, accept: bool
) -> bool:
    store = _load(owner, workspace)
    dashboard = _by_id(store["dashboards"]).get(dashboard_id)
    if dashboard is None:
        return False
    dashboard["shared_with"], changed = _respond_shares(
        dashboard.get("shared_with") or [], viewer, accept
    )
    if changed:
        _save(owner, workspace, store)
        dashboard_index.reindex_dashboard(owner, workspace, dashboard)
    return changed


def leave_share(viewer: str, owner: str, workspace: str, dashboard_id: str) -> bool:
    return respond_to_share(viewer, owner, workspace, dashboard_id, False)


# ---------------------------------------------------------------------------
# Delete — self-healing floor-of-one rule (no stored "protected" flag)
# ---------------------------------------------------------------------------


def delete_dashboard(
    viewer: str, workspace: str, dashboard_id: str, is_admin: bool = False
) -> None:
    """Raises ValueError('not_found') or ValueError('floor_of_one')."""
    store = _load(viewer, workspace)
    if not any(d["id"] == dashboard_id for d in store["dashboards"]):
        raise ValueError("not_found")
    owned = [d for d in store["dashboards"] if d["id"] == dashboard_id]
    if not owned:
        raise ValueError("not_found")
    if len(store["dashboards"]) == 1:
        raise ValueError("floor_of_one")
    store["dashboards"] = [d for d in store["dashboards"] if d["id"] != dashboard_id]
    _save(viewer, workspace, store)
    dashboard_index.remove_dashboard(viewer, workspace, dashboard_id)


def resolve_default_dashboard_id(
    viewer: str, viewer_role: str, is_admin: bool, workspace: str, saved_default: str | None
) -> str | None:
    """Self-healing default resolution: prefer the saved default if it still
    resolves; else the viewer's only owned dashboard (floor-of-one); else the
    first dashboard they own; else None (empty state)."""
    own = list_dashboards(viewer, workspace)
    if saved_default and find_dashboard(viewer, viewer_role, is_admin, workspace, saved_default):
        return saved_default
    if len(own) == 1:
        return own[0]["id"]
    if own:
        return own[0]["id"]
    return None
