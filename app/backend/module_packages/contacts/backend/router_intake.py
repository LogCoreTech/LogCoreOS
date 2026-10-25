"""Lead intake — POST /api/v1/contacts/intake/lead, authenticated by an
integration API key (`leads:create`; routers/auth/deps.py:require_api_key).

Built for an external lead form (e.g. a website's "request a call" form) to
drop a lead straight into Contacts as something to call back. An integration
key belongs to the instance, not a person, and is pinned at creation to one
shared contacts list (Team or Household) — the form can't pick or change
where its leads go. The contact is upserted by phone/email/external_id
(contacts_service.upsert_external_contact — merges, never wipes), tagged
`website`, and gets a note interaction whose `follow_up` date puts it on the
nightly follow-up sweep, which notifies every admin for a shared list.

Write-only by design (docs/MEMORY.md 2026-07-14): the response carries ids
only, never any contact data, so a leaked intake key can add leads but can't
read a thing back. `GET` on the same path describes the fields."""

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException

from routers.auth.deps import require_api_key
from services import contacts_service, mod_store_service
from services.intake_spec import LeadIntake, intake_spec
from services.rate_limiter import rate_limit

router = APIRouter()

_intake_ip_limit = rate_limit(20, 60)
_spec_limit = rate_limit(30, 60)
_intake_key = require_api_key("leads:create", max_calls=10, window_seconds=60)

_SOURCE_RE = re.compile(r"[^a-z0-9]+")


def _source_tag(source: str) -> str:
    return _SOURCE_RE.sub("-", source.strip().lower()).strip("-")[:40]


def _today(tz_name: str):
    try:
        return datetime.now(ZoneInfo(tz_name)).date()
    except (ZoneInfoNotFoundError, ValueError):
        return datetime.now(ZoneInfo("UTC")).date()


@router.get("/intake/lead")
def intake_lead_spec(_rl: None = Depends(_spec_limit)):
    """The fields this endpoint accepts, with descriptions and a ready-to-copy
    example (services/intake_spec.py). Deliberately unauthenticated: it's
    static documentation of the request shape, contains no data, and lets an
    automation tool (or the person wiring up a form) discover the fields
    before they have a key in hand."""
    return intake_spec()


@router.post("/intake/lead")
def intake_lead(
    req: LeadIntake,
    principal: dict = Depends(_intake_key),
    _rl: None = Depends(_intake_ip_limit),
):
    """Upsert the contact by phone/email/external_id (never by name alone),
    tag it, and log a follow-up interaction in the key's shared list."""
    if not mod_store_service.is_installed("contacts"):
        raise HTTPException(status_code=403, detail="Contacts isn't installed on this instance")
    if not contacts_service._phone_key(req.phone):
        raise HTTPException(status_code=400, detail="phone must contain at least 7 digits")
    key = principal["_api_key"]
    store, workspace = key["target"], key["workspace"]

    tags = ["website"]
    source_tag = _source_tag(req.source)
    if source_tag and source_tag not in tags:
        tags.append(source_tag)
    contact_data: dict = {"name": req.name, "phones": [req.phone], "tags": tags}
    if req.email:
        contact_data["emails"] = [req.email]
    if req.external_id:
        contact_data["external_id"] = req.external_id

    created_by = f"api-key:{key['name']}"
    try:
        contact, created = contacts_service.upsert_external_contact(
            store, workspace, contact_data, created_by=created_by, match_name=False
        )
        follow_up = _today(key.get("timezone") or "UTC") + timedelta(days=req.follow_up_days)
        summary = req.message.strip() or "New lead — no message left."
        if req.source.strip():
            summary = f"[{req.source.strip()}] {summary}"
        interaction = contacts_service.add_interaction(
            store,
            workspace,
            contact["id"],
            {"type": "note", "summary": summary, "follow_up": follow_up.isoformat()},
            created_by=created_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "ok": True,
        "contact_id": contact["id"],
        "interaction_id": interaction["id"],
        "created": created,
    }
