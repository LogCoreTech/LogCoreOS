"""Derived share-routing index for the assets module.

`list_visible`/`find_asset` need to know which *other* users share assets with a
viewer without reading every user's asset file on each request. This index maps
owner → workspace → the set of share targets (user names + `team`/`household`) so
resolution only reads the files of owners who actually share with the viewer.

It is a **disposable derived cache** (same rule as the RAG index in MEMORY.md):
`brain/_system/assets_share_index.json`, never a source of truth, rebuildable from
the asset files at any time. Maintained incrementally on sharing changes and
rebuilt on startup / on demand. Reads asset files directly (no import of
assets_service) to avoid a circular import.
"""

from services.file_service import assets_path, brain_path, read_json, write_json


def _index_path():
    return brain_path() / "_system" / "assets_share_index.json"


def _targets_for(owner: str, workspace: str) -> list[str]:
    assets = read_json(assets_path(owner, workspace), default={"assets": []}).get("assets", [])
    targets: set[str] = set()
    for a in assets:
        for share in a.get("shared_with") or []:
            t = share.get("target")
            if t:
                targets.add(t)
    return sorted(targets)


def _load() -> dict:
    return read_json(_index_path(), default={"version": 1, "owners": {}})


def rebuild_share_index() -> dict:
    """Scan all real users × both workspaces and rebuild the index from scratch."""
    from services.auth_service import list_users

    owners: dict[str, dict] = {}
    for user in list_users():
        name = user["name"]
        ws_map = {}
        for workspace in ("personal", "business"):
            targets = _targets_for(name, workspace)
            if targets:
                ws_map[workspace] = targets
        if ws_map:
            owners[name] = ws_map
    index = {"version": 1, "owners": owners}
    write_json(_index_path(), index)
    return index


def _ensure() -> dict:
    """Load the index, building it once if the file is missing."""
    if not _index_path().exists():
        return rebuild_share_index()
    return _load()


def reindex_owner(owner: str, workspace: str) -> None:
    """Recompute one owner+workspace entry from their current asset file."""
    index = _ensure()
    owners = index.setdefault("owners", {})
    ws_map = owners.get(owner, {})
    targets = _targets_for(owner, workspace)
    if targets:
        ws_map[workspace] = targets
    else:
        ws_map.pop(workspace, None)
    if ws_map:
        owners[owner] = ws_map
    else:
        owners.pop(owner, None)
    write_json(_index_path(), index)


def sharers_for(viewer: str, workspace: str) -> list[str]:
    """Owners who share at least one asset with `viewer` in this workspace."""
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
