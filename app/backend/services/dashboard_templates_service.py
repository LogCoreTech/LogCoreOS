"""Dashboard templates — admin-curated global + per-user personal, mirroring
assets_service.py's template system exactly (owner confirmed this shape).

Unlike asset templates (which define FIELDS an asset instance fills in), a
dashboard template defines a BLOCK SET (type + config per slot, keyed by a
stable slot id) that every dashboard created from it stays synced to — see
dashboards_service.py's `_sync_blocks_from_template` for the read-time
reconciliation that gives "edit the template, every dashboard updates" its
live property without dashboards ever storing a redundant copy of template
structure.

A template block's config may use the literal string "$subject" in place of a
concrete contact_id/asset_id — resolved per-dashboard-instance at render time
(see dashboard_blocks/render.py) against that dashboard's own subject_id.
Template blocks intentionally have no stored layout — see
dashboards_service.py for why.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from services.auth_service import get_user_by_name, list_users
from services.file_service import (
    dashboard_templates_path,
    global_dashboard_templates_path,
    read_json,
    write_json,
)

GLOBAL_OWNER = "_global"
SUBJECT_TYPES = {"contact", "asset"}
_LABEL_MAX = 80


def _template_store_path(owner: str):
    return (
        global_dashboard_templates_path()
        if owner == GLOBAL_OWNER
        else dashboard_templates_path(owner)
    )


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


def visible_templates(
    viewer: str, is_admin: bool = False, feature_role: str = "member"
) -> list[dict]:
    """Templates a viewer can build a dashboard from: role-permitted global +
    own personal + personal templates shared to and accepted by the viewer."""
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


def _validate_template_blocks(blocks: list[dict]) -> list[dict]:
    """Normalize a template's block list — {id, type, config} only, no layout
    (see module docstring). Slot ids are stable identity for the sync
    reconciliation in dashboards_service.py, so an existing id is preserved
    and a new one only gets minted when absent."""
    from services.dashboard_blocks.registry import REGISTRY

    cleaned: list[dict] = []
    for b in blocks or []:
        btype = b.get("type")
        if btype not in REGISTRY:
            raise ValueError(f"Unknown block type {btype!r}")
        cleaned.append(
            {
                "id": b.get("id") or str(uuid.uuid4()),
                "type": btype,
                "config": b.get("config") or {},
            }
        )
    return cleaned


def _validate_subject_type(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if value not in SUBJECT_TYPES:
        raise ValueError(f"Invalid subject_type {value!r}. Valid: {sorted(SUBJECT_TYPES)}, or null")
    return value


def create_template(data: dict, owner: str = GLOBAL_OWNER) -> dict:
    template = {
        "id": str(uuid.uuid4()),
        "label": (data.get("label") or "Untitled Template").strip()[:_LABEL_MAX],
        "icon": (data.get("icon") or "📊").strip()[:8],
        "subject_type": _validate_subject_type(data.get("subject_type")),
        "blocks": _validate_template_blocks(data.get("blocks") or []),
        "owner": owner,
        "shared_with": [],
        "restrict_roles": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    store = _load_template_store(owner)
    store["templates"].append(template)
    _save_template_store(owner, store)
    return template


def update_template(tid: str, updates: dict) -> dict | None:
    """Replace label/icon/subject_type/blocks (+ restrict_roles for global)."""
    found = _find_template(tid)
    if found is None:
        return None
    owner, _ = found
    store = _load_template_store(owner)
    for i, t in enumerate(store["templates"]):
        if t.get("id") != tid:
            continue
        if "label" in updates and updates["label"]:
            t["label"] = str(updates["label"]).strip()[:_LABEL_MAX]
        if "icon" in updates:
            t["icon"] = str(updates["icon"] or "📊").strip()[:8]
        if "subject_type" in updates:
            t["subject_type"] = _validate_subject_type(updates["subject_type"])
        if "blocks" in updates:
            t["blocks"] = _validate_template_blocks(updates["blocks"] or [])
        if "restrict_roles" in updates and owner == GLOBAL_OWNER:
            t["restrict_roles"] = [str(r).strip() for r in (updates["restrict_roles"] or [])]
        store["templates"][i] = t
        _save_template_store(owner, store)
        return t
    return None


def template_reference_count(tid: str) -> int:
    from services.dashboards_service import _all_stores, list_dashboards

    count = 0
    for store_user, workspace in _all_stores():
        for d in list_dashboards(store_user, workspace):
            if d.get("template_id") == tid:
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
            f"{refs} dashboard(s) still use template {tmpl.get('label')!r} — "
            "detach or delete them first"
        )
    store = _load_template_store(owner)
    before = len(store["templates"])
    store["templates"] = [t for t in store["templates"] if t.get("id") != tid]
    if len(store["templates"]) == before:
        return False
    _save_template_store(owner, store)
    return True


# ---------------------------------------------------------------------------
# Personal template sharing — request/accept handshake, mirrors assets exactly
# ---------------------------------------------------------------------------


def _resolve_targets(target: str) -> list[str]:
    from services.dashboards_service import _resolve_targets as _dashboards_resolve_targets

    return _dashboards_resolve_targets(target)


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


def _notify_share_targets(recipients: list[str], sharer: str, tid: str, label: str) -> None:
    from services import suggestions_service

    for name in recipients:
        if name == sharer:
            continue
        try:
            suggestions_service.add_notification(
                name,
                title=f"{sharer} shared a dashboard template with you",
                body=f"“{label}” — accept to use it when creating a dashboard.",
                source="dashboards",
                delivery="in_app",
                action={"type": "dashboard_template_share", "owner": sharer, "template_id": tid},
            )
        except Exception:
            pass


def _load_features_roles() -> list[str]:
    from services.features_service import load_features

    return list((load_features().get("roles") or {}).keys())


def share_template(owner: str, tid: str, shared_with: list[dict], by: str) -> dict | None:
    """Replace a personal template's shared_with (request-based). Global
    templates are managed via restrict_roles, not shares."""
    store = _load_template_store(owner)
    tmpl = next((t for t in store["templates"] if t.get("id") == tid), None)
    if tmpl is None:
        return None

    prev_accepted = {
        s.get("target"): list(s.get("accepted") or []) for s in (tmpl.get("shared_with") or [])
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
        _notify_share_targets(list(recipients), by, tid, tmpl.get("label", "a template"))
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
