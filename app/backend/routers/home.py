"""Home module — Home Assistant device control and monitoring."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routers.auth import get_current_user, require_admin, require_module
from services import ha_service
from services.rate_limiter import rate_limit

logger = logging.getLogger("logcore.home")

_require_home = require_module("home")
_read_limit  = rate_limit(60, 60)
_write_limit = rate_limit(20, 60)

router = APIRouter()


class HaConfigRequest(BaseModel):
    url: str
    token: str


class CallServiceRequest(BaseModel):
    service: str
    data: dict = {}


class FavouritesRequest(BaseModel):
    entity_ids: list[str]


# ── Admin config endpoints ─────────────────────────────────────────────────────

@router.get("/status")
def ha_status(
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_read_limit),
):
    return ha_service.test_connection()


@router.post("/config")
def save_ha_config(
    req: HaConfigRequest,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_write_limit),
):
    ha_service.save_config({"url": req.url.strip(), "token": req.token.strip()})
    return {"ok": True}


# ── Entity endpoints ──────────────────────────────────────────────────────────

@router.get("/entities")
def list_entities(
    domain: str | None = None,
    current_user: dict = Depends(_require_home),
    _rl: None = Depends(_read_limit),
):
    if not ha_service.is_configured():
        return []
    try:
        return ha_service.get_states(domain)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"HA error: {exc}") from exc


@router.get("/entities/{entity_id:path}")
def get_entity(
    entity_id: str,
    current_user: dict = Depends(_require_home),
    _rl: None = Depends(_read_limit),
):
    if not ha_service.is_configured():
        raise HTTPException(status_code=503, detail="Home Assistant not configured")
    try:
        return ha_service.get_state(entity_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"HA error: {exc}") from exc


@router.post("/entities/{entity_id:path}/call")
def call_entity_service(
    entity_id: str,
    req: CallServiceRequest,
    current_user: dict = Depends(_require_home),
    _rl: None = Depends(_write_limit),
):
    if not ha_service.is_configured():
        raise HTTPException(status_code=503, detail="Home Assistant not configured")
    try:
        domain = entity_id.split(".")[0]
        data = {**req.data, "entity_id": entity_id}
        return ha_service.call_service(domain, req.service, data)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"HA error: {exc}") from exc


# ── Areas ─────────────────────────────────────────────────────────────────────

@router.get("/areas")
def list_areas(
    current_user: dict = Depends(_require_home),
    _rl: None = Depends(_read_limit),
):
    if not ha_service.is_configured():
        return []
    try:
        return ha_service.get_areas()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"HA error: {exc}") from exc


# ── Scenes ────────────────────────────────────────────────────────────────────

@router.get("/scenes")
def list_scenes(
    current_user: dict = Depends(_require_home),
    _rl: None = Depends(_read_limit),
):
    if not ha_service.is_configured():
        return []
    try:
        return ha_service.get_scenes()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"HA error: {exc}") from exc


@router.post("/scenes/{entity_id:path}/activate")
def activate_scene(
    entity_id: str,
    current_user: dict = Depends(_require_home),
    _rl: None = Depends(_write_limit),
):
    if not ha_service.is_configured():
        raise HTTPException(status_code=503, detail="Home Assistant not configured")
    try:
        return ha_service.call_service("scene", "turn_on", {"entity_id": entity_id})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"HA error: {exc}") from exc


# ── Automations ───────────────────────────────────────────────────────────────

@router.get("/automations")
def list_ha_automations(
    current_user: dict = Depends(_require_home),
    _rl: None = Depends(_read_limit),
):
    if not ha_service.is_configured():
        return []
    try:
        return ha_service.get_automations()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"HA error: {exc}") from exc


@router.post("/automations/{entity_id:path}/trigger")
def trigger_ha_automation(
    entity_id: str,
    current_user: dict = Depends(_require_home),
    _rl: None = Depends(_write_limit),
):
    if not ha_service.is_configured():
        raise HTTPException(status_code=503, detail="Home Assistant not configured")
    try:
        return ha_service.trigger_automation(entity_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"HA error: {exc}") from exc


# ── Favourites ────────────────────────────────────────────────────────────────

@router.get("/favourites")
def get_favourites(
    current_user: dict = Depends(_require_home),
    _rl: None = Depends(_read_limit),
):
    return ha_service.get_favourites(current_user["name"])


@router.put("/favourites")
def save_favourites(
    req: FavouritesRequest,
    current_user: dict = Depends(_require_home),
    _rl: None = Depends(_write_limit),
):
    ha_service.save_favourites(current_user["name"], req.entity_ids)
    return {"ok": True}
