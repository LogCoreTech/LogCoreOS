from fastapi import APIRouter, Body, Depends
from typing import Any

from routers.auth import get_current_user
from services.rate_limiter import rate_limit
from services.profile_service import load_profile, save_profile

router = APIRouter()
_write_limit = rate_limit(10, 60)


@router.get("")
def get_profile(current_user: dict = Depends(get_current_user)):
    return load_profile(current_user["name"])


@router.put("")
def put_profile(
    body: dict[str, Any] = Body(...),
    current_user: dict = Depends(get_current_user),
    _rl: None = Depends(_write_limit),
):
    return save_profile(current_user["name"], body)
