"""Web Push subscription management and VAPID public key endpoint."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.auth import get_current_user
from services.push_service import (
    delete_subscription,
    get_subscription,
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
    get_vapid_public_key()  # just ensure keys are generated
    # Distinguish "never subscribed" from "subscribed, but the send itself
    # failed" — these used to collapse into one generic message, making the
    # real cause (VAPID subject, an expired subscription, a push-service
    # rejection) invisible without shell access to the server logs.
    if get_subscription(current_user["name"]) is None:
        raise HTTPException(
            status_code=400,
            detail='No push subscription on file for this account — click "Enable Push '
            'Notifications" first, then try the test again.',
        )
    ok = send_push(current_user["name"], req.title, req.body)
    if not ok:
        raise HTTPException(
            status_code=502,
            detail="A subscription exists but the push service rejected or failed the "
            "send. Check the server logs (services.push.*) for the exact reason.",
        )
    return {"ok": True}
