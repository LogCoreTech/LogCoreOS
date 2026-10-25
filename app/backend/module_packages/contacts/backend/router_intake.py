"""Lead intake — POST /api/v1/contacts/intake/lead, authenticated by a personal
API key with the `leads:create` scope (routers/auth/deps.py:require_api_key).

Built for an external lead form (e.g. a website's "request a call" form) to
drop a lead straight into Contacts as something to call back: the contact is
upserted by phone (contacts_service.upsert_external_contact — merges, never
wipes), tagged `website`, and gets a note interaction whose `follow_up` date
puts it on the nightly follow-up reminder sweep.

Write-only by design (docs/MEMORY.md 2026-07-14): the response carries ids
only, never any contact data, so a leaked intake key can add leads but can't
read a thing back."""

import re
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.auth.deps import require_api_key
from services import auth_service, contacts_service
from services.rate_limiter import rate_limit

router = APIRouter()

_intake_ip_limit = rate_limit(20, 60)
_intake_key = require_api_key("leads:create", max_calls=10, window_seconds=60)

_SOURCE_RE = re.compile(r"[^a-z0-9]+")


class LeadIntake(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    phone: str = Field(..., min_length=7, max_length=40)
    email: str | None = Field(default=None, max_length=200)
    message: str = Field(default="", max_length=5000)
    source: str = Field(default="", max_length=40)
    external_id: str | None = Field(default=None, max_length=128)
    follow_up_days: int = Field(default=1, ge=0, le=365)
    to_pool: bool = False


def _source_tag(source: str) -> str:
    return _SOURCE_RE.sub("-", source.strip().lower()).strip("-")[:40]


@router.post("/intake/lead")
def intake_lead(
    req: LeadIntake,
    current_user: dict = Depends(_intake_key),
    _rl: None = Depends(_intake_ip_limit),
):
    """Upsert the contact by phone/email/external_id (never by name alone),
    tag it, and log a follow-up interaction. `to_pool` drops it into the active workspace's shared pool (Team for
    business, Household for personal) so everyone who works leads sees it."""
    if "contacts" in current_user.get("disabled_modules", []):
        raise HTTPException(status_code=403, detail="Contacts is disabled for this key's account")
    if not contacts_service._phone_key(req.phone):
        raise HTTPException(status_code=400, detail="phone must contain at least 7 digits")
    workspace = current_user["_workspace"]
    store = contacts_service.pool_for(workspace) if req.to_pool else current_user["name"]

    tags = ["website"]
    source_tag = _source_tag(req.source)
    if source_tag and source_tag not in tags:
        tags.append(source_tag)
    contact_data: dict = {"name": req.name, "phones": [req.phone], "tags": tags}
    if req.email:
        contact_data["emails"] = [req.email]
    if req.external_id:
        contact_data["external_id"] = req.external_id

    key_name = current_user["_api_key"]["name"]
    try:
        contact, created = contacts_service.upsert_external_contact(
            store, workspace, contact_data, created_by=f"api-key:{key_name}", match_name=False
        )
        follow_up = auth_service.today_for_user(current_user["name"]) + timedelta(
            days=req.follow_up_days
        )
        summary = req.message.strip() or "New lead — no message left."
        if req.source.strip():
            summary = f"[{req.source.strip()}] {summary}"
        interaction = contacts_service.add_interaction(
            store,
            workspace,
            contact["id"],
            {
                "type": "note",
                "summary": summary,
                "follow_up": follow_up.isoformat(),
            },
            created_by=f"api-key:{key_name}",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "ok": True,
        "contact_id": contact["id"],
        "interaction_id": interaction["id"],
        "created": created,
    }
