"""Web Push subscription management and VAPID public key endpoint."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.auth import get_current_user
from services.push_service import (
    delete_device,
    delete_subscription,
    get_subscriptions,
    get_vapid_public_key,
    list_devices,
    rename_device,
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
    label: str | None = Field(default=None, max_length=100)


class UnsubscribeRequest(BaseModel):
    endpoint: str = Field(..., max_length=2048)


class RenameDeviceRequest(BaseModel):
    label: str = Field(..., min_length=1, max_length=100)


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
    data = sub.model_dump()
    label = data.pop("label", None)
    try:
        save_subscription(current_user["name"], data, label=label)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.delete("/subscribe")
def unsubscribe(req: UnsubscribeRequest, current_user: dict = Depends(get_current_user)):
    """Unsubscribe THIS device — the caller already knows its own endpoint
    from the live browser subscription object. To remove a different device,
    use DELETE /push/devices/{id} instead."""
    delete_subscription(current_user["name"], endpoint=req.endpoint)
    return {"ok": True}


@router.get("/devices")
def devices(current_user: dict = Depends(get_current_user)):
    """Every device with push enabled for this account — no raw endpoint/keys,
    just enough to tell devices apart and remove one that isn't the device
    making this request (an old phone you no longer have, say)."""
    return {"devices": list_devices(current_user["name"])}


@router.delete("/devices/{device_id}")
def remove_device(device_id: str, current_user: dict = Depends(get_current_user)):
    if not delete_device(current_user["name"], device_id):
        raise HTTPException(status_code=404, detail="No matching device subscription.")
    return {"ok": True}


@router.patch("/devices/{device_id}")
def rename(
    device_id: str, req: RenameDeviceRequest, current_user: dict = Depends(get_current_user)
):
    """Overwrite one device's label. No browser exposes a device's real name
    or model to a web page — a self-chosen label is the only way to tell two
    devices apart in the list, so this is the fix for 'every device says
    Unknown device', not a cosmetic nicety."""
    label = req.label.strip()
    if not label:
        raise HTTPException(status_code=422, detail="Label cannot be blank.")
    if not rename_device(current_user["name"], device_id, label):
        raise HTTPException(status_code=404, detail="No matching device subscription.")
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
    if not get_subscriptions(current_user["name"]):
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
            "send on every device. Check the server logs (services.push.*) for the exact reason.",
        )
    return {"ok": True}
