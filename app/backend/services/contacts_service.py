"""Contacts (CRM) core: contacts, interactions, deals, custom fields, pipeline,
and asset-style sharing (read / contribute / edit).

Design mirrors finance_service / assets_service:
- Brain-native JSON storage, per user per workspace; pool pseudo-users _household
  (personal ws) and _team (business ws) hold shared-pool contacts.
- Sharing: shared_with entries {target, access, accepted[]} on personal contacts
  (accept handshake); pool contributors {target, access} (no handshake).
  Specificity: a by-name entry overrides group/role entries. hidden_from beats
  shares. **contribute** = log interactions + create/advance deals only, never
  edit core fields / delete / reshare (enforced in the router).
- Cross-store visibility is routed through contacts_index (disposable cache).
- Money data on a contact card is resolved in the router against the viewer's
  own finance access — this service never reads finance stores.
"""

import uuid
from datetime import date, datetime, timezone

from services.file_service import (
    contact_deals_path,
    contact_fields_path,
    contact_interactions_path,
    contact_pipeline_path,
    contacts_path,
    read_json,
    write_json,
)

POOL_HOUSEHOLD = "_household"
POOL_TEAM = "_team"

CONTACT_TYPES = {"person", "company"}
INTERACTION_TYPES = {"call", "email", "meeting", "text", "note"}
FIELD_TYPES = {"text", "number", "date", "boolean", "select"}
ACCESS_LEVELS = {"read", "contribute", "edit"}
DEFAULT_STAGES = ["Lead", "Contacted", "Proposal", "Negotiation", "Won", "Lost"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_pool(store_user: str) -> bool:
    return store_user in (POOL_HOUSEHOLD, POOL_TEAM)


def pool_for(workspace: str) -> str:
    return POOL_TEAM if workspace == "business" else POOL_HOUSEHOLD


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def list_contacts(store_user: str, workspace: str) -> list[dict]:
    return read_json(contacts_path(store_user, workspace), default={"contacts": []}).get(
        "contacts", []
    )


def _save_contacts(store_user: str, workspace: str, contacts: list[dict]) -> None:
    write_json(contacts_path(store_user, workspace), {"contacts": contacts})


def _list_interactions(store_user: str, workspace: str) -> list[dict]:
    return read_json(
        contact_interactions_path(store_user, workspace), default={"interactions": []}
    ).get("interactions", [])


def _save_interactions(store_user: str, workspace: str, items: list[dict]) -> None:
    write_json(contact_interactions_path(store_user, workspace), {"interactions": items})


def _list_deals(store_user: str, workspace: str) -> list[dict]:
    return read_json(contact_deals_path(store_user, workspace), default={"deals": []}).get(
        "deals", []
    )


def _save_deals(store_user: str, workspace: str, items: list[dict]) -> None:
    write_json(contact_deals_path(store_user, workspace), {"deals": items})


def get_contact(store_user: str, workspace: str, contact_id: str) -> dict | None:
    return next((c for c in list_contacts(store_user, workspace) if c["id"] == contact_id), None)


# ---------------------------------------------------------------------------
# Custom field definitions (instance-level, admin-managed) + pipeline
# ---------------------------------------------------------------------------


def get_custom_fields() -> list[dict]:
    return read_json(contact_fields_path(), default={"fields": []}).get("fields", [])


def set_custom_fields(fields: list) -> list[dict]:
    out = []
    seen = set()
    for f in fields or []:
        if not isinstance(f, dict):
            continue
        key = (f.get("key") or "").strip().lower().replace(" ", "_")[:40]
        label = (f.get("label") or "").strip()[:60]
        ftype = f.get("type") if f.get("type") in FIELD_TYPES else "text"
        if not key or not label or key in seen:
            continue
        seen.add(key)
        entry = {"key": key, "label": label, "type": ftype}
        if ftype == "select":
            opts = [str(o).strip()[:60] for o in (f.get("options") or []) if str(o).strip()]
            entry["options"] = opts
        out.append(entry)
    write_json(contact_fields_path(), {"fields": out})
    return out


def _validate_custom(custom) -> dict:
    """Keep only values for known custom-field keys; light type coercion."""
    if not isinstance(custom, dict):
        return {}
    defs = {f["key"]: f for f in get_custom_fields()}
    out = {}
    for key, val in custom.items():
        f = defs.get(key)
        if not f:
            continue
        if val is None or val == "":
            continue
        if f["type"] == "number":
            try:
                out[key] = float(val)
            except (TypeError, ValueError):
                continue
        elif f["type"] == "boolean":
            out[key] = bool(val)
        elif f["type"] == "select":
            if str(val) in (f.get("options") or []):
                out[key] = str(val)
        else:
            out[key] = str(val)[:2000]
    return out


def get_pipeline(store_user: str, workspace: str) -> list[str]:
    data = read_json(contact_pipeline_path(store_user, workspace), default={})
    stages = data.get("stages")
    if isinstance(stages, list) and stages:
        return stages
    return list(DEFAULT_STAGES)


def set_pipeline(store_user: str, workspace: str, stages: list) -> list[str]:
    clean = []
    for s in stages or []:
        name = str(s).strip()[:40]
        if name and name not in clean:
            clean.append(name)
    if not clean:
        clean = list(DEFAULT_STAGES)
    write_json(contact_pipeline_path(store_user, workspace), {"stages": clean})
    return clean


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _clean_list(values, cap: int = 20, item_cap: int = 200) -> list[str]:
    out = []
    for v in values or []:
        s = str(v).strip()[:item_cap]
        if s and s not in out:
            out.append(s)
        if len(out) >= cap:
            break
    return out


def _validate_contact(data: dict, partial: bool = False) -> dict:
    out: dict = {}
    if "type" in data or not partial:
        t = data.get("type", "person")
        if t not in CONTACT_TYPES:
            raise ValueError("type must be 'person' or 'company'")
        out["type"] = t
    if "name" in data or not partial:
        name = (data.get("name") or "").strip()
        if not name or len(name) > 200:
            raise ValueError("Contact name must be 1-200 characters")
        out["name"] = name
    if "emails" in data:
        out["emails"] = _clean_list(data.get("emails"))
    if "phones" in data:
        out["phones"] = _clean_list(data.get("phones"))
    if "address" in data:
        out["address"] = (data.get("address") or "").strip()[:500]
    if "company_id" in data:
        out["company_id"] = (data.get("company_id") or None) or None
    if "tags" in data:
        out["tags"] = _clean_list(data.get("tags"), cap=30, item_cap=40)
    if "birthday" in data:
        bd = (data.get("birthday") or "").strip()
        if bd:
            try:
                date.fromisoformat(bd)
            except ValueError:
                raise ValueError("birthday must be YYYY-MM-DD")
        out["birthday"] = bd or None
    if "status" in data:
        out["status"] = (data.get("status") or "").strip()[:40]
    if "notes" in data:
        out["notes"] = (data.get("notes") or "").strip()[:5000]
    if "custom" in data:
        out["custom"] = _validate_custom(data.get("custom"))
    return out


# ---------------------------------------------------------------------------
# Sharing resolution (contribute has no field caps — fixed policy)
# ---------------------------------------------------------------------------


def _entry_matches(entry: dict, viewer: str, viewer_role: str, workspace: str) -> bool:
    target = entry.get("target") or ""
    if target == viewer:
        return True
    if target == "team":
        return workspace == "business"
    if target == "household":
        return True
    if target.startswith("role:"):
        return target[5:] == viewer_role
    return False


def _entry_accepted(entry: dict, viewer: str) -> bool:
    accepted = entry.get("accepted")
    if accepted is None:
        return True
    return viewer in accepted


def _rung_access(entries: list[dict]) -> str | None:
    if not entries:
        return None
    if any(e.get("access", "read") == "edit" for e in entries):
        return "edit"
    if any(e.get("access", "read") == "contribute" for e in entries):
        return "contribute"
    return "read"


def resolve_access(
    viewer: str,
    viewer_role: str,
    is_admin: bool,
    store_user: str,
    contact: dict,
    workspace: str = "personal",
) -> str | None:
    """access ∈ {edit, contribute, read, None}. By-name overrides group entries;
    hidden_from beats shares (except owner / pool admin)."""
    hidden = contact.get("hidden_from") or []
    is_hidden = viewer in hidden or f"role:{viewer_role}" in hidden

    if is_pool(store_user):
        if is_admin:
            return "edit"
        if is_hidden:
            return None
        entries = [
            e
            for e in (contact.get("contributors") or [])
            if _entry_matches(e, viewer, viewer_role, workspace)
        ]
        by_name = [e for e in entries if e.get("target") == viewer]
        group = [e for e in entries if e.get("target") != viewer]
        return _rung_access(by_name) or _rung_access(group) or "read"

    if store_user == viewer:
        return "edit"
    if is_hidden:
        return None
    entries = [
        e
        for e in (contact.get("shared_with") or [])
        if _entry_matches(e, viewer, viewer_role, workspace) and _entry_accepted(e, viewer)
    ]
    by_name = [e for e in entries if e.get("target") == viewer]
    group = [e for e in entries if e.get("target") != viewer]
    return _rung_access(by_name) or _rung_access(group)


def annotate(contact: dict, store_user: str, viewer: str, access: str) -> dict:
    out = dict(contact)
    if store_user == POOL_HOUSEHOLD:
        out["_owner"] = "household"
    elif store_user == POOL_TEAM:
        out["_owner"] = "team"
    elif store_user != viewer:
        out["_owner"] = store_user
    out["_access"] = access
    return out


def store_for_annotated(contact: dict, viewer: str) -> str:
    owner = contact.get("_owner")
    if owner == "household":
        return POOL_HOUSEHOLD
    if owner == "team":
        return POOL_TEAM
    return owner or viewer


def list_visible_contacts(
    viewer: str, viewer_role: str, is_admin: bool, workspace: str, include_archived: bool = False
) -> list[dict]:
    from services.contacts_index import sharers_for

    results = []
    stores = [viewer, pool_for(workspace)]
    stores += [s for s in sharers_for(viewer, viewer_role, workspace) if s not in stores]
    for store_user in stores:
        for contact in list_contacts(store_user, workspace):
            if contact.get("archived") and not include_archived:
                continue
            access = resolve_access(viewer, viewer_role, is_admin, store_user, contact, workspace)
            if not access:
                continue
            results.append(annotate(contact, store_user, viewer, access))
    return results


def find_contact(
    viewer: str, viewer_role: str, is_admin: bool, workspace: str, contact_id: str
) -> tuple[str, dict, str] | None:
    """Returns (store_user, contact, access) or None."""
    from services.contacts_index import sharers_for

    stores = [viewer, pool_for(workspace)]
    stores += [s for s in sharers_for(viewer, viewer_role, workspace) if s not in stores]
    for store_user in stores:
        contact = get_contact(store_user, workspace, contact_id)
        if contact:
            access = resolve_access(viewer, viewer_role, is_admin, store_user, contact, workspace)
            return (store_user, contact, access) if access else None
    return None


# ---------------------------------------------------------------------------
# Contact CRUD
# ---------------------------------------------------------------------------


def create_contact(store_user: str, workspace: str, data: dict, created_by: str) -> dict:
    fields = _validate_contact(data)
    contact = {
        "id": str(uuid.uuid4()),
        "type": "person",
        "name": "",
        "emails": [],
        "phones": [],
        "address": "",
        "company_id": None,
        "tags": [],
        "birthday": None,
        "status": "",
        "notes": "",
        "custom": {},
        "shared_with": [],
        "contributors": [],
        "hidden_from": [],
        "archived": False,
        "created_by": created_by,
        "created_at": _now(),
        "updated_at": _now(),
        **fields,
    }
    contacts = list_contacts(store_user, workspace)
    contacts.append(contact)
    _save_contacts(store_user, workspace, contacts)
    return contact


def update_contact(store_user: str, workspace: str, contact_id: str, updates: dict) -> dict | None:
    fields = _validate_contact(updates, partial=True)
    contacts = list_contacts(store_user, workspace)
    for i, c in enumerate(contacts):
        if c["id"] != contact_id:
            continue
        fields["updated_at"] = _now()
        contacts[i] = {**c, **fields}
        _save_contacts(store_user, workspace, contacts)
        return contacts[i]
    return None


def set_archived(store_user: str, workspace: str, contact_id: str, archived: bool) -> dict | None:
    contacts = list_contacts(store_user, workspace)
    for i, c in enumerate(contacts):
        if c["id"] != contact_id:
            continue
        c["archived"] = bool(archived)
        c["updated_at"] = _now()
        contacts[i] = c
        _save_contacts(store_user, workspace, contacts)
        return c
    return None


def delete_contact(store_user: str, workspace: str, contact_id: str) -> bool:
    contacts = list_contacts(store_user, workspace)
    remaining = [c for c in contacts if c["id"] != contact_id]
    if len(remaining) == len(contacts):
        return False
    _save_contacts(store_user, workspace, remaining)
    # Cascade delete this contact's interactions + deals in the same store.
    ints = [
        x for x in _list_interactions(store_user, workspace) if x.get("contact_id") != contact_id
    ]
    _save_interactions(store_user, workspace, ints)
    deals = [d for d in _list_deals(store_user, workspace) if d.get("contact_id") != contact_id]
    _save_deals(store_user, workspace, deals)
    return True


def resolve_target_users(target: str) -> list[str]:
    """Concrete user names for a share target. Raises ValueError on unknowns."""
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


def _clean_share_entries(entries, existing, pool: bool) -> list[dict]:
    old_accepted = {e.get("target"): e.get("accepted") for e in (existing or [])}
    cleaned = []
    seen = set()
    for entry in entries or []:
        target = (entry.get("target") or "").strip()
        if not target or target in seen:
            continue
        seen.add(target)
        resolve_target_users(target)  # validates
        access = entry.get("access", "read")
        if access not in ACCESS_LEVELS:
            raise ValueError(f"Invalid access level: {access!r}")
        out = {"target": target, "access": access}
        if not pool:
            prior = old_accepted.get(target)
            out["accepted"] = prior if isinstance(prior, list) else []
        cleaned.append(out)
    return cleaned


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


def update_access(
    store_user: str,
    workspace: str,
    contact_id: str,
    shared_with=None,
    hidden_from=None,
    contributors=None,
) -> tuple[dict, list[str]]:
    """Replace a contact's audience. Personal contacts use shared_with (handshake);
    pool contacts use contributors (no handshake). Returns (record, users_to_notify)."""
    pool = is_pool(store_user)
    if pool and shared_with is not None:
        raise ValueError("Pool contacts are workspace-visible — use contributors, not shares")
    if not pool and contributors is not None:
        raise ValueError("Contributors are for pool contacts — use shared_with")

    contacts = list_contacts(store_user, workspace)
    for i, c in enumerate(contacts):
        if c["id"] != contact_id:
            continue
        to_notify: list[str] = []
        if shared_with is not None:
            cleaned = _clean_share_entries(shared_with, c.get("shared_with"), pool=False)
            c["shared_with"] = cleaned
            for entry in cleaned:
                accepted = set(entry.get("accepted") or [])
                for name in resolve_target_users(entry["target"]):
                    if name != store_user and name not in accepted:
                        to_notify.append(name)
        if contributors is not None:
            c["contributors"] = _clean_share_entries(contributors, c.get("contributors"), pool=True)
        if hidden_from is not None:
            c["hidden_from"] = _clean_hidden(hidden_from)
        c["updated_at"] = _now()
        contacts[i] = c
        _save_contacts(store_user, workspace, contacts)
        if not pool:
            from services.contacts_index import reindex_owner

            reindex_owner(store_user)
        return (c, sorted(set(to_notify)))
    raise ValueError("Contact not found")


def respond_share(viewer: str, owner: str, workspace: str, contact_id: str, accept: bool) -> bool:
    """Accept adds viewer to accepted[]; decline drops a by-name entry / removes
    the viewer from a group entry's acceptance."""
    contacts = list_contacts(owner, workspace)
    changed = False
    for i, c in enumerate(contacts):
        if c["id"] != contact_id:
            continue
        kept = []
        for entry in c.get("shared_with") or []:
            targets_viewer = False
            try:
                targets_viewer = viewer in resolve_target_users(entry.get("target", ""))
            except ValueError:
                pass
            if not targets_viewer:
                kept.append(entry)
                continue
            if accept:
                accepted = entry.setdefault("accepted", [])
                if viewer not in accepted:
                    accepted.append(viewer)
                    changed = True
                kept.append(entry)
            else:
                if entry.get("target") == viewer:
                    changed = True
                    continue
                accepted = entry.get("accepted")
                if isinstance(accepted, list) and viewer in accepted:
                    entry["accepted"] = [n for n in accepted if n != viewer]
                    changed = True
                kept.append(entry)
        c["shared_with"] = kept
        c["updated_at"] = _now()
        contacts[i] = c
        _save_contacts(owner, workspace, contacts)
        return changed
    return False


# ---------------------------------------------------------------------------
# Interactions
# ---------------------------------------------------------------------------


def list_interactions(store_user: str, workspace: str, contact_id: str) -> list[dict]:
    items = [
        x for x in _list_interactions(store_user, workspace) if x.get("contact_id") == contact_id
    ]
    return sorted(items, key=lambda x: x.get("date", ""), reverse=True)


def add_interaction(
    store_user: str, workspace: str, contact_id: str, data: dict, created_by: str
) -> dict:
    itype = data.get("type", "note")
    if itype not in INTERACTION_TYPES:
        raise ValueError(f"Invalid interaction type: {itype!r}")
    when = (data.get("date") or "").strip() or date.today().isoformat()
    try:
        date.fromisoformat(when)
    except ValueError:
        raise ValueError("date must be YYYY-MM-DD")
    follow_up = (data.get("follow_up") or "").strip() or None
    if follow_up:
        try:
            date.fromisoformat(follow_up)
        except ValueError:
            raise ValueError("follow_up must be YYYY-MM-DD")
    item = {
        "id": str(uuid.uuid4()),
        "contact_id": contact_id,
        "type": itype,
        "summary": (data.get("summary") or "").strip()[:5000],
        "date": when,
        "follow_up": follow_up,
        "follow_up_done": False,
        "created_by": created_by,
        "created_at": _now(),
    }
    items = _list_interactions(store_user, workspace)
    items.append(item)
    _save_interactions(store_user, workspace, items)
    return item


def update_interaction(
    store_user: str, workspace: str, interaction_id: str, updates: dict
) -> dict | None:
    items = _list_interactions(store_user, workspace)
    for i, x in enumerate(items):
        if x["id"] != interaction_id:
            continue
        if "summary" in updates:
            x["summary"] = (updates["summary"] or "").strip()[:5000]
        if "follow_up" in updates:
            fu = (updates["follow_up"] or "").strip() or None
            if fu:
                date.fromisoformat(fu)
            x["follow_up"] = fu
        if "follow_up_done" in updates:
            x["follow_up_done"] = bool(updates["follow_up_done"])
        items[i] = x
        _save_interactions(store_user, workspace, items)
        return x
    return None


def delete_interaction(store_user: str, workspace: str, interaction_id: str) -> bool:
    items = _list_interactions(store_user, workspace)
    remaining = [x for x in items if x["id"] != interaction_id]
    if len(remaining) == len(items):
        return False
    _save_interactions(store_user, workspace, remaining)
    return True


# ---------------------------------------------------------------------------
# Deals
# ---------------------------------------------------------------------------


def is_won(deal: dict) -> bool:
    return (deal.get("stage") or "").strip().lower() == "won"


def list_deals(store_user: str, workspace: str, contact_id: str | None = None) -> list[dict]:
    items = _list_deals(store_user, workspace)
    if contact_id:
        items = [d for d in items if d.get("contact_id") == contact_id]
    return items


def find_deal(
    viewer: str, viewer_role: str, is_admin: bool, workspace: str, deal_id: str
) -> tuple[str, dict, dict, str] | None:
    """Locate a deal across viewer + pool + sharer stores. A deal has no access
    of its own — it inherits the parent contact's resolve_access result.
    Returns (store_user, deal, contact, access) or None."""
    from services.contacts_index import sharers_for

    stores = [viewer, pool_for(workspace)]
    stores += [s for s in sharers_for(viewer, viewer_role, workspace) if s not in stores]
    for store_user in stores:
        deal = next((d for d in _list_deals(store_user, workspace) if d["id"] == deal_id), None)
        if deal is None:
            continue
        contact = get_contact(store_user, workspace, deal.get("contact_id") or "")
        if contact is None:
            return None
        access = resolve_access(viewer, viewer_role, is_admin, store_user, contact, workspace)
        return (store_user, deal, contact, access) if access else None
    return None


def _validate_deal(store_user: str, workspace: str, data: dict, partial: bool = False) -> dict:
    out: dict = {}
    stages = get_pipeline(store_user, workspace)
    if "title" in data or not partial:
        title = (data.get("title") or "").strip()
        if not title or len(title) > 120:
            raise ValueError("Deal title must be 1-120 characters")
        out["title"] = title
    if "value_cents" in data or not partial:
        v = data.get("value_cents", 0)
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError("value_cents must be an integer")
        out["value_cents"] = v
    if "stage" in data or not partial:
        stage = data.get("stage") or (stages[0] if stages else "Lead")
        if stage not in stages:
            raise ValueError(f"Unknown pipeline stage: {stage!r}")
        out["stage"] = stage
    if "expected_close" in data:
        ec = (data.get("expected_close") or "").strip()
        if ec:
            date.fromisoformat(ec)
        out["expected_close"] = ec or None
    if "follow_up" in data:
        fu = (data.get("follow_up") or "").strip()
        if fu:
            date.fromisoformat(fu)
        out["follow_up"] = fu or None
    if "notes" in data:
        out["notes"] = (data.get("notes") or "").strip()[:5000]
    if "invoice_id" in data:
        out["invoice_id"] = (data.get("invoice_id") or None) or None
    return out


def add_deal(store_user: str, workspace: str, contact_id: str, data: dict, created_by: str) -> dict:
    fields = _validate_deal(store_user, workspace, data)
    deal = {
        "id": str(uuid.uuid4()),
        "contact_id": contact_id,
        "expected_close": None,
        "follow_up": None,
        "notes": "",
        "invoice_id": None,
        "linked_asset_ids": [],
        "created_by": created_by,
        "created_at": _now(),
        "updated_at": _now(),
        **fields,
    }
    items = _list_deals(store_user, workspace)
    items.append(deal)
    _save_deals(store_user, workspace, items)
    return deal


def update_deal(store_user: str, workspace: str, deal_id: str, updates: dict) -> dict | None:
    fields = _validate_deal(store_user, workspace, updates, partial=True)
    items = _list_deals(store_user, workspace)
    for i, d in enumerate(items):
        if d["id"] != deal_id:
            continue
        fields["updated_at"] = _now()
        items[i] = {**d, **fields}
        _save_deals(store_user, workspace, items)
        return items[i]
    return None


def delete_deal(store_user: str, workspace: str, deal_id: str) -> bool:
    items = _list_deals(store_user, workspace)
    remaining = [d for d in items if d["id"] != deal_id]
    if len(remaining) == len(items):
        return False
    _save_deals(store_user, workspace, remaining)
    return True


def link_asset(store_user: str, workspace: str, deal_id: str, asset_id: str) -> dict | None:
    """Append an Asset id to a deal's linked_asset_ids (idempotent). The caller
    (router) must have already resolved the asset for the acting user via
    assets_service.find_asset() — this is a pure data mutation."""
    items = _list_deals(store_user, workspace)
    for i, d in enumerate(items):
        if d["id"] != deal_id:
            continue
        ids = list(d.get("linked_asset_ids") or [])
        if asset_id not in ids:
            ids.append(asset_id)
        items[i] = {**d, "linked_asset_ids": ids, "updated_at": _now()}
        _save_deals(store_user, workspace, items)
        return items[i]
    return None


def unlink_asset(store_user: str, workspace: str, deal_id: str, asset_id: str) -> dict | None:
    items = _list_deals(store_user, workspace)
    for i, d in enumerate(items):
        if d["id"] != deal_id:
            continue
        ids = [a for a in (d.get("linked_asset_ids") or []) if a != asset_id]
        items[i] = {**d, "linked_asset_ids": ids, "updated_at": _now()}
        _save_deals(store_user, workspace, items)
        return items[i]
    return None


# ---------------------------------------------------------------------------
# Dedup search (used by agent + automation to avoid duplicate contacts)
# ---------------------------------------------------------------------------


def find_match(store_user: str, workspace: str, name: str = "", email: str = "") -> dict | None:
    name_n = (name or "").strip().lower()
    email_n = (email or "").strip().lower()
    for c in list_contacts(store_user, workspace):
        if email_n and email_n in [e.lower() for e in c.get("emails", [])]:
            return c
        if name_n and c.get("name", "").strip().lower() == name_n:
            return c
    return None


def search_contacts(store_user: str, workspace: str, query: str, limit: int = 20) -> list[dict]:
    q = (query or "").strip().lower()
    if not q:
        return list_contacts(store_user, workspace)[:limit]
    out = []
    for c in list_contacts(store_user, workspace):
        hay = " ".join(
            [c.get("name", ""), " ".join(c.get("emails", [])), " ".join(c.get("tags", []))]
        ).lower()
        if q in hay:
            out.append(c)
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------
# Follow-ups (for reminders)
# ---------------------------------------------------------------------------


def due_followups(store_user: str, workspace: str, on_or_before: str) -> list[dict]:
    """Interactions + deals whose follow_up date is due (<= on_or_before) and not done."""
    out = []
    for x in _list_interactions(store_user, workspace):
        fu = x.get("follow_up")
        if fu and not x.get("follow_up_done") and fu <= on_or_before:
            out.append({"kind": "interaction", "item": x})
    for d in _list_deals(store_user, workspace):
        fu = d.get("follow_up")
        if fu and fu <= on_or_before and not is_won(d) and (d.get("stage") or "").lower() != "lost":
            out.append({"kind": "deal", "item": d})
    return out


def run_followup_reminders() -> None:
    """Nightly: notify each owner of due contact follow-ups (interactions + deals).
    Deduped per item per due date via `followup_notified_for`. Never raises."""
    from datetime import date

    from services import auth_service

    today = date.today().isoformat()
    stores: list[tuple[str, str]] = [(POOL_HOUSEHOLD, "personal"), (POOL_TEAM, "business")]
    for user in auth_service.list_users():
        for ws in user.get("workspaces", ["personal"]):
            stores.append((user["name"], ws))

    for store_user, ws in stores:
        try:
            due = due_followups(store_user, ws, today)
            if not due:
                continue
            recipients = _followup_recipients(store_user)
            _mark_and_notify(store_user, ws, due, recipients, today)
        except Exception:  # pragma: no cover - defensive
            import logging

            logging.getLogger("logcore.contacts").exception("contacts follow-up sweep failed")


def _followup_recipients(store_user: str) -> list[str]:
    from services import auth_service

    if is_pool(store_user):
        return [u["name"] for u in auth_service.list_users() if u.get("role") == "admin"]
    return [store_user]


def _mark_and_notify(store_user, ws, due, recipients, today) -> None:
    from services.suggestions_service import notify_user

    contacts = {c["id"]: c for c in list_contacts(store_user, ws)}
    ints = _list_interactions(store_user, ws)
    deals = _list_deals(store_user, ws)
    changed_i = changed_d = False
    for entry in due:
        item = entry["item"]
        if item.get("followup_notified_for") == item.get("follow_up"):
            continue
        contact = contacts.get(item.get("contact_id"))
        cname = contact.get("name", "a contact") if contact else "a contact"
        for name in recipients:
            notify_user(
                name,
                "👥 Contact follow-up due",
                f"Follow up with {cname} (due {item.get('follow_up')}).",
                source="contacts",
                action={
                    "type": "open_contact",
                    "workspace": ws,
                    "contact_id": item.get("contact_id"),
                },
                url="/contacts",
            )
        item["followup_notified_for"] = item.get("follow_up")
        if entry["kind"] == "interaction":
            changed_i = True
        else:
            changed_d = True
    if changed_i:
        _save_interactions(store_user, ws, ints)
    if changed_d:
        _save_deals(store_user, ws, deals)
