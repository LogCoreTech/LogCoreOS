"""Mod Store — browse, install, and uninstall first-party LogCoreOS modules.

Everything here is first-party and hand-reviewed before it's listed — no
untrusted submission path exists (see module_registry.py's docstring for why
that boundary matters). Install/uninstall only ever flip a marker in
installed_modules.json; restart is a separate, admin-triggered action (never
automatic) that actually applies the change to the running process.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from routers.auth import get_current_user, require_admin
from services import mod_store_service, presence_service
from services.auth_service import list_users
from services.rate_limiter import rate_limit

router = APIRouter()
logger = logging.getLogger("logcore.mod_store")

_read_limit = rate_limit(30, 60)
_write_limit = rate_limit(10, 60)


@router.get("/catalog")
def get_catalog(
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_read_limit),
):
    """Full catalog with live installed/error/uninstallable state. Admin-only —
    the catalog can reveal broken-module errors, install history isn't for
    every user's eyes."""
    return {"modules": mod_store_service.get_catalog()}


@router.get("/installed")
def get_installed(
    current_user: dict = Depends(get_current_user),
    _rl: None = Depends(_read_limit),
):
    """Which module ids are marked installed right now — any logged-in user,
    since the frontend's own module-loading needs this to decide nav/routes."""
    return {"installed": sorted(mod_store_service.get_installed_ids())}


@router.get("/active")
def get_active(
    request: Request,
    current_user: dict = Depends(get_current_user),
    _rl: None = Depends(_read_limit),
):
    """Which module ids are ACTUALLY registered in the running process —
    cached at boot on app.state by module_registry.register_routers().
    Distinct from /installed: between clicking Install and clicking Restart
    Now, /installed says yes but /active still says no, since the router
    isn't wired into this process until the next restart."""
    return {"active": sorted(getattr(request.app.state, "active_module_ids", set()))}


class RestartRequest(BaseModel):
    force: bool = False


@router.post("/restart")
def restart(
    req: RestartRequest,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_write_limit),
):
    """Restart the app's own container so install/uninstall changes take
    effect. Never automatic — only ever called when the admin explicitly
    clicks "Restart Now". Warns (via 409) if anyone else appears online,
    unless force=true."""
    others_online = [
        u["name"]
        for u in list_users()
        if u["name"] != current_user["name"] and presence_service.is_online(u["name"])
    ]
    if others_online and not req.force:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Other users are currently online and will be briefly disconnected.",
                "online_users": others_online,
            },
        )

    try:
        import docker as docker_sdk

        docker_sdk.from_env().containers.get("logcore-app").restart()
    except Exception:
        logger.exception("mod store restart failed")
        raise HTTPException(status_code=502, detail="Restart failed — check server logs.")

    return {"ok": True, "restarting": True}


@router.post("/install/{module_id}")
def install(
    module_id: str,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_write_limit),
):
    from module_registry import discover_manifests

    catalog_entry = next(
        (e for e in mod_store_service.get_catalog() if e["id"] == module_id), None
    )
    if catalog_entry is None:
        raise HTTPException(status_code=404, detail="Unknown module")
    if catalog_entry["status"] != "available":
        raise HTTPException(status_code=400, detail="This module isn't available to install yet.")
    if mod_store_service.is_installed(module_id):
        raise HTTPException(status_code=409, detail="Already installed")

    # Whitelist lookup against what's actually discovered on disk — module_id
    # is never used to construct a filesystem path directly.
    manifests, _errors = discover_manifests()
    manifest = manifests.get(module_id)
    if manifest is None:
        raise HTTPException(status_code=400, detail="Module code isn't present in this build")

    if manifest.on_install:
        try:
            from services.file_service import brain_path

            manifest.on_install(brain_path())
        except Exception:
            logger.exception("module_packages/%s: on_install hook failed", module_id)
            raise HTTPException(status_code=500, detail="Install setup step failed — check logs.")

    mod_store_service.mark_installed(module_id, by=current_user["name"])
    return {"ok": True, "module_id": module_id, "restart_required": True}


@router.post("/uninstall/{module_id}")
def uninstall(
    module_id: str,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_write_limit),
):
    from module_registry import discover_manifests

    if not mod_store_service.is_installed(module_id):
        raise HTTPException(status_code=404, detail="Not installed")

    manifests, _errors = discover_manifests()
    manifest = manifests.get(module_id)
    if manifest is not None and manifest.uninstallable:
        raise HTTPException(status_code=400, detail="This module can't be uninstalled.")

    mod_store_service.mark_uninstalled(module_id, by=current_user["name"])
    return {"ok": True, "module_id": module_id, "restart_required": True}
