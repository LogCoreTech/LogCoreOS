"""
Web Push notification service.

Implements RFC 8291 (Message Encryption for Web Push) and VAPID
(RFC 8292) natively using the `cryptography` library.
No pywebpush dependency required.
"""

import base64
import hmac
import json
import logging
import os
import struct
import time
import urllib.parse
import urllib.request
from hashlib import sha256

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric.ec import (
    ECDH,
    ECDSA,
    SECP256R1,
    EllipticCurvePrivateKey,
    EllipticCurvePublicNumbers,
    generate_private_key,
)
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from config import settings
from services.file_service import brain_path, read_json, write_json

logger = logging.getLogger("logcore.push")

_VAPID_PATH = lambda: brain_path() / "_system" / "vapid_keys.json"
_SUB_PATH = lambda name: brain_path() / "USERS" / name / "push_subscription.json"

# ── helpers ────────────────────────────────────────────────────────────────────


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _b64ud(s: str) -> bytes:
    s += "=" * (4 - len(s) % 4)
    return base64.urlsafe_b64decode(s)


def _hmac(key: bytes, *msgs: bytes) -> bytes:
    h = hmac.new(key, digestmod=sha256)
    for m in msgs:
        h.update(m)
    return h.digest()


# ── VAPID key management ───────────────────────────────────────────────────────

_vapid_cache: tuple[EllipticCurvePrivateKey, str] | None = None


def _load_or_generate_vapid() -> tuple[EllipticCurvePrivateKey, str]:
    """Return (private_key, public_key_b64url). Generates and persists on first call. Cached in memory."""
    global _vapid_cache
    if _vapid_cache is not None:
        return _vapid_cache

    vpath = _VAPID_PATH()
    data = read_json(vpath)
    if data.get("private_key_pem") and data.get("public_key_b64u"):
        from cryptography.hazmat.primitives.serialization import load_pem_private_key

        priv = load_pem_private_key(
            data["private_key_pem"].encode(),
            password=None,
            backend=default_backend(),
        )
        _vapid_cache = (priv, data["public_key_b64u"])
        return _vapid_cache

    priv = generate_private_key(SECP256R1(), default_backend())
    pub_bytes = priv.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    pub_b64u = _b64u(pub_bytes)
    pem = priv.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()
    write_json(vpath, {"private_key_pem": pem, "public_key_b64u": pub_b64u})
    logger.info("Generated new VAPID key pair.")
    _vapid_cache = (priv, pub_b64u)
    return _vapid_cache


def get_vapid_public_key() -> str:
    """Return the VAPID public key as base64url (for the frontend applicationServerKey)."""
    _, pub = _load_or_generate_vapid()
    return pub


# ── Subscription storage ───────────────────────────────────────────────────────


def save_subscription(user_name: str, subscription: dict) -> None:
    write_json(_SUB_PATH(user_name), subscription)


def delete_subscription(user_name: str) -> None:
    path = _SUB_PATH(user_name)
    if path.exists():
        path.unlink()


def get_subscription(user_name: str) -> dict | None:
    data = read_json(_SUB_PATH(user_name))
    return data if data.get("endpoint") else None


# ── VAPID JWT ──────────────────────────────────────────────────────────────────


def _build_vapid_jwt(private_key: EllipticCurvePrivateKey, endpoint: str) -> str:
    """Build a signed VAPID JWT (ES256)."""
    parsed = urllib.parse.urlparse(endpoint)
    audience = f"{parsed.scheme}://{parsed.netloc}"
    subject = f"mailto:{settings.vapid_subject}"

    header_b = _b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    payload_b = _b64u(
        json.dumps(
            {"aud": audience, "exp": int(time.time()) + 86400, "sub": subject},
            separators=(",", ":"),
        ).encode()
    )
    signing_input = f"{header_b}.{payload_b}".encode()

    sig_der = private_key.sign(signing_input, ECDSA(SHA256()))
    r, s = decode_dss_signature(sig_der)
    sig_bytes = r.to_bytes(32, "big") + s.to_bytes(32, "big")

    return f"{header_b}.{payload_b}.{_b64u(sig_bytes)}"


# ── RFC 8291 payload encryption ────────────────────────────────────────────────


def _encrypt_payload(subscription: dict, plaintext: bytes) -> bytes:
    """
    Encrypt plaintext per RFC 8291 (aes128gcm content encoding).
    Returns the raw HTTP request body.
    """
    auth_secret = _b64ud(subscription["keys"]["auth"])
    ua_pub_raw = _b64ud(subscription["keys"]["p256dh"])

    # Rebuild receiver's public key from uncompressed point bytes (65 bytes, 0x04 prefix)
    if len(ua_pub_raw) != 65 or ua_pub_raw[0] != 0x04:
        raise ValueError(
            f"Invalid p256dh: expected 65-byte uncompressed EC point, got {len(ua_pub_raw)} bytes"
        )
    x = int.from_bytes(ua_pub_raw[1:33], "big")
    y = int.from_bytes(ua_pub_raw[33:65], "big")
    ua_public = EllipticCurvePublicNumbers(x, y, SECP256R1()).public_key(default_backend())

    # Ephemeral sender key pair
    as_private = generate_private_key(SECP256R1(), default_backend())
    as_pub_raw = as_private.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)

    # ECDH shared secret
    ecdh_secret = as_private.exchange(ECDH(), ua_public)

    # RFC 8291 §3.3 key derivation
    key_info = b"WebPush: info\x00" + ua_pub_raw + as_pub_raw
    prk_key = _hmac(auth_secret, ecdh_secret, key_info)

    salt = os.urandom(16)
    prk = _hmac(salt, prk_key)

    cek = _hmac(prk, b"Content-Encoding: aes128gcm\x00\x01")[:16]
    nonce = _hmac(prk, b"Content-Encoding: nonce\x00\x01")[:12]

    # Pad + encrypt (RFC 8188 record format, single record)
    padded = plaintext + b"\x02"  # \x02 = padding delimiter, no padding
    ciphertext = AESGCM(cek).encrypt(nonce, padded, None)

    # RFC 8188 §2.1 header: salt(16) + rs(4 big-endian) + keylen(1) + as_public
    rs = 4096
    header = salt + struct.pack(">I", rs) + bytes([len(as_pub_raw)]) + as_pub_raw
    return header + ciphertext


# ── High-level send ────────────────────────────────────────────────────────────


def send_push(user_name: str, title: str, body: str, url: str = "/") -> bool:
    """
    Send a Web Push notification to the stored subscription for user_name.
    Returns True on success (2xx from push service), False otherwise.
    """
    sub = get_subscription(user_name)
    if not sub:
        return False

    private_key, pub_b64u = _load_or_generate_vapid()
    endpoint = sub["endpoint"]
    jwt = _build_vapid_jwt(private_key, endpoint)

    payload = json.dumps({"title": title, "body": body, "url": url}).encode()
    encrypted = _encrypt_payload(sub, payload)

    req = urllib.request.Request(
        url=endpoint,
        data=encrypted,
        method="POST",
        headers={
            "Authorization": f"vapid t={jwt},k={pub_b64u}",
            "Content-Encoding": "aes128gcm",
            "Content-Type": "application/octet-stream",
            "TTL": "86400",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            success = 200 <= resp.status < 300
            if not success:
                logger.warning("Push returned %d for %s", resp.status, user_name)
            return success
    except Exception as exc:
        if hasattr(exc, "code") and exc.code == 410:
            # Subscription expired — clean it up
            logger.info("Push subscription gone for %s, removing.", user_name)
            delete_subscription(user_name)
        else:
            logger.error("Push send failed for %s: %s", user_name, exc)
        return False
