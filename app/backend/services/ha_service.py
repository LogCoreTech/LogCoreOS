"""Home Assistant service — REST API client and Brain config management."""
import logging

import httpx

from services.file_service import brain_path, read_json, user_path, write_json

logger = logging.getLogger("logcore.ha")

_CONFIG_PATH = lambda: brain_path() / "_system" / "ha_config.json"
_FAVS_FILE = "favourites.json"


def get_config() -> dict:
    """Read HA config from Brain; fall back to env vars."""
    cfg = read_json(_CONFIG_PATH(), default={})
    from config import settings
    return {
        "url":   cfg.get("url")   or getattr(settings, "ha_url",   ""),
        "token": cfg.get("token") or getattr(settings, "ha_token", ""),
    }


def save_config(cfg: dict) -> None:
    write_json(_CONFIG_PATH(), cfg)


def is_configured() -> bool:
    cfg = get_config()
    return bool(cfg.get("url") and cfg.get("token"))


def _client() -> httpx.Client:
    cfg = get_config()
    return httpx.Client(
        base_url=cfg["url"].rstrip("/"),
        headers={"Authorization": f"Bearer {cfg['token']}"},
        timeout=10.0,
    )


def test_connection() -> dict:
    """Test HA connectivity. Returns {ok, url, error?}."""
    cfg = get_config()
    if not cfg["url"] or not cfg["token"]:
        return {"ok": False, "url": cfg.get("url", ""), "error": "HA URL and token are required."}
    try:
        with _client() as c:
            r = c.get("/api/")
            ok = r.status_code == 200 and "message" in r.json()
            return {"ok": ok, "url": cfg["url"]}
    except Exception as exc:
        return {"ok": False, "url": cfg.get("url", ""), "error": str(exc)}


def get_states(domain: str | None = None) -> list:
    """Return all entity states, optionally filtered by domain prefix."""
    with _client() as c:
        r = c.get("/api/states", timeout=15.0)
        r.raise_for_status()
        states = r.json()
    if domain:
        domains = {d.strip() for d in domain.split(",") if d.strip()}
        states = [s for s in states if s.get("entity_id", "").split(".")[0] in domains]
    return states


def get_state(entity_id: str) -> dict:
    """Return a single entity's state and attributes."""
    with _client() as c:
        r = c.get(f"/api/states/{entity_id}")
        r.raise_for_status()
        return r.json()


def call_service(domain: str, service: str, data: dict) -> dict:
    """Call a HA service (turn_on, turn_off, set_temperature, etc.)."""
    with _client() as c:
        r = c.post(f"/api/services/{domain}/{service}", json=data, timeout=15.0)
        r.raise_for_status()
        return {"ok": True, "result": r.json() if r.content else []}


def get_scenes() -> list:
    """Return all scene entities."""
    states = get_states("scene")
    return states


def get_automations() -> list:
    """Return all automation entities."""
    return get_states("automation")


def trigger_automation(entity_id: str) -> dict:
    """Trigger a HA automation."""
    return call_service("automation", "trigger", {"entity_id": entity_id})


def get_areas() -> list:
    """Return area list via HA template endpoint."""
    try:
        with _client() as c:
            r = c.post("/api/template", json={"template": "{{ areas() | list }}"})
            if r.status_code == 200:
                import json as _json
                raw = r.text.strip()
                return _json.loads(raw) if raw.startswith("[") else []
    except Exception:
        pass
    return []


def get_favourites(user_name: str) -> list:
    p = user_path(user_name) / "Home" / _FAVS_FILE
    data = read_json(p, default={})
    return data.get("entity_ids", [])


def save_favourites(user_name: str, entity_ids: list) -> None:
    p = user_path(user_name) / "Home" / _FAVS_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    write_json(p, {"entity_ids": entity_ids})
