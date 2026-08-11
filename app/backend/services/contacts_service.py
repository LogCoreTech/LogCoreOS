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

import re
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

# Self-contact profile fields (merged from the retired Profile module). "Basic"
# fields share like any other contact field; "private" fields never leave the
# record's own store_user's view regardless of sharing config, enforced in
# _strip_private() below — this is a general Contacts-module rule, not a
# self-contact-specific check, so it costs nothing on ordinary contacts.
_BASIC_SHORT_FIELDS = {
    "pronouns",
    "city",
    "state",
    "country",
    "occupation",
    "gender",
    "marital_status",
    "pets",
}
_BASIC_LONG_FIELDS = {"life_mission", "core_values", "key_constraints"}
_PRIVATE_SHORT_FIELDS = {
    "wake_weekday",
    "wake_weekend",
    "bedtime",
    "work_start",
    "work_end",
    "height_cm",
    "height_unit",
    "weight_kg",
    "weight_unit",
    "blood_type",
    "income_range",
    "budget_style",
    "communication_style",
    "tone",
    "response_language",
}
_PRIVATE_LONG_FIELDS = {
    "conditions",
    "medications",
    "diet",
    "exercise",
    "topics_to_emphasize",
    "topics_to_avoid",
}
_PRIVATE_FIELDS = _PRIVATE_SHORT_FIELDS | _PRIVATE_LONG_FIELDS
_PROFILE_WORKSPACES = ("personal", "business")

# Short fields validated as plain trimmed/capped strings via the generic loop
# in _validate_contact — every _BASIC_SHORT_FIELDS/_PRIVATE_SHORT_FIELDS entry
# EXCEPT the ones with their own dedicated enum/numeric/time validation below.
# Listed explicitly (not "all minus a subtraction") so adding a new
# specially-validated field can't silently fall through to plain-string
# handling — that exact bug (height_cm treated as a string) happened once.
_PLAIN_STRING_SHORT_FIELDS = (_BASIC_SHORT_FIELDS | _PRIVATE_SHORT_FIELDS) - {
    "gender",
    "height_unit",
    "weight_unit",
    "blood_type",
    "height_cm",
    "weight_kg",
    "wake_weekday",
    "wake_weekend",
    "bedtime",
    "work_start",
    "work_end",
}

GENDERS = {"male", "female"}
HEIGHT_UNITS = {"ftin", "cm"}
WEIGHT_UNITS = {"lbs", "kg"}
BLOOD_TYPES = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-", "Unknown"}
EDUCATION_LEVELS = [
    "Junior High",
    "High School",
    "Some College",
    "Trade/Vocational School",
    "Associate's Degree",
    "Bachelor's Degree",
    "Master's Degree",
    "Doctorate",
    "Other",
]
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Career history: a resume-style list of entries on the self-contact (or any
# contact). Exactly the fields inside each entry are "career" fields — they
# are NOT top-level Contact fields anymore (employer/industry/education/
# years_experience/skills all moved here from the flat schema).
_CAREER_FIELDS = {"title", "industry", "education", "years_experience", "skills"}


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
# Self-contact — the user's own Contact record IS their profile. Physically
# always stored in the user's PERSONAL store (one record shared across both
# workspaces), never a pool store.
# ---------------------------------------------------------------------------


def get_self_contact(user_name: str, create_if_missing: bool = False) -> dict | None:
    if is_pool(user_name):
        return None
    for c in list_contacts(user_name, "personal"):
        if c.get("self_of") == user_name:
            return c
    return create_self_contact(user_name) if create_if_missing else None


def create_self_contact(
    user_name: str, *, display_name: str | None = None, occupation: str | None = None
) -> dict:
    """Idempotent — returns the existing self-contact if one is already there."""
    existing = get_self_contact(user_name)
    if existing:
        return existing
    contact = create_contact(
        user_name,
        "personal",
        {"type": "person", "name": display_name or user_name},
        created_by=user_name,
    )
    contacts = list_contacts(user_name, "personal")
    for i, c in enumerate(contacts):
        if c["id"] != contact["id"]:
            continue
        c["self_of"] = user_name
        contacts[i] = c
        _save_contacts(user_name, "personal", contacts)
        contact = c
        break
    if occupation:
        contact = (
            update_contact(user_name, "personal", contact["id"], {"occupation": occupation})
            or contact
        )
    return contact


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


def _validate_emails(values) -> list[str]:
    out = []
    for v in values or []:
        s = str(v).strip()[:200]
        if not s:
            continue
        if not _EMAIL_RE.match(s):
            raise ValueError(f"{s!r} is not a valid email address")
        if s not in out:
            out.append(s)
        if len(out) >= 20:
            break
    return out


def _validate_phones(values) -> list[dict]:
    """Each entry is {country_code, number, extension} — digits only, capped
    to plausible lengths. A plain string is accepted for backward
    compatibility (legacy data, CSV import, automation) and wrapped."""
    out = []
    for v in values or []:
        if isinstance(v, str):
            v = {"number": v}
        if not isinstance(v, dict):
            continue
        digits = re.sub(r"\D", "", str(v.get("number") or ""))[:10]
        if not digits:
            continue
        country = re.sub(r"\D", "", str(v.get("country_code") or "1"))[:3] or "1"
        ext = re.sub(r"\D", "", str(v.get("extension") or ""))[:6]
        entry = {"country_code": country, "number": digits, "extension": ext}
        if entry not in out:
            out.append(entry)
        if len(out) >= 20:
            break
    return out


def _validate_career_history(values) -> list[dict]:
    """Resume-style list: one entry per role. `archived` (end_date set) marks
    a past role; at most the caller's UI keeps one non-archived "current"
    entry, but this validator doesn't enforce that — it's a display/workflow
    convention, not a data invariant worth hard-blocking on."""
    out = []
    for v in values or []:
        if not isinstance(v, dict):
            continue
        entry = {
            "id": str(v.get("id") or uuid.uuid4()),
            "title": (v.get("title") or "").strip()[:200],
            "company_id": (v.get("company_id") or None) or None,
            "industry": (v.get("industry") or "").strip()[:200],
            "education": (v.get("education") or "").strip()[:60],
            "years_experience": (v.get("years_experience") or "").strip()[:20],
            "skills": (v.get("skills") or "").strip()[:2000],
            "start_date": (v.get("start_date") or "").strip()[:7] or None,
            "end_date": (v.get("end_date") or "").strip()[:7] or None,
            "archived": bool(v.get("archived")),
        }
        if entry["education"] and entry["education"] not in EDUCATION_LEVELS:
            raise ValueError(f"Unknown education level: {entry['education']!r}")
        out.append(entry)
        if len(out) >= 40:
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
        out["emails"] = _validate_emails(data.get("emails"))
    if "phones" in data:
        out["phones"] = _validate_phones(data.get("phones"))
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
    if "gender" in data:
        g = (data.get("gender") or "").strip().lower()
        if g and g not in GENDERS:
            raise ValueError("gender must be 'male' or 'female'")
        out["gender"] = g
    if "height_unit" in data:
        hu = (data.get("height_unit") or "").strip()
        if hu and hu not in HEIGHT_UNITS:
            raise ValueError("height_unit must be 'ftin' or 'cm'")
        out["height_unit"] = hu
    if "weight_unit" in data:
        wu = (data.get("weight_unit") or "").strip()
        if wu and wu not in WEIGHT_UNITS:
            raise ValueError("weight_unit must be 'lbs' or 'kg'")
        out["weight_unit"] = wu
    if "blood_type" in data:
        bt = (data.get("blood_type") or "").strip()
        if bt and bt not in BLOOD_TYPES:
            raise ValueError(f"Unknown blood type: {bt!r}")
        out["blood_type"] = bt
    if "height_cm" in data:
        hc = data.get("height_cm")
        out["height_cm"] = _validate_number(hc, "height_cm", 0, 300)
    if "weight_kg" in data:
        wk = data.get("weight_kg")
        out["weight_kg"] = _validate_number(wk, "weight_kg", 0, 500)
    if "career_history" in data:
        out["career_history"] = _validate_career_history(data.get("career_history"))
    for key in ("wake_weekday", "wake_weekend", "bedtime", "work_start", "work_end"):
        if key in data:
            val = (data.get(key) or "").strip()[:5]
            if val:
                try:
                    datetime.strptime(val, "%H:%M")
                except ValueError:
                    raise ValueError(f"{key} must be HH:MM")
            out[key] = val
    for key in _PLAIN_STRING_SHORT_FIELDS:
        if key in data:
            out[key] = (data.get(key) or "").strip()[:200]
    for key in _BASIC_LONG_FIELDS | _PRIVATE_LONG_FIELDS:
        if key in data:
            out[key] = (data.get(key) or "").strip()[:2000]
    if data.get("priority_order") is not None:
        out["priority_order"] = _validate_priority_order(data.get("priority_order"))
    return out


def _validate_number(value, field: str, lo: float, hi: float):
    if value in (None, ""):
        return ""
    try:
        num = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a number")
    if not (lo <= num <= hi):
        raise ValueError(f"{field} must be between {lo} and {hi}")
    return num


def _validate_priority_order(value) -> dict:
    if not isinstance(value, dict):
        raise ValueError("priority_order must be an object with personal/business keys")
    cleaned: dict = {}
    for ws in _PROFILE_WORKSPACES:
        if ws not in value:
            continue
        items = value[ws]
        if not isinstance(items, list):
            raise ValueError(f"priority_order.{ws} must be a list")
        cleaned[ws] = [str(x).strip()[:50] for x in items if str(x).strip()][:20]
    return cleaned


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


def _strip_private(contact: dict, store_user: str, viewer: str) -> dict:
    """Health/finance/AI-preference fields never leave the record's own
    store_user's view, regardless of sharing config — a general Contacts rule
    (not self-contact-specific) that happens to be what keeps a shared
    self-contact's sensitive fields locked to its owner."""
    if store_user == viewer:
        return contact
    return {k: v for k, v in contact.items() if k not in _PRIVATE_FIELDS}


def annotate(contact: dict, store_user: str, viewer: str, access: str) -> dict:
    out = dict(_strip_private(contact, store_user, viewer))
    if store_user == POOL_HOUSEHOLD:
        out["_owner"] = "household"
    elif store_user == POOL_TEAM:
        out["_owner"] = "team"
    elif store_user != viewer:
        out["_owner"] = store_user
    out["_access"] = access
    if contact.get("self_of") == viewer:
        out["_pinned"] = True
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
    seen_ids: set[str] = set()

    # The viewer's own self-contact is pinned to the top of THEIR OWN list,
    # regardless of active workspace — it's one record shared across both
    # workspaces, physically stored in the personal store (item 8/9 of the
    # design). Other users' self-contacts are not made cross-workspace-visible
    # here; they're still resolved the normal way below via sharing.
    self_contact = get_self_contact(viewer, create_if_missing=True)
    if self_contact:
        results.append(annotate(self_contact, viewer, viewer, "edit"))
        seen_ids.add(self_contact["id"])

    stores = [viewer, pool_for(workspace)]
    stores += [s for s in sharers_for(viewer, viewer_role, workspace) if s not in stores]
    for store_user in stores:
        for contact in list_contacts(store_user, workspace):
            if contact["id"] in seen_ids:
                continue
            if contact.get("archived") and not include_archived:
                continue
            access = resolve_access(viewer, viewer_role, is_admin, store_user, contact, workspace)
            if not access:
                continue
            results.append(annotate(contact, store_user, viewer, access))
            seen_ids.add(contact["id"])
    return results


def find_contact(
    viewer: str, viewer_role: str, is_admin: bool, workspace: str, contact_id: str
) -> tuple[str, dict, str] | None:
    """Returns (store_user, contact, access) or None. The viewer's own
    self-contact short-circuits here so it resolves regardless of the active
    `workspace` — see list_visible_contacts for why."""
    from services.contacts_index import sharers_for

    self_contact = get_self_contact(viewer)
    if self_contact and self_contact["id"] == contact_id:
        return (viewer, self_contact, "edit")

    stores = [viewer, pool_for(workspace)]
    stores += [s for s in sharers_for(viewer, viewer_role, workspace) if s not in stores]
    for store_user in stores:
        contact = get_contact(store_user, workspace, contact_id)
        if contact:
            access = resolve_access(viewer, viewer_role, is_admin, store_user, contact, workspace)
            if not access:
                return None
            # Defense-in-depth: strip here too (not just in annotate()) so a
            # caller that reads this tuple's raw contact directly — e.g. the
            # agent's get_contact tool — can never leak private fields.
            return (store_user, _strip_private(contact, store_user, viewer), access)
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
        "affiliated_contact_ids": [],
        "career_history": [],
        "photo_ext": None,
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


def update_contact(
    store_user: str, workspace: str, contact_id: str, updates: dict, *, viewer: str | None = None
) -> dict | None:
    """`viewer` is optional and only matters when it differs from `store_user`
    (an edit-level sharee patching someone else's contact) — private fields
    are stripped from the incoming update in that case, so a third party can
    never inject data into fields only the owner will ever be able to read
    back. Callers that always act as their own store_user (self/`/contacts/me`,
    automation, setup, migrations) can omit it."""
    if viewer is not None and viewer != store_user:
        updates = {k: v for k, v in updates.items() if k not in _PRIVATE_FIELDS}
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
        if c.get("self_of"):
            raise ValueError("A user's own contact can't be archived")
        c["archived"] = bool(archived)
        c["updated_at"] = _now()
        contacts[i] = c
        _save_contacts(store_user, workspace, contacts)
        return c
    return None


def set_contact_photo(store_user: str, workspace: str, contact_id: str, ext: str) -> dict | None:
    """Record the uploaded photo's extension on the contact. The router owns
    writing/deleting the actual file — this just keeps the pointer in sync,
    clearing out an old file of a different extension if one exists."""
    from services.file_service import contact_photo_path

    contacts = list_contacts(store_user, workspace)
    for i, c in enumerate(contacts):
        if c["id"] != contact_id:
            continue
        old_ext = c.get("photo_ext")
        if old_ext and old_ext != ext:
            contact_photo_path(store_user, workspace, contact_id, old_ext).unlink(missing_ok=True)
        c["photo_ext"] = ext
        c["updated_at"] = _now()
        contacts[i] = c
        _save_contacts(store_user, workspace, contacts)
        return c
    return None


def clear_contact_photo(store_user: str, workspace: str, contact_id: str) -> dict | None:
    from services.file_service import contact_photo_path

    contacts = list_contacts(store_user, workspace)
    for i, c in enumerate(contacts):
        if c["id"] != contact_id:
            continue
        ext = c.get("photo_ext")
        if ext:
            contact_photo_path(store_user, workspace, contact_id, ext).unlink(missing_ok=True)
        c["photo_ext"] = None
        c["updated_at"] = _now()
        contacts[i] = c
        _save_contacts(store_user, workspace, contacts)
        return c
    return None


def delete_contact(store_user: str, workspace: str, contact_id: str) -> bool:
    contacts = list_contacts(store_user, workspace)
    target = next((c for c in contacts if c["id"] == contact_id), None)
    if target is None:
        return False
    if target.get("self_of"):
        raise ValueError(
            "A user's own contact can't be deleted directly — delete the account instead"
        )
    if target.get("photo_ext"):
        from services.file_service import contact_photo_path

        contact_photo_path(store_user, workspace, contact_id, target["photo_ext"]).unlink(
            missing_ok=True
        )
    remaining = [c for c in contacts if c["id"] != contact_id]
    _save_contacts(store_user, workspace, remaining)
    # Cascade delete this contact's interactions + deals in the same store.
    ints = [
        x for x in _list_interactions(store_user, workspace) if x.get("contact_id") != contact_id
    ]
    _save_interactions(store_user, workspace, ints)
    deals = [d for d in _list_deals(store_user, workspace) if d.get("contact_id") != contact_id]
    _save_deals(store_user, workspace, deals)
    # Strip any dangling affiliation back-references within the SAME store
    # (v1 scope — affiliation linking requires edit on both ends, so both
    # sides always live in a store this function can see; cross-store
    # staleness is accepted, matching the app's existing tolerance elsewhere).
    changed = False
    for c in remaining:
        ids = c.get("affiliated_contact_ids") or []
        if contact_id in ids:
            c["affiliated_contact_ids"] = [i for i in ids if i != contact_id]
            changed = True
    if changed:
        _save_contacts(store_user, workspace, remaining)
    return True


def transfer_ownership(
    store_user: str, workspace: str, contact_id: str, *, new_owner: str, by: str = ""
) -> dict:
    """Move a contact (+ its interactions/deals, which live in separate flat
    per-store files) to another store — a named user's store in the SAME
    workspace, or that workspace's pool.

    Unlike a pool-conversion-style move, share fields are preserved: for a
    named-user destination shared_with/contributors/hidden_from carry over
    unchanged. For a pool destination, each shared_with entry is converted to
    an equivalent contributors entry — pool contacts never read shared_with.
    """
    contacts = list_contacts(store_user, workspace)
    contact = next((c for c in contacts if c["id"] == contact_id), None)
    if contact is None:
        raise ValueError("Contact not found")
    if contact.get("self_of"):
        raise ValueError("A user's own contact can't be transferred")
    _save_contacts(store_user, workspace, [c for c in contacts if c["id"] != contact_id])

    dest_is_pool = is_pool(new_owner)
    if dest_is_pool:
        converted = list(contact.get("contributors") or [])
        for share in contact.get("shared_with") or []:
            converted.append({"target": share["target"], "access": share.get("access", "read")})
        contact["contributors"] = converted
        contact["shared_with"] = []

    dest_contacts = list_contacts(new_owner, workspace)
    dest_contacts.append(contact)
    _save_contacts(new_owner, workspace, dest_contacts)

    src_ints = _list_interactions(store_user, workspace)
    moving_ints = [x for x in src_ints if x.get("contact_id") == contact_id]
    if moving_ints:
        _save_interactions(
            store_user, workspace, [x for x in src_ints if x.get("contact_id") != contact_id]
        )
        dest_ints = _list_interactions(new_owner, workspace)
        _save_interactions(new_owner, workspace, dest_ints + moving_ints)

    src_deals = _list_deals(store_user, workspace)
    moving_deals = [d for d in src_deals if d.get("contact_id") == contact_id]
    if moving_deals:
        _save_deals(
            store_user, workspace, [d for d in src_deals if d.get("contact_id") != contact_id]
        )
        dest_deals = _list_deals(new_owner, workspace)
        _save_deals(new_owner, workspace, dest_deals + moving_deals)

    from services.contacts_index import reindex_owner

    reindex_owner(store_user)
    if not dest_is_pool:
        reindex_owner(new_owner)

    return contact


# ---------------------------------------------------------------------------
# Affiliations — general bidirectional Contact<->Contact links (family,
# company<->person, etc.). A flat symmetric id list, maintained on both ends
# via this dedicated mutation — mirrors the Deal<->Asset linked_asset_ids
# pointer + dedicated-mutation precedent. Never part of the general
# ContactUpdate PATCH. v1 scope: both contacts must resolve to `edit` for the
# acting viewer — cross-owner linking is out of scope (raises ValueError).
# ---------------------------------------------------------------------------


def link_affiliation(
    viewer: str, viewer_role: str, is_admin: bool, workspace: str, contact_id: str, other_id: str
) -> tuple[dict, dict]:
    if contact_id == other_id:
        raise ValueError("A contact can't be affiliated with itself")
    a = find_contact(viewer, viewer_role, is_admin, workspace, contact_id)
    b = find_contact(viewer, viewer_role, is_admin, workspace, other_id)
    if a is None or b is None:
        raise ValueError("Contact not found")
    store_a, contact_a, access_a = a
    store_b, contact_b, access_b = b
    if access_a != "edit" or access_b != "edit":
        raise ValueError("You need edit access to both contacts to link them")
    ws_a = "personal" if contact_a.get("self_of") else workspace
    ws_b = "personal" if contact_b.get("self_of") else workspace
    ids_a = list(contact_a.get("affiliated_contact_ids") or [])
    if other_id not in ids_a:
        ids_a.append(other_id)
    ids_b = list(contact_b.get("affiliated_contact_ids") or [])
    if contact_id not in ids_b:
        ids_b.append(contact_id)
    updated_a = _set_affiliations(store_a, ws_a, contact_id, ids_a)
    updated_b = _set_affiliations(store_b, ws_b, other_id, ids_b)
    return updated_a, updated_b


def unlink_affiliation(
    viewer: str, viewer_role: str, is_admin: bool, workspace: str, contact_id: str, other_id: str
) -> tuple[dict, dict]:
    a = find_contact(viewer, viewer_role, is_admin, workspace, contact_id)
    b = find_contact(viewer, viewer_role, is_admin, workspace, other_id)
    if a is None or b is None:
        raise ValueError("Contact not found")
    store_a, contact_a, access_a = a
    store_b, contact_b, access_b = b
    if access_a != "edit" or access_b != "edit":
        raise ValueError("You need edit access to both contacts to unlink them")
    ws_a = "personal" if contact_a.get("self_of") else workspace
    ws_b = "personal" if contact_b.get("self_of") else workspace
    ids_a = [i for i in (contact_a.get("affiliated_contact_ids") or []) if i != other_id]
    ids_b = [i for i in (contact_b.get("affiliated_contact_ids") or []) if i != contact_id]
    updated_a = _set_affiliations(store_a, ws_a, contact_id, ids_a)
    updated_b = _set_affiliations(store_b, ws_b, other_id, ids_b)
    return updated_a, updated_b


def _set_affiliations(store_user: str, workspace: str, contact_id: str, ids: list[str]) -> dict:
    contacts = list_contacts(store_user, workspace)
    for i, c in enumerate(contacts):
        if c["id"] != contact_id:
            continue
        c["affiliated_contact_ids"] = ids
        c["updated_at"] = _now()
        contacts[i] = c
        _save_contacts(store_user, workspace, contacts)
        return c
    raise ValueError("Contact not found")


def strip_user_references(user_name: str) -> None:
    """Remove `user_name` from shared_with/contributors/hidden_from/accepted[]
    across every OTHER store (real users + pools)."""
    from services import auth_service

    stores = [(u["name"], ws) for u in auth_service.list_users() for ws in ("personal", "business")]
    stores += [(POOL_HOUSEHOLD, "personal"), (POOL_TEAM, "business")]
    for store_user, workspace in stores:
        if store_user == user_name:
            continue
        contacts = list_contacts(store_user, workspace)
        changed = False
        for c in contacts:
            kept = []
            for s in c.get("shared_with") or []:
                if s.get("target") == user_name:
                    changed = True
                    continue
                accepted = s.get("accepted")
                if isinstance(accepted, list) and user_name in accepted:
                    s = {**s, "accepted": [n for n in accepted if n != user_name]}
                    changed = True
                kept.append(s)
            c["shared_with"] = kept

            contrib = c.get("contributors") or []
            new_contrib = [x for x in contrib if x.get("target") != user_name]
            if len(new_contrib) != len(contrib):
                c["contributors"] = new_contrib
                changed = True

            hidden = c.get("hidden_from") or []
            if user_name in hidden:
                c["hidden_from"] = [h for h in hidden if h != user_name]
                changed = True
        if changed:
            _save_contacts(store_user, workspace, contacts)


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
            if c.get("self_of") and any(e.get("access") == "edit" for e in cleaned):
                raise ValueError(
                    "A self-contact can only be shared at read or contribute access — "
                    "nobody but its owner can ever edit it"
                )
            c["shared_with"] = cleaned
            for entry in cleaned:
                accepted = set(entry.get("accepted") or [])
                for name in resolve_target_users(entry["target"]):
                    if name != store_user and name not in accepted:
                        to_notify.append(name)
        if contributors is not None:
            c["contributors"] = _clean_share_entries(contributors, c.get("contributors"), pool=True)
        if hidden_from is not None:
            cleaned_hidden = _clean_hidden(hidden_from)
            if c.get("self_of") and c["self_of"] in cleaned_hidden:
                raise ValueError("A self-contact can never be hidden from its own owner")
            c["hidden_from"] = cleaned_hidden
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
    Returns (store_user, deal, contact, access) or None. Deals on the viewer's
    own self-contact are anchored to the personal store regardless of the
    active workspace, so they're checked first here the same way
    find_contact() short-circuits the self-contact itself."""
    from services.contacts_index import sharers_for

    self_contact = get_self_contact(viewer)
    if self_contact:
        self_deal = next(
            (
                d
                for d in _list_deals(viewer, "personal")
                if d["id"] == deal_id and d.get("contact_id") == self_contact["id"]
            ),
            None,
        )
        if self_deal:
            return (viewer, self_deal, self_contact, "edit")

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


def format_height(height_cm, unit: str) -> str:
    if not height_cm:
        return ""
    cm = float(height_cm)
    if unit == "cm":
        return f"{cm:.0f} cm"
    total_in = cm / 2.54
    ft, inch = divmod(round(total_in), 12)
    return f"{ft}'{inch}\""


def format_weight(weight_kg, unit: str) -> str:
    if not weight_kg:
        return ""
    kg = float(weight_kg)
    if unit == "kg":
        return f"{kg:.1f} kg"
    return f"{kg * 2.20462:.1f} lbs"


def format_profile_text(contact: dict) -> str:
    """Render a self-contact as readable text for the AI chat system prompt —
    the successor to the old Profile.md, but generated on the fly from the
    live self-contact record instead of a stored file."""
    lines = [f"# {contact.get('name', 'User')} — Profile", ""]

    basics = []
    if contact.get("occupation"):
        basics.append(f"**Occupation:** {contact['occupation']}")
    loc = ", ".join(
        x for x in [contact.get("city"), contact.get("state"), contact.get("country")] if x
    )
    if loc:
        basics.append(f"**Location:** {loc}")
    if contact.get("pronouns"):
        basics.append(f"**Pronouns:** {contact['pronouns']}")
    if contact.get("gender"):
        basics.append(f"**Gender:** {contact['gender']}")
    lines.extend(basics)
    if basics:
        lines.append("")

    routine = [
        (lbl, contact[k])
        for k, lbl in [
            ("wake_weekday", "Wake (weekdays)"),
            ("wake_weekend", "Wake (weekends)"),
            ("bedtime", "Bedtime"),
        ]
        if contact.get(k)
    ]
    if contact.get("work_start") or contact.get("work_end"):
        routine.append(
            ("Work hours", f"{contact.get('work_start', '')}–{contact.get('work_end', '')}")
        )
    if routine:
        lines.append("## Daily Routine")
        lines.extend(f"- {lbl}: {v}" for lbl, v in routine)
        lines.append("")

    health = []
    height_str = format_height(contact.get("height_cm"), contact.get("height_unit") or "ftin")
    weight_str = format_weight(contact.get("weight_kg"), contact.get("weight_unit") or "lbs")
    hw = " · ".join(x for x in [height_str, weight_str] if x)
    if hw:
        health.append(("Height/Weight", hw))
    for k, lbl in [
        ("blood_type", "Blood type"),
        ("diet", "Dietary restrictions"),
        ("exercise", "Exercise"),
        ("conditions", "Conditions"),
        ("medications", "Medications"),
    ]:
        if contact.get(k):
            health.append((lbl, contact[k]))
    if health:
        lines.append("## Health")
        lines.extend(f"- {lbl}: {v}" for lbl, v in health)
        lines.append("")

    careers = [c for c in (contact.get("career_history") or []) if not c.get("archived")]
    past_careers = [c for c in (contact.get("career_history") or []) if c.get("archived")]
    if careers or past_careers:
        lines.append("## Work & Career")
        for c in careers:
            when = f" ({c['start_date']}–present)" if c.get("start_date") else ""
            lines.append(f"- **Current:** {c.get('title', '')}{when}")
            for k, lbl in [
                ("industry", "Industry"),
                ("education", "Education"),
                ("skills", "Skills"),
            ]:
                if c.get(k):
                    lines.append(f"  - {lbl}: {c[k]}")
        for c in past_careers:
            when = f" ({c.get('start_date', '?')}–{c.get('end_date', '?')})"
            lines.append(f"- Previously: {c.get('title', '')}{when}")
        lines.append("")

    family_lines = []
    if contact.get("marital_status"):
        family_lines.append(f"- Marital status: {contact['marital_status']}")
    if contact.get("affiliated_contact_ids"):
        family_lines.append(
            f"- Affiliated contacts: {len(contact['affiliated_contact_ids'])} linked"
        )
    if contact.get("pets"):
        family_lines.append(f"- Pets: {contact['pets']}")
    if family_lines:
        lines.append("## Family")
        lines.extend(family_lines)
        lines.append("")

    finances = [
        (lbl, contact[k])
        for k, lbl in [("income_range", "Income range"), ("budget_style", "Budget style")]
        if contact.get(k)
    ]
    if finances:
        lines.append("## Finances")
        lines.extend(f"- {lbl}: {v}" for lbl, v in finances)
        lines.append("")

    gv = [
        (lbl, contact[k])
        for k, lbl in [
            ("life_mission", "Life mission"),
            ("core_values", "Core values"),
            ("key_constraints", "Key constraints"),
        ]
        if contact.get(k)
    ]
    if gv:
        lines.append("## Values & Principles")
        lines.extend(f"- {lbl}: {v}" for lbl, v in gv)
        lines.append("")

    ai = [
        (lbl, contact[k])
        for k, lbl in [
            ("communication_style", "Communication style"),
            ("tone", "Tone"),
            ("response_language", "Response language"),
            ("topics_to_emphasize", "Emphasize"),
            ("topics_to_avoid", "Avoid"),
        ]
        if contact.get(k)
    ]
    if ai:
        lines.append("## AI Preferences")
        lines.extend(f"- {lbl}: {v}" for lbl, v in ai)
        lines.append("")

    if contact.get("notes"):
        lines.append("## Personal Notes")
        lines.append(contact["notes"])
        lines.append("")

    return "\n".join(lines)


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
