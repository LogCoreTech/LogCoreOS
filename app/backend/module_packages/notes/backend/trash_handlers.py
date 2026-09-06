"""Trash registry contract for the notes module — see module_registry.py's
trash_dispatch()/owned_trash_types and services/trash_service.py's module
docstring for the shared per-module contract. Notes has no JSON payload —
the whole record is the moved .md file (a "note") or directory (a
"folder"), plus any tags nested under it (snapshotted into
`original_location`, since delete_note/delete_folder already drop the live
tags sidecar entries as their last step).

NOT snapshotted, deliberately: the note/folder's _shares.json entry. A
pre-existing, separate gap — delete_note()/delete_folder() never remove the
share sidecar entry on delete in the first place, so it's still sitting
there, unchanged, whether or not this feature exists. Restoring the file
back to its original path makes that dangling entry apply again exactly as
it did before deletion — correct by accident, not because this module does
anything with it. Fixing that pre-existing gap is out of scope here.
"""

from services.file_service import ws_path
from services.notes_service import _folder_path, _note_path, get_note, set_note_tags

RECORD_TYPES = ["note", "folder"]


def describe(record_type: str, payload: dict | None) -> tuple[str, str]:
    path = (payload or {}).get("path", "?")
    name = path.rsplit("/", 1)[-1]
    if record_type == "folder":
        return name, f"Notes folder · {path}"
    return name, f"Notes · {path}"


def restore(store_user: str, workspace: str, entry: dict) -> dict:
    path = entry["original_id"]
    record_type = entry["record_type"]
    file_ref = entry.get("file_ref")
    if not file_ref:
        raise ValueError("Trash entry is missing its file reference")
    src = ws_path(store_user, workspace) / file_ref

    dest = (
        _folder_path(store_user, path, workspace)
        if record_type == "folder"
        else _note_path(store_user, path, workspace)
    )
    if dest.exists():
        kind = "folder" if record_type == "folder" else "note"
        raise ValueError(
            f"A {kind} already exists at that location — it may have already been restored."
        )

    dest.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dest)

    tags = (entry.get("original_location") or {}).get("tags") or {}
    for tag_path, tag_list in tags.items():
        set_note_tags(store_user, workspace, tag_path, tag_list)

    if record_type == "folder":
        return {"type": "folder", "path": path}
    return get_note(store_user, path, workspace)


def access_check(user: dict, workspace: str, entry: dict) -> bool:
    """list_trash_for_user() only ever reads from the caller's own store or
    an enabled (admin-only) pool's store; restore/browse is inherently an
    owner-side operation, not a shared-viewer one — a note someone else
    shared with `user` never lands in `user`'s own Trash, since it was never
    deleted from THEIR store. So every entry that reaches this point is
    already something `user` is entitled to see."""
    return True
