"""TOTP two-factor authentication endpoints — enrollment (setup/enable/
disable/recovery-code regeneration), login-time verification, and admin
reset. A new sibling of session.py/profile.py/admin_users.py/
admin_settings.py (not folded into any of them): this is the one auth
concern with a whole new dependency stack (pyotp/qrcode/Fernet) and enough
surface area to warrant its own file per routers/auth/__init__.py's own
"split by concern" convention, and keeps every credential-handling line in
one reviewable place for a security-audit-driven feature. See
routers/auth/__init__.py's docstring for the full package-split rationale."""

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from services import audit_log, auth_service, totp_service
from services.rate_limiter import rate_limit

from .deps import _admin_limit, _set_auth_cookie, get_current_user, require_admin
from .session import _login_response

router = APIRouter()

# /status and /setup verify nothing secret yet — generous but still capped.
_totp_setup_limit = rate_limit(10, 60)
# /enable, /disable, /regenerate all require an already-live session; the
# threat here is a session-holding attacker, not a stranger guessing codes —
# plain per-IP limiting is the right layer, same tier as _password_limit.
_totp_verify_self_limit = rate_limit(5, 60)
# The true login-time boundary — shares the account-lockout trio (below) for
# defense in depth, same window as _login_limit itself.
_totp_verify_login_limit = rate_limit(5, 300, bucket="auth-totp-verify-login")


class EnableTotpRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=16)


class DisableTotpRequest(BaseModel):
    current_password: str
    code: str = Field(..., min_length=1, max_length=16)


class RegenerateRecoveryCodesRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=16)


class VerifyLoginRequest(BaseModel):
    pending_token: str
    code: str = Field(..., min_length=1, max_length=16)


@router.get("/2fa/status")
def totp_status(current_user: dict = Depends(get_current_user)):
    return {
        "enabled": bool(current_user.get("totp_enabled")),
        "recovery_codes_remaining": len(current_user.get("totp_recovery_codes") or []),
    }


@router.post("/2fa/setup")
def setup_totp(
    current_user: dict = Depends(get_current_user),
    _rl: None = Depends(_totp_setup_limit),
):
    """Generates and persists a new (encrypted) secret with totp_enabled
    still False — calling this again before /enable simply overwrites the
    pending secret, so a page refresh mid-setup is harmless."""
    if current_user.get("totp_enabled"):
        raise HTTPException(status_code=400, detail="Two-factor authentication is already enabled.")
    secret = totp_service.generate_secret()
    auth_service.update_user(
        current_user["id"], {"totp_secret": totp_service.encrypt_secret(secret)}
    )
    uri = totp_service.provisioning_uri(secret, current_user["email"])
    return {"secret": secret, "otpauth_uri": uri, "qr_code": totp_service.qr_data_uri(uri)}


@router.post("/2fa/enable")
def enable_totp(
    req: EnableTotpRequest,
    current_user: dict = Depends(get_current_user),
    _rl: None = Depends(_totp_verify_self_limit),
):
    if current_user.get("totp_enabled"):
        raise HTTPException(status_code=400, detail="Two-factor authentication is already enabled.")
    secret = current_user.get("totp_secret")
    if not secret:
        raise HTTPException(status_code=400, detail="Start setup first.")
    if not totp_service.verify_totp_code(totp_service.decrypt_secret(secret), req.code):
        raise HTTPException(status_code=400, detail="Invalid code")
    codes = totp_service.generate_recovery_codes()
    auth_service.update_user(
        current_user["id"],
        {"totp_enabled": True, "totp_recovery_codes": totp_service.hash_recovery_codes(codes)},
    )
    audit_log.record(current_user, "user.2fa_enrolled", current_user["name"])
    return {"ok": True, "recovery_codes": codes}


@router.post("/2fa/disable")
def disable_totp(
    req: DisableTotpRequest,
    current_user: dict = Depends(get_current_user),
    _rl: None = Depends(_totp_verify_self_limit),
):
    """Requires BOTH a correct current password AND a valid code/recovery
    code — disabling 2FA is at least as sensitive as changing a password."""
    if not current_user.get("totp_enabled"):
        raise HTTPException(status_code=400, detail="Two-factor authentication is not enabled.")
    if totp_service.policy_requires_2fa_for(current_user):
        raise HTTPException(
            status_code=403,
            detail="Two-factor authentication is required by your administrator and can't be disabled. Ask an admin to reset it if you've lost access.",
        )
    if not auth_service.verify_password(req.current_password, current_user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    ok, _ = totp_service.check_totp_or_recovery(current_user, req.code)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid code")
    auth_service.update_user(
        current_user["id"],
        {"totp_enabled": False, "totp_secret": None, "totp_recovery_codes": []},
    )
    audit_log.record(current_user, "user.2fa_disabled", current_user["name"])
    return {"ok": True}


@router.post("/2fa/recovery-codes/regenerate")
def regenerate_recovery_codes(
    req: RegenerateRecoveryCodesRequest,
    current_user: dict = Depends(get_current_user),
    _rl: None = Depends(_totp_verify_self_limit),
):
    if not current_user.get("totp_enabled"):
        raise HTTPException(status_code=400, detail="Two-factor authentication is not enabled.")
    ok, _ = totp_service.check_totp_or_recovery(current_user, req.code)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid code")
    codes = totp_service.generate_recovery_codes()
    auth_service.update_user(
        current_user["id"], {"totp_recovery_codes": totp_service.hash_recovery_codes(codes)}
    )
    return {"ok": True, "recovery_codes": codes}


@router.post("/2fa/verify-login")
def verify_login(
    req: VerifyLoginRequest,
    response: Response,
    _rl: None = Depends(_totp_verify_login_limit),
):
    payload = totp_service.decode_pending_token(req.pending_token)
    if not payload:
        raise HTTPException(
            status_code=401, detail="Your 2FA session has expired — please log in again."
        )
    user = auth_service.get_user_by_id(payload["sub"])
    if not user or not user.get("totp_enabled"):
        raise HTTPException(status_code=401, detail="Please log in again.")
    ok, locked = totp_service.verify_second_factor(payload["email"], user, req.code)
    if locked:
        raise HTTPException(
            status_code=429, detail=f"Too many failed attempts. Try again in {locked} seconds."
        )
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid code")
    if payload["mode"] == "bearer":
        return {"token": auth_service.create_token(user)}
    token = auth_service.create_token(user)
    _set_auth_cookie(response, token, auth_service.get_effective_session_minutes())
    return _login_response(user)


@router.post("/admin/users/{user_id}/2fa/reset")
def admin_reset_totp(
    user_id: str,
    current_user: dict = Depends(require_admin),
    _rl: None = Depends(_admin_limit),
):
    """Mirrors admin_reset_password() exactly — no admin_count() guard
    needed, since disabling someone's 2FA never touches admin-privilege
    scarcity the way demoting/deleting an admin does."""
    target = auth_service.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    auth_service.update_user(
        user_id, {"totp_enabled": False, "totp_secret": None, "totp_recovery_codes": []}
    )
    audit_log.record(current_user, "user.2fa_admin_reset", target["name"])
    return {"ok": True}
