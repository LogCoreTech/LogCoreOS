from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routers.auth import get_current_user
from services.auth_service import today_for_user
from services.file_service import parse_priority_order, write_json, override_path
from services.priority_service import get_priority_order

router = APIRouter()


class OverrideRequest(BaseModel):
    order: list[str]


@router.get("")
def get_priorities(current_user: dict = Depends(get_current_user)):
    return {
        "order": get_priority_order(current_user["name"]),
        "profile_order": parse_priority_order(current_user["name"]),
    }


@router.post("/override")
def set_override(req: OverrideRequest, current_user: dict = Depends(get_current_user)):
    # Validate that submitted categories exist in user's profile
    profile_order = parse_priority_order(current_user["name"])
    invalid = [c for c in req.order if c not in profile_order]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown categories: {invalid}. Add them to your profile first.",
        )
    payload = {"date": today_for_user(current_user["name"]).isoformat(), "order": req.order}
    write_json(override_path(current_user["name"]), payload)
    return {"ok": True, "date": payload["date"], "order": req.order}
