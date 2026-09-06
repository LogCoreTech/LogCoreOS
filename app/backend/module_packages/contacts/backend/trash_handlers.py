"""Trash registry contract for the contacts module — see module_registry.py's
trash_dispatch()/owned_trash_types and services/trash_service.py's module
docstring for the shared per-module contract. Interactions/deals stay
hard-deleted (2026-09-05 owner decision) — a restored contact comes back
without them; their counts are snapshotted into the payload purely so the
Trash preview and the restore response can say so plainly, not so they can
be brought back.
"""

from services.contacts_service import _save_contacts, list_contacts
from services.file_service import contact_photo_path, ws_path

RECORD_TYPES = ["contact"]


def describe(record_type: str, payload: dict | None) -> tuple[str, str]:
    contact = payload or {}
    name = contact.get("name") or "Untitled contact"
    ints = len(contact.get("_trashed_interactions") or [])
    deals = len(contact.get("_trashed_deals") or [])
    if not ints and not deals:
        return name, "Contacts"
    parts = []
    if ints:
        parts.append(f"{ints} interaction{'s' if ints != 1 else ''}")
    if deals:
        parts.append(f"{deals} deal{'s' if deals != 1 else ''}")
    return name, f"Contacts · {' + '.join(parts)} not restorable"


def restore(store_user: str, workspace: str, entry: dict) -> dict:
    payload = dict(entry["payload"])
    trashed_interactions = payload.pop("_trashed_interactions", [])
    trashed_deals = payload.pop("_trashed_deals", [])
    contact = payload

    contacts = list_contacts(store_user, workspace)
    if any(c["id"] == contact["id"] for c in contacts):
        raise ValueError(
            "A contact with this ID already exists — it may have already been restored."
        )

    file_ref = entry.get("file_ref")
    if file_ref and contact.get("photo_ext"):
        src = ws_path(store_user, workspace) / file_ref
        dest = contact_photo_path(store_user, workspace, contact["id"], contact["photo_ext"])
        if src.exists() and not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dest)

    contacts.append(contact)
    _save_contacts(store_user, workspace, contacts)

    if trashed_interactions or trashed_deals:
        return {
            **contact,
            "_warning": "This contact's interaction/deal history was permanently deleted "
            "when it was trashed and could not be restored.",
        }
    return contact


def access_check(user: dict, workspace: str, entry: dict) -> bool:
    """list_trash_for_user() only ever reads from the caller's own store or
    an enabled (admin-only) pool's store, and pool contact deletion is
    already admin-only (see the router's own is_pool gate) — so every entry
    that reaches this point is already something `user` is entitled to
    see."""
    return True
