"""
Web Push notification service.

Implements RFC 8291 (Message Encryption for Web Push) and VAPID
(RFC 8292) natively using the `cryptography` library.
No pywebpush dependency required.
"""

import base64
import hmac
import ipaddress
import json
import logging
import os
import socket
import struct
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
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
from services.hosting_service import effective_domain_url

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
#
# One user can have push enabled on more than one device (phone + laptop,
# say) — each browser/device produces its own distinct subscription
# (different endpoint, different keys) when it subscribes, even for the same
# user account. Stored as a list, keyed by `endpoint` so re-subscribing the
# same device replaces its own entry instead of appending a duplicate.
# Transparently reads the older single-object format (one subscription, no
# list) that every file predating 2026-08-30 is still in — no migration
# needed, the first save after this ships rewrites it as a list.


def get_subscriptions(user_name: str) -> list[dict]:
    data = read_json(_SUB_PATH(user_name), default=[])
    if isinstance(data, dict):
        return [data] if data.get("endpoint") else []
    return [s for s in data if s.get("endpoint")]


_MAX_DEVICES_PER_USER = 10


def _validate_push_endpoint(endpoint: str) -> None:
    """Reject a subscription endpoint that isn't a real, external push
    service. Without this, any authenticated user can point `endpoint` at an
    internal-only address (the Docker socket-proxy, n8n, cloud instance
    metadata at 169.254.169.254, ...) and the server will POST to it — with
    a signed VAPID header and an encrypted body — every time a notification
    fires, not just on an explicit test send. Validated by resolved IP, not
    a hostname allowlist: push-provider hostnames change/multiply over time
    and a stale allowlist would just break real browsers, while "every
    resolved address must be public" generalizes without maintenance.
    Deliberately does NOT defend against DNS rebinding (a TOCTOU gap between
    this check and the real send later) — legitimate push-provider domains
    are stable, high-reputation domains with no realistic path to resolving
    privately, so full IP-pinning on every send isn't worth the complexity
    it would add here.
    """
    parsed = urllib.parse.urlparse(endpoint)
    if parsed.scheme != "https":
        raise ValueError("Push endpoint must be an https:// URL.")
    if not parsed.hostname:
        raise ValueError("Push endpoint must include a hostname.")
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        raise ValueError("Push endpoint hostname could not be resolved.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise ValueError("Push endpoint resolves to a non-public address and was rejected.")


def save_subscription(user_name: str, subscription: dict, label: str | None = None) -> None:
    existing = get_subscriptions(user_name)
    prior = next((s for s in existing if s.get("endpoint") == subscription.get("endpoint")), None)
    if prior is None:
        _validate_push_endpoint(subscription["endpoint"])
        if len(existing) >= _MAX_DEVICES_PER_USER:
            raise ValueError(
                f"Maximum of {_MAX_DEVICES_PER_USER} push-enabled devices per account."
            )
    subs = [s for s in existing if s.get("endpoint") != subscription.get("endpoint")]
    subs.append(
        {
            **subscription,
            "label": label if label else (prior or {}).get("label", "Unknown device"),
            # Preserve the original subscribe date across a re-save of the
            # same device (a token refresh, or a rename) — only a genuinely
            # new endpoint gets a fresh timestamp.
            "created_at": (prior or {}).get("created_at") or datetime.now(timezone.utc).isoformat(),
        }
    )
    write_json(_SUB_PATH(user_name), subs)


def delete_subscription(user_name: str, endpoint: str | None = None) -> None:
    """Remove one device's subscription by endpoint, or every subscription for
    this user if endpoint is None (e.g. on account deletion)."""
    path = _SUB_PATH(user_name)
    if endpoint is None:
        if path.exists():
            path.unlink()
        return
    remaining = [s for s in get_subscriptions(user_name) if s.get("endpoint") != endpoint]
    if remaining:
        write_json(path, remaining)
    elif path.exists():
        path.unlink()


def _device_id(endpoint: str) -> str:
    """A stable, opaque id for a subscription — safe to hand to the frontend
    instead of the real push endpoint (which is a live, sender-authenticated
    URL to that specific device's push channel)."""
    return sha256(endpoint.encode()).hexdigest()[:16]


def list_devices(user_name: str) -> list[dict]:
    """Every device subscribed for user_name, safe to return to the client —
    no endpoint/keys, just enough to tell devices apart and remove one."""
    return [
        {
            "id": _device_id(s["endpoint"]),
            "label": s.get("label", "Unknown device"),
            "created_at": s.get("created_at"),
        }
        for s in get_subscriptions(user_name)
    ]


def delete_device(user_name: str, device_id: str) -> bool:
    """Remove one device by its opaque id, regardless of whether it's the
    caller's own current device — this is what lets someone clear out an old
    phone they no longer have from a different, currently-active device.
    Returns False if no subscription matched (id already gone)."""
    subs = get_subscriptions(user_name)
    match = next((s for s in subs if _device_id(s["endpoint"]) == device_id), None)
    if match is None:
        return False
    delete_subscription(user_name, endpoint=match["endpoint"])
    return True


def rename_device(user_name: str, device_id: str, label: str) -> bool:
    """Overwrite one device's own label — the real fix for 'Unknown device'
    (or a UA-guessed label that isn't specific enough to tell two phones
    apart): no browser exposes a device's real name or model to a web page,
    on any platform, by design, so a self-chosen name is the only way this
    ever becomes readable. Returns False if no subscription matched."""
    subs = get_subscriptions(user_name)
    match = next((s for s in subs if _device_id(s["endpoint"]) == device_id), None)
    if match is None:
        return False
    save_subscription(user_name, match, label=label)
    return True


# ── VAPID JWT ──────────────────────────────────────────────────────────────────


def _build_vapid_jwt(private_key: EllipticCurvePrivateKey, endpoint: str) -> str:
    """Build a signed VAPID JWT (ES256)."""
    parsed = urllib.parse.urlparse(endpoint)
    audience = f"{parsed.scheme}://{parsed.netloc}"
    # The VAPID spec (RFC 8292) requires `sub` to be a mailto: or https: URI.
    # settings.vapid_subject may already be either (an admin who read the
    # config.py comment literally could set VAPID_SUBJECT=https://example.com)
    # — only wrap it in mailto: if it isn't already a URI, instead of always
    # prepending mailto: regardless of what was configured.
    raw_subject = settings.vapid_subject
    if raw_subject == "logcore@localhost":
        # Nobody set VAPID_SUBJECT — fall back to the domain already
        # configured in Admin -> Hosting (stored as a full https:// URL,
        # a valid VAPID subject as-is) instead of sending Apple/Google a
        # contact address that was never real.
        domain = effective_domain_url()
        if domain:
            raw_subject = domain
    subject = (
        raw_subject if raw_subject.startswith(("mailto:", "https:")) else f"mailto:{raw_subject}"
    )

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

    # RFC 8291 §3.3 key derivation — two SEPARATE, sequentially-keyed HMAC
    # calls (Extract, then Expand with the trailing 0x01 block-counter byte),
    # not one HMAC over the concatenated message. Collapsing these into a
    # single call (as an earlier version of this function did) silently
    # produces a CEK/nonce a spec-compliant receiver never derives — the push
    # service still accepts and relays the opaque ciphertext with a 2xx (it
    # never decrypts it), but the device fails AES-GCM auth on decrypt and
    # discards the notification with no visible error anywhere.
    key_info = b"WebPush: info\x00" + ua_pub_raw + as_pub_raw
    prk_key = _hmac(auth_secret, ecdh_secret)
    ikm = _hmac(prk_key, key_info + b"\x01")

    salt = os.urandom(16)
    prk = _hmac(salt, ikm)

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
    Send a Web Push notification to every device subscribed for user_name.
    One device's failure (expired subscription, unreachable relay, etc.)
    never blocks delivery to the others. Returns True if at least one device
    received it, False only if every device failed (or none are subscribed).
    """
    subs = get_subscriptions(user_name)
    if not subs:
        return False
    # A list comprehension, not any(<generator>) — any() short-circuits on
    # the first True, which would silently skip sending to every device
    # after the first one that succeeds.
    results = [_send_to_one(user_name, sub, title, body, url) for sub in subs]
    return any(results)


def _send_to_one(user_name: str, sub: dict, title: str, body: str, url: str) -> bool:
    # Everything below — JWT building, payload encryption, and the actual
    # send — is wrapped in one try/except. Previously only the urlopen() call
    # was guarded, so a malformed/legacy subscription (bad p256dh/auth
    # base64, wrong point length, etc.) raised straight out of this function
    # uncaught, past the router's own error handling, into FastAPI's generic
    # 500 with a PLAIN-TEXT body ("Internal Server Error", not JSON) — Safari
    # specifically throws its own opaque "The string did not match the
    # expected pattern." parsing that as JSON client-side, which is exactly
    # what made this undiagnosable (2026-08-15). Now any failure here always
    # returns False with the real reason logged server-side, so /push/test's
    # existing 502 path (routers/push.py) is what the caller actually sees.
    try:
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
        with urllib.request.urlopen(req, timeout=10) as resp:
            success = 200 <= resp.status < 300
            if not success:
                logger.warning("Push returned %d for %s", resp.status, user_name)
            return success
    except Exception as exc:
        if hasattr(exc, "code") and exc.code == 410:
            # This one device's subscription expired — remove only its own
            # entry, other devices for this user are unaffected.
            logger.info("Push subscription gone for %s, removing.", user_name)
            delete_subscription(user_name, endpoint=sub.get("endpoint"))
        else:
            logger.error("Push send failed for %s: %s: %s", user_name, type(exc).__name__, exc)
        return False
