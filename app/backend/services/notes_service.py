"""CRUD for Notes/ files and folders in the user's Brain.

Notes stay portable plain-.md files; share metadata lives in a sidecar
Notes/_shares.json index keyed by note/folder path (never the source of truth
for content). A share on a folder cascades to everything inside it. Pool notes
live in the _household (personal) / _team (business) pseudo-user Notes stores.
"""

import re
import shutil
from datetime import datetime
from pathlib import Path

from services.file_service import read_json, read_markdown, write_json, write_markdown, ws_path

_SEGMENT_RE = re.compile(r"^[\w \-. ]+$")
_MAX_CONTENT_BYTES = 512_000

POOL_HOUSEHOLD = "_household"
POOL_TEAM = "_team"
ACCESS_LEVELS = {"read", "contribute", "edit"}
ACCESS_ORDER = {"read": 0, "contribute": 1, "edit": 2}


def meets(access: str | None, need: str) -> bool:
    """True if `access` (read|contribute|edit, or None for no access) is at
    least as strong as `need`. The single ordinal comparison every caller that
    gates a note operation by access level should use, rather than each
    re-deriving its own copy of the read < contribute < edit ordering."""
    return ACCESS_ORDER.get(access, -1) >= ACCESS_ORDER[need]


def is_pool(store_user: str) -> bool:
    return store_user in (POOL_HOUSEHOLD, POOL_TEAM)


def pool_for(workspace: str) -> str:
    return POOL_TEAM if workspace == "business" else POOL_HOUSEHOLD


_GETTING_STARTED_PATH = "Getting Started"
_GETTING_STARTED_CONTENT = """# Welcome to Notes

Use the sidebar to create and organize your notes.

## Navigation

- **+ Note** — create a new note (inside the selected folder, or at the root if none selected)
- **+ Folder** — create a folder to organize notes
- Click a folder to open/close it; click it again to deselect it so new notes go to the root
- Hover any note or folder and click **···** for rename, move, or delete options

## Tips

- Notes auto-save as you type — no save button needed
- Your notes are stored as plain Markdown files in your Brain folder
- You can access and edit them from any AI tool that reads your Brain
"""


def _validate_path(path: str) -> None:
    parts = path.split("/")
    if not parts or any(p in ("", ".", "..") for p in parts):
        raise ValueError("Invalid path")
    if not all(_SEGMENT_RE.match(p) for p in parts):
        raise ValueError(
            "Path contains invalid characters (use letters, digits, spaces, hyphens, dots, underscores)"
        )


def _notes_root(user_name: str, workspace: str = "personal") -> Path:
    return ws_path(user_name, workspace) / "Notes"


def _note_path(user_name: str, path: str, workspace: str = "personal") -> Path:
    return _notes_root(user_name, workspace) / f"{path}.md"


def _folder_path(user_name: str, path: str, workspace: str = "personal") -> Path:
    return _notes_root(user_name, workspace) / path


def list_notes(
    user_name: str,
    workspace: str = "personal",
    create_default: bool = True,
    include_archived: bool = False,
) -> list[dict]:
    """Return a flat list of all notes and folders (recursive) for tree-building.
    Every item carries `archived` (bool); by default archived items are omitted
    from the list (pass `include_archived=True` to include them too).

    `create_default=False` for pool/foreign stores so we never write a Getting
    Started note into someone else's or a pool store."""
    root = _notes_root(user_name, workspace)
    if not root.exists():
        return []
    items: list[dict] = []

    def _walk(dir_path: Path, rel: str) -> None:
        try:
            entries = sorted(dir_path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            return
        for p in entries:
            p_rel = f"{rel}/{p.name}" if rel else p.name
            if p.is_dir():
                items.append({"type": "folder", "path": p_rel, "name": p.name})
                _walk(p, p_rel)
            elif p.is_file() and p.suffix == ".md":
                note_rel = f"{rel}/{p.stem}" if rel else p.stem
                items.append(
                    {
                        "type": "note",
                        "path": note_rel,
                        "name": p.stem,
                        "modified_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
                    }
                )

    _walk(root, "")

    # Create a Getting Started note for first-time users (no notes exist yet)
    if create_default and not any(i["type"] == "note" for i in items):
        p = _note_path(user_name, _GETTING_STARTED_PATH, workspace)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(_GETTING_STARTED_CONTENT, encoding="utf-8")
        items.append(
            {
                "type": "note",
                "path": _GETTING_STARTED_PATH,
                "name": "Getting Started",
                "modified_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
            }
        )

    archived_paths = set(load_archived(user_name, workspace))
    for item in items:
        item["archived"] = _is_archived_path(archived_paths, item["path"])
    if not include_archived:
        items = [i for i in items if not i["archived"]]

    return items


def get_note(user_name: str, path: str, workspace: str = "personal") -> dict | None:
    _validate_path(path)
    p = _note_path(user_name, path, workspace)
    if not p.exists():
        return None
    return {
        "path": path,
        "name": Path(path).name,
        "content": read_markdown(p),
        "modified_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
    }


def create_note(user_name: str, path: str, content: str = "", workspace: str = "personal") -> dict:
    _validate_path(path)
    if len(content.encode()) > _MAX_CONTENT_BYTES:
        raise ValueError("Content exceeds 500 KB limit")
    p = _note_path(user_name, path, workspace)
    if p.exists():
        raise ValueError(f"A note already exists at {path!r}")
    write_markdown(p, content)
    return {
        "path": path,
        "name": Path(path).name,
        "content": content,
        "modified_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
    }


def update_note(
    user_name: str, path: str, content: str, workspace: str = "personal"
) -> dict | None:
    _validate_path(path)
    if len(content.encode()) > _MAX_CONTENT_BYTES:
        raise ValueError("Content exceeds 500 KB limit")
    p = _note_path(user_name, path, workspace)
    if not p.exists():
        return None
    write_markdown(p, content)
    return {
        "path": path,
        "name": Path(path).name,
        "content": content,
        "modified_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
    }


def delete_note(user_name: str, path: str, workspace: str = "personal") -> bool:
    _validate_path(path)
    p = _note_path(user_name, path, workspace)
    if not p.exists():
        return False
    p.unlink()
    _drop_archived_entry(user_name, workspace, path)
    return True


def create_folder(user_name: str, path: str, workspace: str = "personal") -> dict:
    _validate_path(path)
    p = _folder_path(user_name, path, workspace)
    if p.exists():
        raise ValueError(f"A folder already exists at {path!r}")
    p.mkdir(parents=True)
    return {"type": "folder", "path": path, "name": Path(path).name}


def delete_folder(user_name: str, path: str, workspace: str = "personal") -> bool:
    _validate_path(path)
    p = _folder_path(user_name, path, workspace)
    if not p.exists() or not p.is_dir():
        return False
    shutil.rmtree(p)
    _drop_archived_prefix(user_name, workspace, path)
    return True


def move_item(
    user_name: str, from_path: str, to_path: str, item_type: str, workspace: str = "personal"
) -> dict:
    """Rename or move a note or folder."""
    _validate_path(from_path)
    _validate_path(to_path)
    root = _notes_root(user_name, workspace)
    if item_type == "note":
        src = root / f"{from_path}.md"
        dst = root / f"{to_path}.md"
    else:
        src = root / from_path
        dst = root / to_path
    if not src.exists():
        raise ValueError(f"Source not found: {from_path!r}")
    if dst.exists():
        raise ValueError(f"Destination already exists: {to_path!r}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    return {"from_path": from_path, "to_path": to_path, "type": item_type}


# ---------------------------------------------------------------------------
# Archiving (sidecar list keyed by path — a folder archive cascades to its
# subtree, same ancestor-walk cascade rule as sharing's _entry_for_path)
# ---------------------------------------------------------------------------


def _archive_file(store_user: str, workspace: str) -> Path:
    return _notes_root(store_user, workspace) / "_archive.json"


def load_archived(store_user: str, workspace: str) -> list[str]:
    return read_json(_archive_file(store_user, workspace), default={"archived": []}).get(
        "archived", []
    )


def _save_archived(store_user: str, workspace: str, paths: list[str]) -> None:
    write_json(_archive_file(store_user, workspace), {"archived": sorted(set(paths))})


def _is_archived_path(archived_paths: set[str], path: str) -> bool:
    """True if `path` itself, or any ancestor folder, is archived — a folder
    archive cascades to everything inside it, same as a folder share does."""
    candidate = path
    while True:
        if candidate in archived_paths:
            return True
        if "/" not in candidate:
            return False
        candidate = candidate.rsplit("/", 1)[0]


def set_archived(store_user: str, workspace: str, path: str, archived: bool) -> None:
    _validate_path(path)
    current = set(load_archived(store_user, workspace))
    if archived:
        current.add(path)
    else:
        current.discard(path)
    _save_archived(store_user, workspace, list(current))


def _drop_archived_entry(store_user: str, workspace: str, path: str) -> None:
    current = load_archived(store_user, workspace)
    if path in current:
        _save_archived(store_user, workspace, [p for p in current if p != path])


def _drop_archived_prefix(store_user: str, workspace: str, path: str) -> None:
    current = load_archived(store_user, workspace)
    remaining = [p for p in current if p != path and not p.startswith(f"{path}/")]
    if remaining != current:
        _save_archived(store_user, workspace, remaining)


# ---------------------------------------------------------------------------
# Sharing (sidecar index keyed by path; folder shares cascade to the subtree)
# ---------------------------------------------------------------------------


def _shares_file(store_user: str, workspace: str) -> Path:
    return _notes_root(store_user, workspace) / "_shares.json"


def load_shares(store_user: str, workspace: str) -> dict:
    return read_json(_shares_file(store_user, workspace), default={"shares": {}}).get("shares", {})


def _save_shares(store_user: str, workspace: str, shares: dict) -> None:
    write_json(_shares_file(store_user, workspace), {"shares": shares})


def resolve_target_users(target: str) -> list[str]:
    from services import auth_service

    users = auth_service.list_users()
    names = [u["name"] for u in users]
    if target == "household":
        return names
    if target == "team":
        return [u["name"] for u in users if "business" in (u.get("workspaces") or ["personal"])]
    if target.startswith("role:"):
        role = target[5:]
        from services.features_service import load_features

        if role not in (load_features().get("roles") or {}):
            raise ValueError(f"Unknown role: {role!r}")
        return [u["name"] for u in users if u.get("feature_role", "member") == role]
    if target in names:
        return [target]
    raise ValueError(f"Unknown share target: {target!r}")


def _matches(entry: dict, viewer: str, role: str, workspace: str) -> bool:
    target = entry.get("target") or ""
    if target == viewer:
        return True
    if target == "team":
        return workspace == "business"
    if target == "household":
        return True
    if target.startswith("role:"):
        return target[5:] == role
    return False


def _accepted(entry: dict, viewer: str) -> bool:
    acc = entry.get("accepted")
    return True if acc is None else viewer in acc


def _rung(entries: list[dict]) -> str | None:
    if not entries:
        return None
    if any(e.get("access", "read") == "edit" for e in entries):
        return "edit"
    if any(e.get("access", "read") == "contribute" for e in entries):
        return "contribute"
    return "read"


def _entry_for_path(shares: dict, path: str) -> dict | None:
    """Most specific share entry covering `path` — the path itself or its
    nearest shared ancestor folder (folder shares cascade to the subtree)."""
    candidate = path
    while True:
        if candidate in shares:
            return shares[candidate]
        if "/" not in candidate:
            return None
        candidate = candidate.rsplit("/", 1)[0]


def resolve_access(
    viewer: str, role: str, is_admin: bool, store_user: str, workspace: str, path: str
) -> str | None:
    if store_user == viewer:
        return "edit"
    shares = load_shares(store_user, workspace)
    entry = _entry_for_path(shares, path) or {}
    hidden = entry.get("hidden_from") or []
    is_hidden = viewer in hidden or f"role:{role}" in hidden

    if is_pool(store_user):
        if is_admin:
            return "edit"
        if is_hidden:
            return None
        matched = [e for e in entry.get("contributors", []) if _matches(e, viewer, role, workspace)]
        by_name = [e for e in matched if e.get("target") == viewer]
        group = [e for e in matched if e.get("target") != viewer]
        return _rung(by_name) or _rung(group) or "read"

    if is_hidden:
        return None
    matched = [
        e
        for e in entry.get("shared_with", [])
        if _matches(e, viewer, role, workspace) and _accepted(e, viewer)
    ]
    by_name = [e for e in matched if e.get("target") == viewer]
    group = [e for e in matched if e.get("target") != viewer]
    return _rung(by_name) or _rung(group)


def _annotate(item: dict, store_user: str, viewer: str, access: str) -> dict:
    out = dict(item)
    if store_user == POOL_HOUSEHOLD:
        out["_owner"] = "household"
    elif store_user == POOL_TEAM:
        out["_owner"] = "team"
    elif store_user != viewer:
        out["_owner"] = store_user
    out["_access"] = access
    return out


def store_for_owner(owner: str | None, viewer: str) -> str:
    if owner == "household":
        return POOL_HOUSEHOLD
    if owner == "team":
        return POOL_TEAM
    return owner or viewer


def list_visible_notes(
    viewer: str, role: str, is_admin: bool, workspace: str, include_archived: bool = False
) -> list[dict]:
    """Own notes + workspace-pool notes + notes/folders shared to the viewer,
    each annotated with _owner/_access (and `archived`). Own items carry no
    _owner. Archived items are omitted by default, per store, same as list_notes."""
    from services.notes_index import sharers_for

    results = [
        dict(i)
        for i in list_notes(
            viewer, workspace, create_default=True, include_archived=include_archived
        )
    ]
    stores = [pool_for(workspace)]
    stores += [s for s in sharers_for(viewer, role, workspace) if s not in stores]
    for store_user in stores:
        for item in list_notes(
            store_user, workspace, create_default=False, include_archived=include_archived
        ):
            access = resolve_access(viewer, role, is_admin, store_user, workspace, item["path"])
            if access:
                results.append(_annotate(item, store_user, viewer, access))
    return results


def find_note_store(
    viewer: str, role: str, is_admin: bool, workspace: str, path: str, owner: str | None = None
):
    """Locate the store + access for a note/folder path the viewer can reach.
    Returns (store_user, access) or None. Checks own, pool, then sharers, in
    that order — first match wins. If the same relative path exists in more
    than one store the viewer can reach, that order picks the winner, which
    may not be the one actually meant. Pass `owner` (a note's `_owner` field,
    as already returned by list_visible_notes/list_notes) to resolve directly
    against that one store instead, when the caller already knows it."""
    _validate_path(path)  # reject traversal before touching the filesystem
    if owner is not None:
        store_user = store_for_owner(owner, viewer)
        exists = (
            _note_path(store_user, path, workspace).exists()
            or _folder_path(store_user, path, workspace).exists()
        )
        if not exists:
            return None
        access = (
            "edit"
            if store_user == viewer
            else resolve_access(viewer, role, is_admin, store_user, workspace, path)
        )
        return (store_user, access) if access else None
    if (
        _note_path(viewer, path, workspace).exists()
        or _folder_path(viewer, path, workspace).exists()
    ):
        return (viewer, "edit")
    from services.notes_index import sharers_for

    stores = [pool_for(workspace)] + sharers_for(viewer, role, workspace)
    for store_user in stores:
        exists = (
            _note_path(store_user, path, workspace).exists()
            or _folder_path(store_user, path, workspace).exists()
        )
        if not exists:
            continue
        access = resolve_access(viewer, role, is_admin, store_user, workspace, path)
        if access:
            return (store_user, access)
    return None


def update_access(
    store_user: str,
    workspace: str,
    path: str,
    shared_with=None,
    hidden_from=None,
    contributors=None,
) -> tuple[dict, list[str]]:
    """Set the audience on one note/folder path. Personal notes use shared_with
    (handshake); pool notes use contributors. Returns (entry, users_to_notify)."""
    pool = is_pool(store_user)
    if pool and shared_with is not None:
        raise ValueError("Pool notes are workspace-visible — use contributors, not shares")
    if not pool and contributors is not None:
        raise ValueError("Contributors are for pool notes — use shared_with")

    shares = load_shares(store_user, workspace)
    entry = shares.get(path, {})
    to_notify: list[str] = []
    if shared_with is not None:
        cleaned = _clean_entries(shared_with, entry.get("shared_with"), pool=False)
        entry["shared_with"] = cleaned
        for e in cleaned:
            accepted = set(e.get("accepted") or [])
            for name in resolve_target_users(e["target"]):
                if name != store_user and name not in accepted:
                    to_notify.append(name)
    if contributors is not None:
        entry["contributors"] = _clean_entries(contributors, entry.get("contributors"), pool=True)
    if hidden_from is not None:
        entry["hidden_from"] = _clean_hidden(hidden_from)
    if entry:
        shares[path] = entry
    else:
        shares.pop(path, None)
    _save_shares(store_user, workspace, shares)
    if not pool:
        from services.notes_index import reindex_owner

        reindex_owner(store_user)
    return (entry, sorted(set(to_notify)))


def _clean_entries(entries, existing, pool: bool) -> list[dict]:
    old_accepted = {e.get("target"): e.get("accepted") for e in (existing or [])}
    out, seen = [], set()
    for e in entries or []:
        target = (e.get("target") or "").strip()
        if not target or target in seen:
            continue
        seen.add(target)
        resolve_target_users(target)  # validates
        access = e.get("access", "read")
        if access not in ACCESS_LEVELS:
            raise ValueError(f"Invalid access level: {access!r}")
        entry = {"target": target, "access": access}
        if not pool:
            prior = old_accepted.get(target)
            entry["accepted"] = prior if isinstance(prior, list) else []
        out.append(entry)
    return out


def _clean_hidden(hidden) -> list[str]:
    out = []
    for token in hidden or []:
        token = (token or "").strip()
        if not token:
            continue
        if token.startswith("role:"):
            from services.features_service import load_features

            if token[5:] not in (load_features().get("roles") or {}):
                raise ValueError(f"Unknown role: {token[5:]!r}")
        else:
            resolve_target_users(token)
        out.append(token)
    return out


def transfer_ownership(
    store_user: str, workspace: str, path: str, item_type: str, *, new_owner: str, by: str = ""
) -> None:
    """Move a note file or folder (+ everything inside, for a folder) to another
    store — a named user's store in the SAME workspace, or that workspace's
    pool. Also relocates every _shares.json entry equal to `path` or nested
    under it (path/...).

    Unlike a pool-conversion-style move, share fields are preserved: for a
    named-user destination shared_with/contributors/hidden_from carry over
    unchanged. For a pool destination, each shared_with entry is converted to
    an equivalent contributors entry — pool notes never read shared_with.
    """
    _validate_path(path)
    src_root = _notes_root(store_user, workspace)
    dst_root = _notes_root(new_owner, workspace)
    if item_type == "note":
        src = src_root / f"{path}.md"
        dst = dst_root / f"{path}.md"
    else:
        src = src_root / path
        dst = dst_root / path
    if not src.exists():
        raise ValueError(f"Source not found: {path!r}")
    if dst.exists():
        raise ValueError(f"Destination already exists: {path!r}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))

    dest_is_pool = is_pool(new_owner)
    src_shares = load_shares(store_user, workspace)
    dst_shares = load_shares(new_owner, workspace)
    moved_keys = [k for k in src_shares if k == path or k.startswith(f"{path}/")]
    for key in moved_keys:
        entry = src_shares.pop(key)
        if dest_is_pool:
            converted = list(entry.get("contributors") or [])
            for share in entry.get("shared_with") or []:
                converted.append({"target": share["target"], "access": share.get("access", "read")})
            entry["contributors"] = converted
            entry["shared_with"] = []
        dst_shares[key] = entry
    if moved_keys:
        _save_shares(store_user, workspace, src_shares)
        _save_shares(new_owner, workspace, dst_shares)

    src_archived = load_archived(store_user, workspace)
    moved_archived = [p for p in src_archived if p == path or p.startswith(f"{path}/")]
    if moved_archived:
        _save_archived(store_user, workspace, [p for p in src_archived if p not in moved_archived])
        dst_archived = set(load_archived(new_owner, workspace))
        dst_archived.update(moved_archived)
        _save_archived(new_owner, workspace, list(dst_archived))

    from services.notes_index import reindex_owner

    reindex_owner(store_user)
    if not dest_is_pool:
        reindex_owner(new_owner)


def strip_user_references(user_name: str) -> None:
    """Remove `user_name` from shared_with/contributors/hidden_from/accepted[]
    across every OTHER store's _shares.json (real users + pools)."""
    from services import auth_service

    stores = [(u["name"], ws) for u in auth_service.list_users() for ws in ("personal", "business")]
    stores += [(POOL_HOUSEHOLD, "personal"), (POOL_TEAM, "business")]
    for store_user, workspace in stores:
        if store_user == user_name:
            continue
        shares = load_shares(store_user, workspace)
        changed = False
        for entry in shares.values():
            kept = []
            for s in entry.get("shared_with") or []:
                if s.get("target") == user_name:
                    changed = True
                    continue
                accepted = s.get("accepted")
                if isinstance(accepted, list) and user_name in accepted:
                    s = {**s, "accepted": [n for n in accepted if n != user_name]}
                    changed = True
                kept.append(s)
            entry["shared_with"] = kept

            contrib = entry.get("contributors") or []
            new_contrib = [c for c in contrib if c.get("target") != user_name]
            if len(new_contrib) != len(contrib):
                entry["contributors"] = new_contrib
                changed = True

            hidden = entry.get("hidden_from") or []
            if user_name in hidden:
                entry["hidden_from"] = [h for h in hidden if h != user_name]
                changed = True
        if changed:
            _save_shares(store_user, workspace, shares)


def respond_share(viewer: str, owner: str, workspace: str, path: str, accept: bool) -> bool:
    shares = load_shares(owner, workspace)
    entry = shares.get(path)
    if not entry:
        return False
    kept = []
    changed = False
    for e in entry.get("shared_with", []):
        try:
            targets_viewer = viewer in resolve_target_users(e.get("target", ""))
        except ValueError:
            targets_viewer = False
        if not targets_viewer:
            kept.append(e)
            continue
        if accept:
            acc = e.setdefault("accepted", [])
            if viewer not in acc:
                acc.append(viewer)
                changed = True
            kept.append(e)
        else:
            if e.get("target") == viewer:
                changed = True
                continue
            acc = e.get("accepted")
            if isinstance(acc, list) and viewer in acc:
                e["accepted"] = [n for n in acc if n != viewer]
                changed = True
            kept.append(e)
    entry["shared_with"] = kept
    shares[path] = entry
    _save_shares(owner, workspace, shares)
    return changed
