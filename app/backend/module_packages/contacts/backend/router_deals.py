"""Contacts interactions + deals: the pipeline/CRM timeline for a contact.

contribute access may log interactions and create/advance deals but never
edit core contact fields, delete, or reshare — enforced via
_require_contribute (shared with the core router)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from module_packages.contacts.backend.router import (
    _find_or_404,
    _require_contribute,
    _require_edit,
    _validate_id,
)
from routers.auth import get_workspace, require_module
from services import contacts_service
from services.rate_limiter import rate_limit

_require_contacts = require_module("contacts")
_read_limit = rate_limit(60, 60)
_write_limit = rate_limit(30, 60)

router = APIRouter()


class InteractionCreate(BaseModel):
    type: str = Field(default="note", pattern="^(call|email|meeting|text|note)$")
    summary: str = Field(default="", max_length=5000)
    date: str | None = None
    follow_up: str | None = None


class InteractionUpdate(BaseModel):
    summary: str | None = Field(default=None, max_length=5000)
    follow_up: str | None = None
    follow_up_done: bool | None = None


class DealCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    value_cents: int = 0
    stage: str | None = None
    expected_close: str | None = None
    follow_up: str | None = None
    notes: str | None = None


class DealUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    value_cents: int | None = None
    stage: str | None = None
    expected_close: str | None = None
    follow_up: str | None = None
    notes: str | None = None
    invoice_id: str | None = None


class DealAssetLink(BaseModel):
    asset_id: str = Field(..., min_length=1, max_length=64)


# ---------------------------------------------------------------------------
# Interactions
# ---------------------------------------------------------------------------


@router.get("/{contact_id}/interactions")
def list_interactions(
    contact_id: str,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    store_user, contact, _access = _find_or_404(current_user, workspace, contact_id)
    return contacts_service.list_interactions(
        store_user, contacts_service.effective_workspace(store_user, contact, workspace), contact_id
    )


@router.post("/{contact_id}/interactions")
def add_interaction(
    contact_id: str,
    req: InteractionCreate,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, contact, access = _find_or_404(current_user, workspace, contact_id)
    _require_contribute(access)
    try:
        return contacts_service.add_interaction(
            store_user,
            contacts_service.effective_workspace(store_user, contact, workspace),
            contact_id,
            req.model_dump(),
            created_by=current_user["name"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/{contact_id}/interactions/{interaction_id}")
def update_interaction(
    contact_id: str,
    interaction_id: str,
    req: InteractionUpdate,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, contact, access = _find_or_404(current_user, workspace, contact_id)
    _require_contribute(access)
    updated = contacts_service.update_interaction(
        store_user,
        contacts_service.effective_workspace(store_user, contact, workspace),
        interaction_id,
        req.model_dump(exclude_unset=True),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Interaction not found")
    return updated


@router.delete("/{contact_id}/interactions/{interaction_id}")
def delete_interaction(
    contact_id: str,
    interaction_id: str,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, contact, access = _find_or_404(current_user, workspace, contact_id)
    _require_edit(access)
    ws = contacts_service.effective_workspace(store_user, contact, workspace)
    if not contacts_service.delete_interaction(store_user, ws, interaction_id):
        raise HTTPException(status_code=404, detail="Interaction not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Deals
# ---------------------------------------------------------------------------


@router.get("/{contact_id}/deals")
def list_deals(
    contact_id: str,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    store_user, contact, _access = _find_or_404(current_user, workspace, contact_id)
    return contacts_service.list_deals(
        store_user, contacts_service.effective_workspace(store_user, contact, workspace), contact_id
    )


@router.post("/{contact_id}/deals")
def add_deal(
    contact_id: str,
    req: DealCreate,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, contact, access = _find_or_404(current_user, workspace, contact_id)
    _require_contribute(access)
    try:
        return contacts_service.add_deal(
            store_user,
            contacts_service.effective_workspace(store_user, contact, workspace),
            contact_id,
            req.model_dump(),
            created_by=current_user["name"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/{contact_id}/deals/{deal_id}")
def update_deal(
    contact_id: str,
    deal_id: str,
    req: DealUpdate,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, contact, access = _find_or_404(current_user, workspace, contact_id)
    _require_contribute(access)
    try:
        updated = contacts_service.update_deal(
            store_user,
            contacts_service.effective_workspace(store_user, contact, workspace),
            deal_id,
            req.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not updated:
        raise HTTPException(status_code=404, detail="Deal not found")
    return updated


@router.delete("/{contact_id}/deals/{deal_id}")
def delete_deal(
    contact_id: str,
    deal_id: str,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, contact, access = _find_or_404(current_user, workspace, contact_id)
    _require_edit(access)
    if not contacts_service.delete_deal(
        store_user, contacts_service.effective_workspace(store_user, contact, workspace), deal_id
    ):
        raise HTTPException(status_code=404, detail="Deal not found")
    return {"ok": True}


@router.get("/deals/{deal_id}")
def get_deal_by_id(
    deal_id: str,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_read_limit),
):
    """Deal lookup by id alone — used by Finance surfaces (invoice/tx context
    chips) that only hold a deal_id. Access inherits from the parent contact."""
    _validate_id(deal_id, "deal ID")
    found = contacts_service.find_deal(
        current_user["name"],
        current_user.get("feature_role", "member"),
        current_user.get("role") == "admin",
        workspace,
        deal_id,
    )
    if not found:
        raise HTTPException(status_code=404, detail="Deal not found")
    _store_user, deal, contact, access = found
    return {
        **deal,
        "_access": access,
        "_contact_id": contact["id"],
        "_contact_name": contact.get("name", ""),
    }


@router.post("/{contact_id}/deals/{deal_id}/assets")
def link_deal_asset(
    contact_id: str,
    deal_id: str,
    req: DealAssetLink,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    """Link an existing Asset to a deal. Contribute-level (same bucket as deal
    create/advance). Read access on the asset is enough — the gated write is
    the deal mutation, not the asset."""
    store_user, contact, access = _find_or_404(current_user, workspace, contact_id)
    _require_contribute(access)
    from services import assets_service

    found = assets_service.find_asset(
        current_user["name"],
        workspace,
        req.asset_id,
        is_admin=current_user.get("role") == "admin",
        pool_edit=current_user.get("pool_edit") or [],
        viewer_role=current_user.get("feature_role", "member"),
    )
    if found is None:
        raise HTTPException(status_code=404, detail="Asset not found or not visible to you")
    updated = contacts_service.link_asset(
        store_user,
        contacts_service.effective_workspace(store_user, contact, workspace),
        deal_id,
        req.asset_id,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    return updated


@router.delete("/{contact_id}/deals/{deal_id}/assets/{asset_id}")
def unlink_deal_asset(
    contact_id: str,
    deal_id: str,
    asset_id: str,
    current_user: dict = Depends(_require_contacts),
    workspace: str = Depends(get_workspace),
    _rl: None = Depends(_write_limit),
):
    store_user, contact, access = _find_or_404(current_user, workspace, contact_id)
    _require_contribute(access)
    updated = contacts_service.unlink_asset(
        store_user,
        contacts_service.effective_workspace(store_user, contact, workspace),
        deal_id,
        asset_id,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    return updated
