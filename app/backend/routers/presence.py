"""App-wide online/offline presence ping — Layout.jsx pings this on an
interval while any page is open and visible (owner ask, 2026-08-17: an
online/offline dot on user-linked contacts). No general "look up anyone's
presence" endpoint is exposed here on purpose — presence is only ever meant
to surface embedded in an already access-controlled read (a contact record),
never as its own free lookup by username."""

from fastapi import APIRouter, Depends

from routers.auth import get_current_user
from services.presence_service import record_presence
from services.rate_limiter import rate_limit

router = APIRouter()
_ping_limit = rate_limit(10, 60)


@router.post("/ping")
def ping(current_user: dict = Depends(get_current_user), _rl: None = Depends(_ping_limit)):
    record_presence(current_user["name"])
    return {"ok": True}
