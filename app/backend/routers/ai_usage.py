from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.auth import get_current_user, require_admin
from services import ai_usage_service
from services.auth_service import get_user_by_id

router = APIRouter()


class DefaultsRequest(BaseModel):
    period: Literal["daily", "weekly", "monthly"] | None = None
    message_limit: int | None = Field(default=None, ge=1)
    token_limit: int | None = Field(default=None, ge=1)
    warn_pct: int | None = Field(default=None, ge=1, le=100)


class UserLimitsRequest(BaseModel):
    period: Literal["daily", "weekly", "monthly"] | None = None
    mode: Literal["off", "hard", "soft"] | None = None
    message_limit: int | None = Field(default=None, ge=1)
    token_limit: int | None = Field(default=None, ge=1)


@router.get("/overview")
def get_overview(month: str | None = None, _: dict = Depends(require_admin)):
    return ai_usage_service.get_overview(month)


@router.get("/users")
def get_user_rows(month: str | None = None, _: dict = Depends(require_admin)):
    return ai_usage_service.get_user_rows(month)


@router.get("/defaults")
def get_defaults(_: dict = Depends(require_admin)):
    return ai_usage_service.get_defaults()


@router.patch("/defaults")
def update_defaults(req: DefaultsRequest, _: dict = Depends(require_admin)):
    updates = req.model_dump(exclude_unset=True)
    return ai_usage_service.set_defaults(updates)


@router.patch("/users/{user_id}/limits")
def update_user_limits(user_id: str, req: UserLimitsRequest, _: dict = Depends(require_admin)):
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    updates = req.model_dump(exclude_unset=True)
    return ai_usage_service.set_user_limits(user["name"], updates)


@router.get("/me")
def get_my_usage(current_user: dict = Depends(get_current_user)):
    return ai_usage_service.get_my_usage(current_user["name"])
