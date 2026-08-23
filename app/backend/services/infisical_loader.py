"""
Infisical secret loader — must be imported and called before config.Settings() is instantiated.

When INFISICAL_TOKEN (or a saved token file) is present, this module fetches secrets from
the configured Infisical server and injects them into os.environ so that Pydantic's
BaseSettings reads them transparently. Self-hosted instances with no token are unaffected.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("logcore.infisical")

# Module-level state — set by load_infisical_secrets(), read by status endpoints
_token_source: str | None = None  # "env" | "file" | None
_connected: bool = False
_last_fetched: str | None = None  # ISO-8601 UTC timestamp


def _brain_path() -> Path:
    return Path(os.environ.get("BRAIN_PATH", "/data/brain"))


def _system_path() -> Path:
    return _brain_path() / "_system"


def _config_file() -> Path:
    return _system_path() / "infisical_config.json"


def _cache_file() -> Path:
    return _system_path() / "infisical_cache.json"


def _resolve_token() -> tuple[str | None, str | None]:
    """Returns (token, source) where source is 'env', 'file', or None."""
    token = os.environ.get("INFISICAL_TOKEN", "").strip()
    if token:
        return token, "env"
    cfg = _config_file()
    data, was_plaintext = _read_encrypted_json(cfg)
    if data is not None:
        if was_plaintext and _cipher() is not None:
            _write_encrypted_json(cfg, data)
        t = (data.get("token") or "").strip()
        if t:
            return t, "file"
    return None, None


def _fetch_secrets(token: str) -> dict[str, str]:
    """Fetch secrets from Infisical server. Returns {key: value} dict."""
    base_url = os.environ.get("INFISICAL_URL", "").rstrip("/")
    if not base_url:
        raise ValueError("INFISICAL_URL is required when INFISICAL_TOKEN is set")

    env = os.environ.get("INFISICAL_ENV", "prod")
    project_id = os.environ.get("INFISICAL_PROJECT_ID", "")

    params: dict = {"environment": env, "include_imports": "true"}
    if project_id:
        params["workspaceId"] = project_id

    with httpx.Client(timeout=15.0) as client:
        resp = client.get(
            f"{base_url}/api/v3/secrets/raw",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )
        resp.raise_for_status()

    data = resp.json()
    secrets = data.get("secrets", [])
    return {s["secretKey"]: s["secretValue"] for s in secrets if "secretKey" in s}


def _cipher() -> Fernet | None:
    """The Fernet cipher for encrypting infisical_cache.json/infisical_config.json
    at rest, or None if INFISICAL_CACHE_KEY isn't configured (or is invalid) — in
    which case callers fall back to plaintext rather than failing startup. The
    key deliberately lives in docker/.env, not brain/_system/: this whole
    directory is swept into one tarball by backup.sh, so a key stored next to
    its own ciphertext would defeat the point. See docs/MEMORY.md."""
    key = os.environ.get("INFISICAL_CACHE_KEY", "").strip()
    if not key:
        return None
    try:
        return Fernet(key.encode())
    except Exception:
        logger.warning("INFISICAL_CACHE_KEY is set but invalid — storing/reading as plaintext.")
        return None


def _read_encrypted_json(path: Path) -> tuple[dict | None, bool]:
    """Returns (data, was_legacy_plaintext). (None, False) if missing/corrupt."""
    if not path.exists():
        return None, False
    raw = path.read_bytes()
    cipher = _cipher()
    if cipher:
        try:
            return json.loads(cipher.decrypt(raw)), False
        except InvalidToken:
            pass  # legacy plaintext on disk, or the key changed — try as plaintext
        except json.JSONDecodeError:
            return None, False
    try:
        return json.loads(raw), True
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None, False


def _write_encrypted_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2).encode()
    cipher = _cipher()
    path.write_bytes(cipher.encrypt(payload) if cipher else payload)


def _write_cache(secrets: dict[str, str]) -> None:
    _write_encrypted_json(
        _cache_file(),
        {"fetched_at": datetime.now(timezone.utc).isoformat(), "secrets": secrets},
    )


def _load_cache() -> dict[str, str] | None:
    data, was_plaintext = _read_encrypted_json(_cache_file())
    if data is None:
        return None
    if was_plaintext and _cipher() is not None:
        # A key is now configured but this file predates it — migrate in place
        # so it's encrypted on disk from the next read onward.
        _write_encrypted_json(_cache_file(), data)
    return data.get("secrets")


def read_cache() -> dict:
    """Public reader for other modules (e.g. n8n_service, the automations
    router) that need the raw cached-secrets envelope — never read
    infisical_cache.json directly, it may be encrypted."""
    data, was_plaintext = _read_encrypted_json(_cache_file())
    if data is None:
        return {}
    if was_plaintext and _cipher() is not None:
        _write_encrypted_json(_cache_file(), data)
    return data


def load_infisical_secrets() -> None:
    """
    Entry point — call this before importing config.Settings().
    Resolves token, fetches from Infisical (or cache on failure), injects into os.environ.
    No-op when no token is configured (self-hosted mode).
    """
    global _token_source, _connected, _last_fetched

    token, source = _resolve_token()
    if not token:
        logger.debug("No Infisical token configured — running in self-hosted mode.")
        return

    _token_source = source
    logger.info("Infisical token found (source: %s) — fetching secrets...", source)
    if _cipher() is None:
        logger.warning(
            "INFISICAL_CACHE_KEY is not set — the Infisical secrets cache and token "
            "file will be stored in plaintext until it's configured. See docker/.env.example."
        )

    try:
        secrets = _fetch_secrets(token)
        _write_cache(secrets)
        for key, value in secrets.items():
            os.environ[key] = value
        _connected = True
        _last_fetched = datetime.now(timezone.utc).isoformat()
        logger.info("Infisical: loaded %d secret(s) into environment.", len(secrets))
        # Write secrets to n8n.env so the n8n container can reference them as {{ $env.VAR }}
        try:
            from services.n8n_service import write_n8n_env

            write_n8n_env(secrets)
        except Exception as _n8n_exc:
            logger.warning("Could not write n8n.env: %s", _n8n_exc)
    except Exception as exc:
        logger.warning("Infisical unreachable: %s — attempting local cache...", exc)
        cached = _load_cache()
        if cached is None:
            logger.critical(
                "Infisical is unreachable and no local cache exists. "
                "Cannot start without secrets. Fix INFISICAL_URL / token or remove INFISICAL_TOKEN to run locally."
            )
            sys.exit(1)
        for key, value in cached.items():
            os.environ[key] = value
        _connected = False
        logger.warning(
            "Infisical: loaded %d secret(s) from cache (Infisical was unreachable).", len(cached)
        )


def get_status() -> dict:
    return {
        "configured": _token_source is not None,
        "source": _token_source,
        "connected": _connected,
        "last_fetched": _last_fetched,
    }


def save_token_to_file(token: str) -> None:
    """Write a token to the brain config file (used by Admin UI for rotation)."""
    _write_encrypted_json(_config_file(), {"token": token})


def clear_token_file() -> None:
    """Remove the file-sourced token. Env-var tokens cannot be cleared here."""
    cfg = _config_file()
    if cfg.exists():
        cfg.unlink()


def validate_token(token: str) -> bool:
    """Test connectivity for a given token without modifying any state."""
    original = os.environ.get("INFISICAL_TOKEN")
    os.environ["INFISICAL_TOKEN"] = token
    try:
        _fetch_secrets(token)
        return True
    except Exception:
        return False
    finally:
        if original is None:
            os.environ.pop("INFISICAL_TOKEN", None)
        else:
            os.environ["INFISICAL_TOKEN"] = original
