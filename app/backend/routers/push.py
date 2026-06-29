"""Web Push subscription management and VAPID public key endpoint."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.auth import get_current_user
from services.push_service import (
    delete_subscription,
    get_vapid_public_key,
    save_subscription,
    send_push,
)
from services.rate_limiter import rate_limit

router = APIRouter()
_push_limit = rate_limit(10, 60)


class SubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscription(BaseModel):
    endpoint: str = Field(..., max_length=2048)
    keys: SubscriptionKeys


class TestPushRequest(BaseModel):
    title: str = Field(default="LogCore Test", max_length=100)
    body: str = Field(default="Push notifications are working!", max_length=500)


@router.get("/vapid-key")
def vapid_key():
    """Return the VAPID public key for the service worker to use when subscribing."""
    return {"publicKey": get_vapid_public_key()}


@router.post("/subscribe")
def subscribe(
    sub: PushSubscription,
    current_user: dict = Depends(get_current_user),
    _rl: None = Depends(_push_limit),
):
    save_subscription(current_user["name"], sub.model_dump())
    return {"ok": True}


@router.delete("/subscribe")
def unsubscribe(current_user: dict = Depends(get_current_user)):
    delete_subscription(current_user["name"])
    return {"ok": True}


@router.post("/test")
def test_push(
    req: TestPushRequest,
    current_user: dict = Depends(get_current_user),
    _rl: None = Depends(_push_limit),
):
    sub = get_vapid_public_key()  # just ensure keys are generated
    ok = send_push(current_user["name"], req.title, req.body)
    if not ok:
        raise HTTPException(status_code=400, detail="No subscription found or push failed.")
    return {"ok": True}
