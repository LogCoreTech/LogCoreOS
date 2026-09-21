"""TOTP two-factor authentication — secret generation/encryption, QR
provisioning, code/recovery-code verification, and the short-lived
pending-2FA token minted between password-check and full-session-mint at
login. Imports auth_service one-directionally (hash_password/verify_password/
update_user/get_system_settings/the account-lockout trio) — auth_service.py
itself needs zero changes for this feature.

Secret storage mirrors services/infisical_loader.py's own Fernet pattern
exactly, but field-level (just the totp_secret string) rather than
whole-file, since auth.json round-trips the entire users array through one
plain json.dumps/loads today and wrapping that entirely would be a much
bigger, riskier change than this feature needs. TOTP_ENCRYPTION_KEY is a new,
dedicated env var (not reusing INFISICAL_CACHE_KEY, which is semantically
scoped to Infisical specifically) — same graceful philosophy: unset means
plaintext-in-auth.json (the same trust model the bcrypt password hash already
implies for that file), never a blocked feature or failed startup."""

import base64
import io
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

import pyotp
import qrcode
from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt

from config import settings
from services import auth_service

logger = logging.getLogger(__name__)

_ISSUER = "LogCoreOS"
_RECOVERY_CODE_COUNT = 10
_PENDING_TOKEN_MINUTES = 5
_PENDING_PURPOSE = "2fa_pending"


def _cipher() -> Fernet | None:
    """Mirrors services/infisical_loader.py's own _cipher() exactly — None
    (plaintext fallback) if TOTP_ENCRYPTION_KEY isn't configured or is
    invalid, never a hard failure."""
    key = os.environ.get("TOTP_ENCRYPTION_KEY", "").strip()
    if not key:
        return None
    try:
        return Fernet(key.encode())
    except Exception:
        logger.warning("TOTP_ENCRYPTION_KEY is set but invalid — storing/reading as plaintext.")
        return None


def encrypt_secret(plaintext: str) -> str:
    cipher = _cipher()
    if not cipher:
        return plaintext
    return cipher.encrypt(plaintext.encode()).decode()


def decrypt_secret(stored: str) -> str:
    """Legacy-plaintext-tolerant, same shape as infisical_loader's
    _read_encrypted_json(): try decrypting first, fall back to treating the
    stored value as already-plaintext (covers both "no key configured" and
    "key was configured when this secret was written, but isn't now")."""
    cipher = _cipher()
    if cipher:
        try:
            return cipher.decrypt(stored.encode()).decode()
        except InvalidToken:
            pass
    return stored


def generate_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name=_ISSUER)


def qr_data_uri(uri: str) -> str:
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{encoded}"


def verify_totp_code(secret: str, code: str) -> bool:
    """valid_window=1 tolerates +/-30s clock drift — a household member's
    phone isn't NTP-audited."""
    try:
        return pyotp.totp.TOTP(secret).verify((code or "").strip(), valid_window=1)
    except Exception:
        return False


def generate_recovery_codes(n: int = _RECOVERY_CODE_COUNT) -> list[str]:
    return [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}".upper() for _ in range(n)]


def hash_recovery_codes(codes: list[str]) -> list[str]:
    return [auth_service.hash_password(c) for c in codes]


def consume_recovery_code(code: str, hashed_codes: list[str]) -> list[str] | None:
    """Returns the remaining hash list with the matched one removed, or None
    if no hash matches — never mutates the input list."""
    code = (code or "").strip().upper()
    if not code:
        return None
    for i, hashed in enumerate(hashed_codes):
        if auth_service.verify_password(code, hashed):
            return hashed_codes[:i] + hashed_codes[i + 1 :]
    return None


def check_totp_or_recovery(user: dict, code: str) -> tuple[bool, list[str] | None]:
    """(ok, updated_recovery_codes) — updated_recovery_codes is only non-None
    when a recovery code was the thing that matched (caller must persist it)."""
    secret = user.get("totp_secret")
    if secret and verify_totp_code(decrypt_secret(secret), code):
        return True, None
    remaining = consume_recovery_code(code, user.get("totp_recovery_codes") or [])
    if remaining is not None:
        return True, remaining
    return False, None


def verify_second_factor(email: str, user: dict, code: str) -> tuple[bool, int]:
    """Lockout-aware wrapper structurally mirroring auth_service.login_attempt()
    exactly — same lowercased-email key as password lockout, so wrong TOTP
    codes and wrong passwords trip the SAME 10-strikes/15-minute lock: one
    unified lockout surface, no parallel counter.

    Returns (ok, lock_remaining_seconds). ok=False with lock_remaining=0 means
    "wrong code, not locked (yet)"."""
    remaining = auth_service.account_lock_remaining(email)
    if remaining > 0:
        return False, remaining
    ok, updated_codes = check_totp_or_recovery(user, code)
    if not ok:
        auth_service.record_failed_login(email)
        return False, 0
    auth_service.clear_failed_login(email)
    if updated_codes is not None:
        auth_service.update_user(user["id"], {"totp_recovery_codes": updated_codes})
    return True, 0


def policy_requires_2fa_for(user: dict) -> bool:
    policy = auth_service.get_system_settings().get("require_2fa", "off")
    if policy == "all":
        return True
    if policy == "admin":
        return user.get("role") == "admin"
    return False


def create_pending_token(user: dict, mode: str) -> str:
    payload = {
        "sub": user["id"],
        "email": user["email"],
        "mode": mode,
        "purpose": _PENDING_PURPOSE,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=_PENDING_TOKEN_MINUTES),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_pending_token(token: str) -> dict | None:
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != settings.algorithm:
            return None
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None
    if payload.get("purpose") != _PENDING_PURPOSE:
        return None
    return payload
