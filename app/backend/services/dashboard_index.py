"""Derived index for the Dashboards module — two halves:

1. Share-routing (`sharers_for`) — same shape as assets_index.py: which owners
   share at least one dashboard with a given viewer, so list/find don't have to
   scan every user's file on every request.
2. Reverse reference lookup (`references_for`) — (module, record_id) -> which
   dashboards have a block pointing at it, powering "Referenced by N dashboards"
   links on Assets/Contacts/Finance/Tasks/Notes/Journal view surfaces.

Both are a **disposable derived cache** (same rule as the RAG index / other
*_index.py services in MEMORY.md): brain/_system/dashboard_index.json, never a
source of truth, rebuildable from every dashboard file at any time.
"""

from services.file_service import brain_path, dashboards_path, read_json, write_json


def _index_path():
    return brain_path() / "_system" / "dashboard_index.json"


def _load() -> dict:
    return read_json(_index_path(), default={"version": 1, "owners": {}, "refs": {}})


def _share_targets(dashboards: list[dict]) -> list[str]:
    targets: set[str] = set()
    for d in dashboards:
        for share in d.get("shared_with") or []:
            t = share.get("target")
            if t:
                targets.add(t)
    return sorted(targets)


def _refs_for_dashboard(store_user: str, workspace: str, dashboard: dict) -> list[tuple[str, str]]:
    """Return [(module, record_id), ...] this dashboard's blocks point at,
    using each block type's declared record_ref_fields — never per-type
    hardcoded here."""
    from services.dashboard_blocks.registry import REGISTRY

    refs: list[tuple[str, str]] = []
    for block in dashboard.get("blocks") or []:
        spec = REGISTRY.get(block.get("type"))
        if spec is None or not spec.record_ref_fields:
            continue
        config = block.get("config") or {}
        for config_key, module in spec.record_ref_fields.items():
            record_id = config.get(config_key)
            if not record_id:
                continue
            if module.startswith("$"):
                # Target module varies per block instance (e.g. nav_button can
                # point at any module) rather than being fixed per block type —
                # resolve it from the block's own config instead of treating
                # the declared value as a literal module name.
                module = config.get(module[1:])
                if not module:
                    continue
            refs.append((module, record_id))
    return refs


def rebuild_index() -> dict:
    """Full rescan of all real users x both workspaces x both pools."""
    from services.auth_service import list_users
    from services.dashboards_service import POOL_HOUSEHOLD, POOL_TEAM, list_dashboards

    owners: dict[str, dict] = {}
    refs: dict[str, dict[str, list[dict]]] = {}

    stores: list[tuple[str, str]] = []
    for u in list_users():
        stores.append((u["name"], "personal"))
        stores.append((u["name"], "business"))
    stores.extend([(POOL_HOUSEHOLD, "personal"), (POOL_TEAM, "personal")])

    for store_user, workspace in stores:
        dashboards = list_dashboards(store_user, workspace)
        if not dashboards:
            continue
        targets = _share_targets(dashboards)
        if targets:
            owners.setdefault(store_user, {})[workspace] = targets
        for dashboard in dashboards:
            for module, record_id in _refs_for_dashboard(store_user, workspace, dashboard):
                entry = {
                    "dashboard_id": dashboard["id"],
                    "dashboard_name": dashboard.get("name", ""),
                    "owner": dashboard.get("owner", store_user),
                    "store_user": store_user,
                    "workspace": workspace,
                }
                refs.setdefault(module, {}).setdefault(record_id, []).append(entry)

    index = {"version": 1, "owners": owners, "refs": refs}
    write_json(_index_path(), index)
    return index


def _ensure() -> dict:
    if not _index_path().exists():
        return rebuild_index()
    return _load()


def reindex_dashboard(store_user: str, workspace: str, dashboard: dict) -> None:
    """Recompute one dashboard's share-routing + ref entries. Cheaper than a
    full rebuild for the common case of a single dashboard being saved."""
    index = _ensure()
    owners = index.setdefault("owners", {})
    refs = index.setdefault("refs", {})

    # Share routing: recompute this store+workspace's whole target set (still
    # cheap — one file read) rather than trying to diff a single dashboard.
    from services.dashboards_service import list_dashboards

    all_in_store = list_dashboards(store_user, workspace)
    targets = _share_targets(all_in_store)
    ws_map = owners.get(store_user, {})
    if targets:
        ws_map[workspace] = targets
    else:
        ws_map.pop(workspace, None)
    if ws_map:
        owners[store_user] = ws_map
    else:
        owners.pop(store_user, None)

    # Refs: drop every existing entry for this dashboard id, then re-add current ones.
    for module, by_record in list(refs.items()):
        for record_id, entries in list(by_record.items()):
            kept = [e for e in entries if e.get("dashboard_id") != dashboard["id"]]
            if kept:
                by_record[record_id] = kept
            else:
                by_record.pop(record_id, None)
        if not by_record:
            refs.pop(module, None)

    for module, record_id in _refs_for_dashboard(store_user, workspace, dashboard):
        entry = {
            "dashboard_id": dashboard["id"],
            "dashboard_name": dashboard.get("name", ""),
            "owner": dashboard.get("owner", store_user),
            "store_user": store_user,
            "workspace": workspace,
        }
        refs.setdefault(module, {}).setdefault(record_id, []).append(entry)

    write_json(_index_path(), index)


def remove_dashboard(store_user: str, workspace: str, dashboard_id: str) -> None:
    """Strip a deleted dashboard's ref/share entries without a full rebuild."""
    index = _ensure()
    refs = index.setdefault("refs", {})
    for module, by_record in list(refs.items()):
        for record_id, entries in list(by_record.items()):
            kept = [e for e in entries if e.get("dashboard_id") != dashboard_id]
            if kept:
                by_record[record_id] = kept
            else:
                by_record.pop(record_id, None)
        if not by_record:
            refs.pop(module, None)

    from services.dashboards_service import list_dashboards

    owners = index.setdefault("owners", {})
    targets = _share_targets(list_dashboards(store_user, workspace))
    ws_map = owners.get(store_user, {})
    if targets:
        ws_map[workspace] = targets
    else:
        ws_map.pop(workspace, None)
    if ws_map:
        owners[store_user] = ws_map
    else:
        owners.pop(store_user, None)

    write_json(_index_path(), index)


def sharers_for(viewer: str, workspace: str) -> list[str]:
    """Owners who share at least one dashboard with `viewer` in this workspace."""
    group = "team" if workspace == "business" else "household"
    index = _ensure()
    result = []
    for owner, ws_map in index.get("owners", {}).items():
        if owner == viewer:
            continue
        targets = ws_map.get(workspace, [])
        if viewer in targets or group in targets:
            result.append(owner)
    return result


def references_for(
    module: str, record_id: str, viewer: str, viewer_role: str, is_admin: bool, workspace: str
) -> list[dict]:
    """ "Referenced by N dashboards" — filtered through find_dashboard() again so
    a viewer never learns a dashboard exists/its name unless they can see it."""
    from services.dashboards_service import find_dashboard

    index = _ensure()
    raw = index.get("refs", {}).get(module, {}).get(record_id, [])
    visible: list[dict] = []
    seen_ids: set[str] = set()
    for entry in raw:
        dash_id = entry["dashboard_id"]
        if dash_id in seen_ids:
            continue
        found = find_dashboard(viewer, viewer_role, is_admin, entry["workspace"], dash_id)
        if found is None:
            continue
        seen_ids.add(dash_id)
        visible.append(
            {
                "dashboard_id": dash_id,
                "dashboard_name": found["dashboard"].get("name", ""),
                "icon": found["dashboard"].get("icon", "📊"),
            }
        )
    return visible
