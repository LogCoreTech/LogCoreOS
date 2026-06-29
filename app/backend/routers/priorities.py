from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends

from routers.auth import get_current_user
from services.auth_service import today_for_user
from services.profile_service import get_priority_order
from services.file_service import read_json, write_json, user_path

router = APIRouter()


@router.get("")
def get_priorities(current_user: dict = Depends(get_current_user)):
    name = current_user["name"]
    override_file = user_path(name) / "Tasks" / "daily_override.json"
    if override_file.exists():
        data = read_json(override_file, default={})
        today = today_for_user(name).isoformat()
        if data.get("date") == today and data.get("order"):
            return {"order": data["order"]}
    return {"order": get_priority_order(name)}


class OverrideRequest(BaseModel):
    order: list[str] = Field(..., min_length=1, max_length=20)


@router.post("/override")
def save_override(req: OverrideRequest, current_user: dict = Depends(get_current_user)):
    name = current_user["name"]
    override_file = user_path(name) / "Tasks" / "daily_override.json"
    today = today_for_user(name).isoformat()
    write_json(override_file, {"order": req.order, "date": today})
    return {"ok": True}
