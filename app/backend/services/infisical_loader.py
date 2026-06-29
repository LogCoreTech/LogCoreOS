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

logger = logging.getLogger("logcore.infisical")

# Module-level state — set by load_infisical_secrets(), read by status endpoints
_token_source: str | None = None   # "env" | "file" | None
_connected: bool = False
_last_fetched: str | None = None   # ISO-8601 UTC timestamp


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
    if cfg.exists():
        try:
            data = json.loads(cfg.read_text())
            t = data.get("token", "").strip()
            if t:
                return t, "file"
        except (json.JSONDecodeError, OSError):
            pass
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


def _write_cache(secrets: dict[str, str]) -> None:
    cache = _cache_file()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(), "secrets": secrets}, indent=2))


def _load_cache() -> dict[str, str] | None:
    cache = _cache_file()
    if not cache.exists():
        return None
    try:
        data = json.loads(cache.read_text())
        return data.get("secrets")
    except (json.JSONDecodeError, OSError):
        return None


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
        logger.warning("Infisical: loaded %d secret(s) from cache (Infisical was unreachable).", len(cached))


def get_status() -> dict:
    return {
        "configured": _token_source is not None,
        "source": _token_source,
        "connected": _connected,
        "last_fetched": _last_fetched,
    }


def save_token_to_file(token: str) -> None:
    """Write a token to the brain config file (used by Admin UI for rotation)."""
    cfg = _config_file()
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps({"token": token}, indent=2))


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
