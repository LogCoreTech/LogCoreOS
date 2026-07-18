"""update.py — update status check and trigger. Admin only."""

from fastapi import APIRouter, Depends, HTTPException

from routers.auth import get_current_user

router = APIRouter()


def _admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin only")
    return user


@router.get("/status")
def update_status(_: dict = Depends(_admin)) -> dict:
    from services.update_service import get_update_status

    return get_update_status()


@router.post("/check")
def check_now(_: dict = Depends(_admin)) -> dict:
    """Force-refresh the GitHub version cache (bypasses the 4h TTL), return fresh status."""
    from services.update_service import get_update_status, refresh_version_cache

    refresh_version_cache()
    return get_update_status()


@router.post("/apply")
def apply_update(_: dict = Depends(_admin)) -> dict:
    """Write the pending_update flag. Requires update.sh --watch running on the host."""
    from services.update_service import get_update_status, trigger_update

    status = get_update_status()
    if status.get("update_running"):
        raise HTTPException(409, "Update already in progress")
    if status.get("update_pending"):
        raise HTTPException(409, "Update already queued")
    return trigger_update()


@router.get("/log")
def update_log(lines: int = 100, _: dict = Depends(_admin)) -> dict:
    from services.update_service import get_update_log

    return {"lines": get_update_log(lines)}


@router.get("/settings")
def get_settings(_: dict = Depends(_admin)) -> dict:
    from services.update_service import get_auto_update_enabled

    return {"auto_update": get_auto_update_enabled()}


@router.patch("/settings")
def patch_settings(body: dict, _: dict = Depends(_admin)) -> dict:
    from services.update_service import set_auto_update_enabled

    if "auto_update" not in body:
        raise HTTPException(400, "auto_update field required")
    set_auto_update_enabled(bool(body["auto_update"]))
    return {"auto_update": bool(body["auto_update"])}
