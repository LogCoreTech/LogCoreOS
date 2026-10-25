"""Contacts automation API (n8n) — X-Automation-Token, write-focused, NO bulk
export. A leaked token can upsert/log against a known contact but can never
dump or list the contact base."""

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from services import automations_config, contacts_service
from services.auth_service import get_user_by_name
from services.rate_limiter import rate_limit

_automation_limit = rate_limit(30, 60)

router = APIRouter()


def _require_automation_token(x_automation_token: str = Header("")) -> None:
    if not automations_config.verify_api_token(x_automation_token):
        raise HTTPException(status_code=401, detail="Invalid automation token")


def _automation_store(user: str, workspace: str) -> tuple[str, str]:
    if user in ("_team", "_household"):
        return user, "personal"
    if get_user_by_name(user) is None:
        raise HTTPException(status_code=404, detail=f"Unknown user {user!r}")
    return user, workspace


class AutoContact(BaseModel):
    user: str
    workspace: str = "personal"
    name: str = Field(..., min_length=1, max_length=200)
    type: str = Field(default="person", pattern="^(person|company)$")
    emails: list[str] | None = None
    phones: list[str] | None = None
    tags: list[str] | None = None
    notes: str | None = None
    external_id: str | None = Field(default=None, max_length=128)


@router.get("/automation/lookup")
def automation_lookup(
    user: str,
    workspace: str = "personal",
    email: str = "",
    name: str = "",
    phone: str = "",
    external_id: str = "",
    _auth: None = Depends(_require_automation_token),
    _rl: None = Depends(_automation_limit),
):
    """Single-contact dedup lookup. Deliberately NOT a list/export endpoint —
    a leaked token cannot dump the contact base."""
    store, store_ws = _automation_store(user, workspace)
    match = contacts_service.find_match(
        store, store_ws, name=name, email=email, phone=phone, external_id=external_id
    )
    return {"found": bool(match), "contact_id": match["id"] if match else None}


@router.post("/automation/contacts")
def automation_upsert_contact(
    req: AutoContact,
    _auth: None = Depends(_require_automation_token),
    _rl: None = Depends(_automation_limit),
):
    """Create-or-merge. Matches on external_id, email, phone, then name; an
    update merges (never wipes fields the caller didn't send — see
    contacts_service.upsert_external_contact)."""
    store, store_ws = _automation_store(req.user, req.workspace)
    # exclude_unset: an omitted field must mean "leave alone", not "set to None".
    data = req.model_dump(exclude={"user", "workspace"}, exclude_unset=True)
    data["name"] = req.name
    try:
        contact, created = contacts_service.upsert_external_contact(
            store, store_ws, data, created_by="automation"
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"id": contact["id"], "created": created}


class AutoInteraction(BaseModel):
    user: str
    workspace: str = "personal"
    contact_id: str
    type: str = Field(default="note", pattern="^(call|email|meeting|text|note)$")
    summary: str = Field(default="", max_length=5000)
    date: str | None = None
    follow_up: str | None = None


@router.post("/automation/interactions")
def automation_add_interaction(
    req: AutoInteraction,
    _auth: None = Depends(_require_automation_token),
    _rl: None = Depends(_automation_limit),
):
    store, store_ws = _automation_store(req.user, req.workspace)
    if not contacts_service.get_contact(store, store_ws, req.contact_id):
        raise HTTPException(status_code=404, detail="Contact not found")
    try:
        return contacts_service.add_interaction(
            store, store_ws, req.contact_id, req.model_dump(), created_by="automation"
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class AutoDeal(BaseModel):
    user: str
    workspace: str = "personal"
    contact_id: str
    title: str = Field(..., min_length=1, max_length=120)
    value_cents: int = 0
    stage: str | None = None


@router.post("/automation/deals")
def automation_add_deal(
    req: AutoDeal,
    _auth: None = Depends(_require_automation_token),
    _rl: None = Depends(_automation_limit),
):
    store, store_ws = _automation_store(req.user, req.workspace)
    if not contacts_service.get_contact(store, store_ws, req.contact_id):
        raise HTTPException(status_code=404, detail="Contact not found")
    try:
        return contacts_service.add_deal(
            store, store_ws, req.contact_id, req.model_dump(), created_by="automation"
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
