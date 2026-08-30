"""Tests for services/push_service.py — VAPID subject handling and
subscription-vs-send-failure distinction (2026-08-15)."""

import base64
import hmac as hmac_mod
import json
import os
import struct
from hashlib import sha256

import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric.ec import (
    ECDH,
    SECP256R1,
    EllipticCurvePublicNumbers,
    generate_private_key,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from config import settings
from services import push_service


def _b64ud(s: str) -> bytes:
    s += "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s)


def _jwt_sub(jwt: str) -> str:
    header_b, payload_b, _sig_b = jwt.split(".")
    return json.loads(_b64ud(payload_b))["sub"]


def _client_hmac(key: bytes, *msgs: bytes) -> bytes:
    h = hmac_mod.new(key, digestmod=sha256)
    for m in msgs:
        h.update(m)
    return h.digest()


@pytest.fixture(autouse=True)
def _fake_dns(monkeypatch):
    """Stub DNS resolution so every test in this file stays network-free —
    _validate_push_endpoint() (2026-08-30, SSRF fix) does a real
    socket.getaddrinfo() call on every genuinely new subscription, and the
    push.example.com/web.push.apple.com endpoints used throughout this file
    have no reason to actually be looked up. Resolves to a real, definitely-
    public address; individual tests override this via their own monkeypatch
    when they need to test a specific (public or private) resolved address."""
    monkeypatch.setattr(
        push_service.socket,
        "getaddrinfo",
        lambda *a, **k: [(None, None, None, None, ("93.184.216.34", 0))],
    )


def test_bare_email_subject_gets_mailto_prefix(brain, monkeypatch):
    monkeypatch.setattr(settings, "vapid_subject", "admin@example.com")
    private_key, _pub = push_service._load_or_generate_vapid()
    jwt = push_service._build_vapid_jwt(private_key, "https://push.example.com/abc")
    assert _jwt_sub(jwt) == "mailto:admin@example.com"


def test_https_subject_used_as_is_not_double_wrapped(brain, monkeypatch):
    monkeypatch.setattr(settings, "vapid_subject", "https://logcore.example.com")
    private_key, _pub = push_service._load_or_generate_vapid()
    jwt = push_service._build_vapid_jwt(private_key, "https://push.example.com/abc")
    assert _jwt_sub(jwt) == "https://logcore.example.com"


def test_mailto_subject_used_as_is_not_double_wrapped(brain, monkeypatch):
    monkeypatch.setattr(settings, "vapid_subject", "mailto:admin@example.com")
    private_key, _pub = push_service._load_or_generate_vapid()
    jwt = push_service._build_vapid_jwt(private_key, "https://push.example.com/abc")
    assert _jwt_sub(jwt) == "mailto:admin@example.com"


def test_placeholder_subject_uses_configured_domain_automatically(brain, monkeypatch):
    monkeypatch.setattr(settings, "vapid_subject", "logcore@localhost")
    monkeypatch.setattr(push_service, "effective_domain_url", lambda: "https://app.logcoretech.com")
    private_key, _pub = push_service._load_or_generate_vapid()
    jwt = push_service._build_vapid_jwt(private_key, "https://push.example.com/abc")
    assert _jwt_sub(jwt) == "https://app.logcoretech.com"


def test_placeholder_subject_stays_placeholder_with_no_domain_configured(brain, monkeypatch):
    monkeypatch.setattr(settings, "vapid_subject", "logcore@localhost")
    monkeypatch.setattr(push_service, "effective_domain_url", lambda: "")
    private_key, _pub = push_service._load_or_generate_vapid()
    jwt = push_service._build_vapid_jwt(private_key, "https://push.example.com/abc")
    assert _jwt_sub(jwt) == "mailto:logcore@localhost"


def test_encrypt_payload_is_decryptable_by_a_spec_compliant_receiver(brain):
    """
    Round-trips _encrypt_payload() through an independent, RFC 8291-correct
    receiver-side derivation (mirroring what a real browser/OS does with its
    own private key) — the only check that catches a key-derivation bug that
    still produces a well-formed request the push service happily accepts and
    relays (it never decrypts payloads itself), but that no real device can
    ever actually decrypt. A prior version of _encrypt_payload had exactly
    this bug (collapsed two sequentially-keyed HMAC calls into one, and
    dropped the HKDF counter byte) — every push reported "sent" successfully
    while silently failing to decrypt on every receiving device.
    """
    # Simulate the client's own real keypair — generated locally by the
    # browser, private half never sent anywhere, exactly like a real
    # subscription.
    ua_private = generate_private_key(SECP256R1(), default_backend())
    ua_pub_raw = ua_private.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    auth_secret = os.urandom(16)

    subscription = {
        "endpoint": "https://web.push.apple.com/abc",
        "keys": {
            "p256dh": push_service._b64u(ua_pub_raw),
            "auth": push_service._b64u(auth_secret),
        },
    }

    plaintext = b'{"title": "Test", "body": "Hello", "url": "/"}'
    body = push_service._encrypt_payload(subscription, plaintext)

    # Parse the RFC 8188 header: salt(16) + rs(4, unused here) + keylen(1) + as_public
    salt = body[:16]
    keylen = body[20]
    as_pub_raw = body[21 : 21 + keylen]
    ciphertext = body[21 + keylen :]

    x = int.from_bytes(as_pub_raw[1:33], "big")
    y = int.from_bytes(as_pub_raw[33:65], "big")
    as_public = EllipticCurvePublicNumbers(x, y, SECP256R1()).public_key(default_backend())

    # Independent RFC 8291 §3.4 receiver-side derivation — written fresh
    # against the spec, not by calling back into _encrypt_payload's own
    # helpers, so it can't share a mutual bug with the code under test.
    ecdh_secret = ua_private.exchange(ECDH(), as_public)
    key_info = b"WebPush: info\x00" + ua_pub_raw + as_pub_raw
    prk_key = _client_hmac(auth_secret, ecdh_secret)
    ikm = _client_hmac(prk_key, key_info + b"\x01")
    prk = _client_hmac(salt, ikm)
    cek = _client_hmac(prk, b"Content-Encoding: aes128gcm\x00\x01")[:16]
    nonce = _client_hmac(prk, b"Content-Encoding: nonce\x00\x01")[:12]

    decrypted = AESGCM(cek).decrypt(nonce, ciphertext, None)
    assert decrypted.rstrip(b"\x02") == plaintext


def test_send_push_returns_false_with_no_subscription(brain):
    assert push_service.send_push("NoSubUser", "Title", "Body") is False


def _valid_p256dh_b64u() -> str:
    priv = generate_private_key(SECP256R1(), default_backend())
    pub_raw = priv.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return push_service._b64u(pub_raw)


def _fake_sub(endpoint: str) -> dict:
    return {
        "endpoint": endpoint,
        "keys": {"p256dh": _valid_p256dh_b64u(), "auth": push_service._b64u(os.urandom(16))},
    }


class _FakeResponse:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeHTTPError(Exception):
    def __init__(self, code):
        self.code = code


def test_subscription_round_trip(brain):
    assert push_service.get_subscriptions("Alice") == []
    push_service.save_subscription("Alice", _fake_sub("https://push.example.com/x"), label="Laptop")
    subs = push_service.get_subscriptions("Alice")
    assert len(subs) == 1
    assert subs[0]["endpoint"] == "https://push.example.com/x"
    assert subs[0]["label"] == "Laptop"
    assert subs[0]["created_at"]
    push_service.delete_subscription("Alice")
    assert push_service.get_subscriptions("Alice") == []


def test_multiple_devices_coexist_for_one_user(brain):
    push_service.save_subscription(
        "Dana", _fake_sub("https://push.example.com/phone"), label="Phone"
    )
    push_service.save_subscription(
        "Dana", _fake_sub("https://push.example.com/laptop"), label="Laptop"
    )
    subs = push_service.get_subscriptions("Dana")
    assert {s["endpoint"] for s in subs} == {
        "https://push.example.com/phone",
        "https://push.example.com/laptop",
    }


def test_resubscribing_same_endpoint_replaces_not_duplicates(brain):
    push_service.save_subscription(
        "Erin", _fake_sub("https://push.example.com/phone"), label="Old label"
    )
    push_service.save_subscription(
        "Erin", _fake_sub("https://push.example.com/phone"), label="New label"
    )
    subs = push_service.get_subscriptions("Erin")
    assert len(subs) == 1
    assert subs[0]["label"] == "New label"


def test_validate_push_endpoint_rejects_private_ip(brain, monkeypatch):
    monkeypatch.setattr(
        push_service.socket,
        "getaddrinfo",
        lambda *a, **k: [(None, None, None, None, ("10.0.0.5", 0))],
    )
    with pytest.raises(ValueError, match="non-public"):
        push_service.save_subscription("Quinn", _fake_sub("https://internal.example.com/hook"))
    assert push_service.get_subscriptions("Quinn") == []


def test_validate_push_endpoint_rejects_loopback(brain, monkeypatch):
    monkeypatch.setattr(
        push_service.socket,
        "getaddrinfo",
        lambda *a, **k: [(None, None, None, None, ("127.0.0.1", 0))],
    )
    with pytest.raises(ValueError):
        push_service.save_subscription("Quinn", _fake_sub("https://internal.example.com/hook"))


def test_validate_push_endpoint_rejects_cloud_metadata_address(brain, monkeypatch):
    monkeypatch.setattr(
        push_service.socket,
        "getaddrinfo",
        lambda *a, **k: [(None, None, None, None, ("169.254.169.254", 0))],
    )
    with pytest.raises(ValueError):
        push_service.save_subscription("Quinn", _fake_sub("https://metadata.example.com/hook"))


def test_validate_push_endpoint_rejects_non_https_scheme(brain):
    with pytest.raises(ValueError, match="https"):
        push_service.save_subscription("Quinn", _fake_sub("http://push.example.com/insecure"))


def test_validate_push_endpoint_rejects_unresolvable_hostname(brain, monkeypatch):
    def fake_getaddrinfo(*a, **k):
        raise push_service.socket.gaierror("simulated DNS failure")

    monkeypatch.setattr(push_service.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(ValueError, match="resolved"):
        push_service.save_subscription("Quinn", _fake_sub("https://nowhere.example.invalid/hook"))


def test_validate_push_endpoint_accepts_public_address(brain):
    # Relies on the autouse _fake_dns fixture's public IP — must not raise.
    push_service.save_subscription("Quinn", _fake_sub("https://push.example.com/real"))
    assert len(push_service.get_subscriptions("Quinn")) == 1


def test_save_subscription_enforces_device_cap(brain):
    for i in range(push_service._MAX_DEVICES_PER_USER):
        push_service.save_subscription("Rex", _fake_sub(f"https://push.example.com/device-{i}"))
    with pytest.raises(ValueError, match="Maximum"):
        push_service.save_subscription("Rex", _fake_sub("https://push.example.com/one-too-many"))
    assert len(push_service.get_subscriptions("Rex")) == push_service._MAX_DEVICES_PER_USER


def test_device_cap_does_not_block_resubscribing_an_already_registered_device(brain):
    for i in range(push_service._MAX_DEVICES_PER_USER):
        push_service.save_subscription("Sam", _fake_sub(f"https://push.example.com/device-{i}"))
    # Re-subscribing device-0 (already counted, same endpoint) must not be
    # blocked by the cap even while already at the limit.
    push_service.save_subscription(
        "Sam", _fake_sub("https://push.example.com/device-0"), label="Renamed"
    )
    assert len(push_service.get_subscriptions("Sam")) == push_service._MAX_DEVICES_PER_USER


def test_delete_subscription_by_endpoint_removes_only_that_device(brain):
    push_service.save_subscription(
        "Frank", _fake_sub("https://push.example.com/phone"), label="Phone"
    )
    push_service.save_subscription(
        "Frank", _fake_sub("https://push.example.com/laptop"), label="Laptop"
    )
    push_service.delete_subscription("Frank", endpoint="https://push.example.com/phone")
    subs = push_service.get_subscriptions("Frank")
    assert len(subs) == 1
    assert subs[0]["endpoint"] == "https://push.example.com/laptop"


def test_get_subscriptions_reads_legacy_single_object_format(brain):
    """Every push_subscription.json written before 2026-08-30's multi-device
    support is a bare single object, not a list — must keep reading correctly
    with no explicit migration."""
    legacy = _fake_sub("https://web.push.apple.com/legacy-real-file")
    push_service.write_json(push_service._SUB_PATH("Grace"), legacy)  # bare dict, old format
    subs = push_service.get_subscriptions("Grace")
    assert len(subs) == 1
    assert subs[0]["endpoint"] == "https://web.push.apple.com/legacy-real-file"


def test_list_devices_returns_safe_metadata_only(brain):
    push_service.save_subscription(
        "Henry", _fake_sub("https://push.example.com/phone"), label="iPhone · Safari"
    )
    devices = push_service.list_devices("Henry")
    assert len(devices) == 1
    d = devices[0]
    assert d["label"] == "iPhone · Safari"
    assert d["created_at"]
    assert "endpoint" not in d
    assert "keys" not in d
    assert set(d.keys()) == {"id", "label", "created_at"}


def test_delete_device_by_id_removes_that_device_regardless_of_caller(brain):
    push_service.save_subscription(
        "Ivy", _fake_sub("https://push.example.com/old-phone"), label="Old phone"
    )
    push_service.save_subscription(
        "Ivy", _fake_sub("https://push.example.com/laptop"), label="Laptop"
    )
    devices = push_service.list_devices("Ivy")
    old_phone_id = next(d["id"] for d in devices if d["label"] == "Old phone")

    assert push_service.delete_device("Ivy", old_phone_id) is True

    remaining = push_service.list_devices("Ivy")
    assert len(remaining) == 1
    assert remaining[0]["label"] == "Laptop"


def test_delete_device_returns_false_for_unknown_id(brain):
    assert push_service.delete_device("NoSuchUser", "0123456789abcdef") is False


def test_rename_device_overwrites_label_only(brain):
    push_service.save_subscription(
        "Noah", _fake_sub("https://push.example.com/phone"), label="Unknown device"
    )
    device_id = push_service.list_devices("Noah")[0]["id"]

    assert push_service.rename_device("Noah", device_id, "Noah's iPhone") is True

    devices = push_service.list_devices("Noah")
    assert len(devices) == 1
    assert devices[0]["label"] == "Noah's iPhone"
    assert devices[0]["id"] == device_id  # same device, endpoint unchanged


def test_rename_device_preserves_created_at(brain):
    push_service.save_subscription(
        "Olive", _fake_sub("https://push.example.com/phone"), label="Phone"
    )
    original_created_at = push_service.list_devices("Olive")[0]["created_at"]

    push_service.rename_device("Olive", push_service.list_devices("Olive")[0]["id"], "Olive's iPad")

    assert push_service.list_devices("Olive")[0]["created_at"] == original_created_at


def test_rename_device_returns_false_for_unknown_id(brain):
    assert push_service.rename_device("NoSuchUser", "0123456789abcdef", "New Name") is False


def test_rename_device_does_not_affect_other_devices(brain):
    push_service.save_subscription(
        "Piper", _fake_sub("https://push.example.com/phone"), label="Phone"
    )
    push_service.save_subscription(
        "Piper", _fake_sub("https://push.example.com/laptop"), label="Laptop"
    )
    phone_id = next(d["id"] for d in push_service.list_devices("Piper") if d["label"] == "Phone")

    push_service.rename_device("Piper", phone_id, "Renamed Phone")

    labels = {d["label"] for d in push_service.list_devices("Piper")}
    assert labels == {"Renamed Phone", "Laptop"}


def test_send_push_delivers_to_every_device_independently(brain, monkeypatch):
    push_service.save_subscription(
        "Jack", _fake_sub("https://push.example.com/device-a"), label="A"
    )
    push_service.save_subscription(
        "Jack", _fake_sub("https://push.example.com/device-b"), label="B"
    )

    called_urls = []

    def fake_urlopen(req, timeout=10):
        called_urls.append(req.full_url)
        return _FakeResponse(201)

    monkeypatch.setattr(push_service.urllib.request, "urlopen", fake_urlopen)
    assert push_service.send_push("Jack", "Title", "Body") is True
    assert set(called_urls) == {
        "https://push.example.com/device-a",
        "https://push.example.com/device-b",
    }


def test_send_push_one_device_failing_does_not_block_the_others(brain, monkeypatch):
    push_service.save_subscription(
        "Kim", _fake_sub("https://push.example.com/broken"), label="Broken"
    )
    push_service.save_subscription(
        "Kim", _fake_sub("https://push.example.com/working"), label="Working"
    )

    def fake_urlopen(req, timeout=10):
        if "broken" in req.full_url:
            raise ConnectionError("simulated network failure")
        return _FakeResponse(201)

    monkeypatch.setattr(push_service.urllib.request, "urlopen", fake_urlopen)
    assert push_service.send_push("Kim", "Title", "Body") is True
    # Neither subscription is pruned on a generic failure — only a 410 does that.
    assert len(push_service.get_subscriptions("Kim")) == 2


def test_send_push_prunes_only_the_expired_devices_subscription(brain, monkeypatch):
    push_service.save_subscription("Liam", _fake_sub("https://push.example.com/gone"), label="Gone")
    push_service.save_subscription("Liam", _fake_sub("https://push.example.com/good"), label="Good")

    def fake_urlopen(req, timeout=10):
        if "gone" in req.full_url:
            raise _FakeHTTPError(410)
        return _FakeResponse(201)

    monkeypatch.setattr(push_service.urllib.request, "urlopen", fake_urlopen)
    assert push_service.send_push("Liam", "Title", "Body") is True

    remaining = push_service.get_subscriptions("Liam")
    assert len(remaining) == 1
    assert remaining[0]["endpoint"] == "https://push.example.com/good"


def test_send_push_returns_false_only_when_every_device_fails(brain, monkeypatch):
    push_service.save_subscription("Mia", _fake_sub("https://push.example.com/a"), label="A")
    push_service.save_subscription("Mia", _fake_sub("https://push.example.com/b"), label="B")

    def fake_urlopen(req, timeout=10):
        raise ConnectionError("simulated network failure")

    monkeypatch.setattr(push_service.urllib.request, "urlopen", fake_urlopen)
    assert push_service.send_push("Mia", "Title", "Body") is False
