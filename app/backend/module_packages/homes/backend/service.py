"""Homes CRUD + tag generation. Deliberately kept fully inside this package
(nothing outside module_packages/homes/ needs a Home record directly) —
same "no real external consumer" reasoning module_packages/goals/backend/
service.py's own docstring uses. Pool (household/team) homes live under the
existing `_household`/`_team` pseudo-users, exactly like pool goals/tasks —
no separate pool store, just this same service pointed at the pseudo-user's
name; pool resolution itself lives in router.py, mirroring Goals' own
service/router split exactly.

Every mutation goes through file_service.update_json() (never a raw
read_json()+write_json() pair) — the single lock spans the full
read-modify-write cycle, closing the exact class of lost-update race this
session's own audit found and fixed across Assets/Finance/auth.json."""

import re
import uuid
from datetime import date, datetime, timezone

from services import contacts_service, tags_service, trash_service
from services.file_service import homes_path, read_json, update_json

_NAME_MAX_LEN = 100
_TEXT_MAX_LEN = 2000
_MONEY_MAX = (
    100_000_000  # sane upper bound, not a real-world limit — rejects fat-fingered/garbage input
)
_TAG_SLUG_LEN = 14

_RENT_FIELDS = {
    "landlord_name",
    "landlord_contact_id",
    "monthly_rent",
    "lease_start",
    "lease_end",
    "security_deposit",
}
_OWN_FIELDS = {
    "lender_name",
    "lender_contact_id",
    "monthly_payment",
    "purchase_date",
    "purchase_price",
    "property_tax_annual",
}
_MONEY_FIELDS = {
    "monthly_rent",
    "security_deposit",
    "monthly_payment",
    "purchase_price",
    "property_tax_annual",
}
_DATE_FIELDS = {"lease_start", "lease_end", "purchase_date"}
_CONTACT_ID_FIELDS = {"landlord_contact_id", "lender_contact_id"}


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return (slug or "home")[:_TAG_SLUG_LEN]


def _generate_tag(name: str) -> str:
    """Frozen at creation — renaming a home never changes its tag, so
    nothing already tagged with it goes orphaned. Stays comfortably under
    tags_service._TAG_MAX_LEN (30): 14-char slug + '-' + 8 hex chars = 23."""
    return f"home:{_slugify(name)}-{uuid.uuid4().hex[:8]}"


def _validate_variant_fields(
    ownership_type: str, variant: dict, store_user: str, workspace: str
) -> dict:
    """Validates and returns a clean variant dict for the given
    ownership_type. Raises ValueError (the router converts to 400) on any
    bad field — unknown keys are dropped silently (never persisted), not
    just ignored, since this is the one place a client-supplied dict gets
    written to disk almost verbatim."""
    allowed = _RENT_FIELDS if ownership_type == "rent" else _OWN_FIELDS
    clean: dict = {}
    for key, value in (variant or {}).items():
        if key not in allowed or value is None or value == "":
            continue
        if key in _MONEY_FIELDS:
            # Tolerant of how a human actually types money — "$1,617",
            # "1,617.50", stray whitespace — not just a bare float string.
            # Real gap found live (2026-09-18): a plain `<input type="number">`
            # on the frontend silently blocks the whole form's submission
            # (native HTML5 validation, before React's onSubmit even fires)
            # the instant a comma is typed, with zero visible error — fixed
            # there too (switched to text+inputMode="decimal"), but the
            # backend should never have been strict about this in the first
            # place, since the AI agent tools accept this same field from
            # free-form natural language ("rent is $1,617/mo").
            cleaned = str(value).strip().replace(",", "").replace("$", "")
            try:
                amount = float(cleaned)
            except (TypeError, ValueError):
                raise ValueError(f"{key} must be a number")
            if amount < 0 or amount > _MONEY_MAX:
                raise ValueError(f"{key} must be between 0 and {_MONEY_MAX}")
            clean[key] = amount
        elif key in _DATE_FIELDS:
            try:
                clean[key] = date.fromisoformat(str(value)).isoformat()
            except ValueError:
                raise ValueError(f"{key} must be a valid date (YYYY-MM-DD)")
        elif key in _CONTACT_ID_FIELDS:
            contact_id = str(value)
            if contacts_service.get_contact(store_user, workspace, contact_id) is None:
                raise ValueError(f"{key} does not reference a contact you have access to")
            clean[key] = contact_id
        else:
            text = str(value).strip()[:_NAME_MAX_LEN]
            if text:
                clean[key] = text
    return clean


def list_homes(store_user: str, workspace: str = "personal") -> list[dict]:
    return read_json(homes_path(store_user, workspace), default={"homes": []}).get("homes", [])


def get_home(store_user: str, home_id: str, workspace: str = "personal") -> dict | None:
    return next((h for h in list_homes(store_user, workspace) if h["id"] == home_id), None)


def find_home(viewer: str, workspace: str, home_id: str) -> tuple[str, str, dict] | None:
    """Locates a home the viewer can access — own store first, then the
    workspace's household/team pool store. Two-tier only (Homes has no
    peer-sharing concept, unlike Assets'/Finance's three-tier own->pool->
    sharers finders). Returns (store_user, store_workspace, home); pool
    homes are already open to every pool member with the homes module
    active (same policy list_homes()/get_home() already apply), so no
    additional per-viewer gating happens here.

    Used by the home_health dashboard block resolver, whose config only
    ever carries a bare home_id and no already-resolved pool flag — unlike
    router.py's _store_for(pool: bool, ...), which requires the caller to
    already know personal-vs-pool up front."""
    home = get_home(viewer, home_id, workspace)
    if home is not None:
        return viewer, workspace, home
    pool_user = "_household" if workspace == "personal" else "_team"
    pool_home = get_home(pool_user, home_id, "personal")
    if pool_home is not None:
        return pool_user, "personal", pool_home
    return None


def create_home(store_user: str, data: dict, workspace: str = "personal") -> dict:
    name = (data.get("name") or "").strip()[:_NAME_MAX_LEN]
    if not name:
        raise ValueError("name is required")

    ownership_type = data.get("ownership_type")
    if ownership_type not in ("rent", "own"):
        raise ValueError("ownership_type must be 'rent' or 'own'")

    variant = _validate_variant_fields(
        ownership_type, data.get(ownership_type) or {}, store_user, workspace
    )
    now = datetime.now(timezone.utc).isoformat()
    tag = _generate_tag(name)

    home = {
        "id": str(uuid.uuid4()),
        "name": name,
        "icon": (data.get("icon") or "🏘️")[:8],
        "tag": tag,
        "ownership_type": ownership_type,
        "address": (data.get("address") or "").strip()[:_TEXT_MAX_LEN],
        "notes": (data.get("notes") or "").strip()[:_TEXT_MAX_LEN],
        "rent": variant if ownership_type == "rent" else None,
        "own": variant if ownership_type == "own" else None,
        "archived": False,
        "created_by": data.get("created_by"),
        "created_at": now,
        "updated_at": now,
    }

    def _add(store: dict) -> dict:
        store.setdefault("homes", []).append(home)
        return store

    update_json(homes_path(store_user, workspace), _add, default={"homes": []})

    # Registered immediately (not lazily on first tagged item) so the tag is
    # selectable in every other module's tag picker right away — same call
    # Goals already makes on create.
    tags_service.register_tags(store_user, workspace, [tag])

    return home


def update_home(
    store_user: str, home_id: str, updates: dict, workspace: str = "personal"
) -> dict | None:
    """`tag` is never accepted here even if present in `updates` — it is
    server-generated once at creation and immutable. `ownership_type` MAY
    change (rent<->own), in which case the now-inactive variant is cleared
    to null rather than left stale."""
    found: dict | None = None

    def _update(store: dict) -> dict:
        nonlocal found
        for h in store.get("homes", []):
            if h["id"] != home_id:
                continue
            if "name" in updates:
                name = (updates["name"] or "").strip()[:_NAME_MAX_LEN]
                if not name:
                    raise ValueError("name cannot be empty")
                h["name"] = name
            if "icon" in updates:
                h["icon"] = (updates["icon"] or "🏘️")[:8]
            if "address" in updates:
                h["address"] = (updates["address"] or "").strip()[:_TEXT_MAX_LEN]
            if "notes" in updates:
                h["notes"] = (updates["notes"] or "").strip()[:_TEXT_MAX_LEN]

            ownership_type = updates.get("ownership_type", h["ownership_type"])
            if ownership_type not in ("rent", "own"):
                raise ValueError("ownership_type must be 'rent' or 'own'")
            variant_key = ownership_type
            if variant_key in updates or ownership_type != h["ownership_type"]:
                variant = _validate_variant_fields(
                    ownership_type,
                    updates.get(variant_key) or h.get(variant_key) or {},
                    store_user,
                    workspace,
                )
                h["rent"] = variant if ownership_type == "rent" else None
                h["own"] = variant if ownership_type == "own" else None
            h["ownership_type"] = ownership_type

            h["updated_at"] = datetime.now(timezone.utc).isoformat()
            found = h
            break
        return store

    update_json(homes_path(store_user, workspace), _update, default={"homes": []})
    return found


def convert_to_pool(store_user: str, home_id: str, workspace: str, pool_user: str) -> dict | None:
    """One-way move of a home from `store_user`'s own store into
    `pool_user`'s pool store — same "move the record, don't regenerate
    anything" shape as assets_service.convert_to_pool(), simplified since
    homes are a flat single-file record with no subtree/attachments to
    carry along. `id` AND `tag` are both preserved: the tag is already
    embedded on whatever else has been tagged with it, so regenerating it
    here would orphan every one of those items."""
    home = get_home(store_user, home_id, workspace)
    if home is None:
        return None

    def _remove(store: dict) -> dict:
        store["homes"] = [h for h in store.get("homes", []) if h["id"] != home_id]
        return store

    update_json(homes_path(store_user, workspace), _remove, default={"homes": []})

    def _add(store: dict) -> dict:
        store.setdefault("homes", []).append(home)
        return store

    update_json(homes_path(pool_user, "personal"), _add, default={"homes": []})

    # Already registered in store_user's own vocabulary at creation time —
    # register it into the pool's own vocabulary too, so every other pool
    # member's tag picker offers it immediately (same call create_home()
    # already makes for the original owner).
    tags_service.register_tags(pool_user, "personal", [home["tag"]])

    return home


def delete_home(
    store_user: str, home_id: str, workspace: str = "personal", deleted_by: str = ""
) -> bool:
    home = get_home(store_user, home_id, workspace)
    if home is None:
        return False

    trash_service.soft_delete(
        store_user=store_user,
        workspace=workspace,
        module="homes",
        record_type="home",
        original_id=home_id,
        payload=home,
        deleted_by=deleted_by,
        title=home["name"],
        subtitle="Homes",
    )

    def _remove(store: dict) -> dict:
        store["homes"] = [h for h in store.get("homes", []) if h["id"] != home_id]
        return store

    update_json(homes_path(store_user, workspace), _remove, default={"homes": []})
    return True
