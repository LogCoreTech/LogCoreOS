"""Runtime hosting settings — reads from brain/hosting.json, falls back to env config."""

from config import settings
from services.file_service import brain_path, read_json

_HOSTING_PATH = brain_path() / "hosting.json"


def _stored() -> dict:
    return read_json(_HOSTING_PATH, default={})


def effective_cookie_secure() -> bool:
    stored = _stored()
    if "cookie_secure" in stored:
        return bool(stored["cookie_secure"])
    return settings.cookie_secure


def effective_trust_proxy_headers() -> bool:
    stored = _stored()
    if "trust_proxy_headers" in stored:
        return bool(stored["trust_proxy_headers"])
    return settings.trust_proxy_headers


def effective_domain_url() -> str:
    """Return the configured domain URL, or '' if in localhost mode."""
    return _stored().get("domain_url", "")
