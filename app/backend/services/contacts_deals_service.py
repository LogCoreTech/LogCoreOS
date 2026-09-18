"""Contacts (CRM) deals + interactions: pipeline/stages, interaction logging,
deal CRUD, and deal<->asset linking.

Split out of services/contacts_service.py (2026-09-16, cleanup — that file had
grown to ~2100 lines) verbatim, function bodies unchanged. Storage mirrors the
parent module: brain-native JSON, per user per workspace, one flat file per
record type (interactions.json / deals.json / pipeline.json) — see that
file's own module docstring for the full contacts storage model (pools,
sharing, cross-workspace visibility).

A deal/interaction has no access of its own — it always inherits the parent
contact's resolve_access() result, so find_deal() below reaches back into
contacts_service for contact resolution. That reference is done via a
function-local import (not a top-of-file one) specifically so this module
never creates a circular import with contacts_service, which in turn
re-exports every public name below for backward compatibility — see its
module docstring / bottom-of-file import for why.
"""

import uuid
from datetime import date

from services.file_service import (
    contact_deals_path,
    contact_interactions_path,
    contact_pipeline_path,
    read_json,
    write_json,
)

INTERACTION_TYPES = {"call", "email", "meeting", "text", "note"}
DEFAULT_STAGES = ["Lead", "Contacted", "Proposal", "Negotiation", "Won", "Lost"]


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


# ---------------------------------------------------------------------------
# Pipeline (custom per-user/workspace deal stages)
# ---------------------------------------------------------------------------


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
    from services.contacts_service import _now

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
    """Locate a deal across every candidate store (mirrors find_contact()). A
    deal has no access of its own — it inherits the parent contact's
    resolve_access result. Returns (store_user, deal, contact, access) or
    None. No self-contact special case needed — a self-contact's own deals
    live in the household pool's deals.json alongside its record, reached by
    the same general candidate-store scan as any other deal."""
    from services.contacts_service import (
        _candidate_stores,
        _cross_workspace_visible,
        get_contact,
        resolve_access,
    )

    for store_user, store_ws in _candidate_stores(viewer, viewer_role, workspace):
        deal = next((d for d in _list_deals(store_user, store_ws) if d["id"] == deal_id), None)
        if deal is None:
            continue
        contact = get_contact(store_user, store_ws, deal.get("contact_id") or "")
        if contact is None:
            return None
        if not _cross_workspace_visible(contact, store_ws, workspace):
            return None
        access = resolve_access(viewer, viewer_role, is_admin, store_user, contact, store_ws)
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
    from services.contacts_service import _now

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
    from services.contacts_service import _now

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
    from services.contacts_service import _now

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
    from services.contacts_service import _now

    items = _list_deals(store_user, workspace)
    for i, d in enumerate(items):
        if d["id"] != deal_id:
            continue
        ids = [a for a in (d.get("linked_asset_ids") or []) if a != asset_id]
        items[i] = {**d, "linked_asset_ids": ids, "updated_at": _now()}
        _save_deals(store_user, workspace, items)
        return items[i]
    return None
