"""update_service.py — version check, update trigger, and log access."""

import json
import logging
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from config import settings
from services.file_service import read_json, write_json

logger = logging.getLogger("logcore.update")

# Set to "" to disable GitHub update checks (e.g. self-hosted forks on private repos)
GITHUB_REPO = "logcoretech/logcoreOS"
CACHE_TTL = 4 * 3600  # seconds


def _sys() -> Path:
    return settings.brain_path / "_system"


def get_installed_version() -> str:
    """Read version written by launch.sh or update.sh at install/update time."""
    try:
        return read_json(_sys() / "installed_version.json").get("version", "0.1.0")
    except Exception:
        return "0.1.0"


def check_latest_version() -> dict:
    """Fetch latest GitHub release. Caches result for CACHE_TTL seconds."""
    cache_path = _sys() / "update_cache.json"
    try:
        cached = read_json(cache_path)
        if time.time() - cached.get("cached_at", 0) < CACHE_TTL:
            return cached
    except Exception:
        pass

    if not GITHUB_REPO:
        result = {
            "latest_version": None,
            "release_url": None,
            "cached_at": time.time(),
            "error": None,
        }
        return result

    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "LogCoreOS/1.0", "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        tag = data.get("tag_name", "")
        result = {
            "latest_version": tag.lstrip("v"),
            "release_url": data.get("html_url", ""),
            "release_name": data.get("name", tag),
            "cached_at": time.time(),
            "error": None,
        }
    except Exception as exc:
        result = {
            "latest_version": None,
            "release_url": None,
            "release_name": None,
            "cached_at": time.time(),
            "error": str(exc),
        }

    try:
        write_json(cache_path, result)
    except Exception:
        pass
    return result


def _version_gt(a: str, b: str) -> bool:
    """Return True if semver string a is strictly greater than b."""

    def _t(v: str) -> tuple:
        try:
            return tuple(int(x) for x in v.strip().split("."))
        except Exception:
            return (0,)

    return _t(a) > _t(b)


HEARTBEAT_STALE_SECONDS = 150  # cron runs every 60s; stale after 2.5x that


def daemon_is_active() -> bool:
    """Return True if update.sh wrote a heartbeat within the last 150 seconds."""
    try:
        hb = read_json(_sys() / "update_heartbeat.json")
        return time.time() - hb.get("last_seen", 0) < HEARTBEAT_STALE_SECONDS
    except Exception:
        return False


def get_auto_update_enabled() -> bool:
    """Read the admin-controlled auto-update toggle (default True)."""
    try:
        return bool(read_json(_sys() / "update_settings.json").get("auto_update", True))
    except Exception:
        return True


def set_auto_update_enabled(enabled: bool) -> None:
    write_json(_sys() / "update_settings.json", {"auto_update": enabled})


def get_update_status() -> dict:
    installed = get_installed_version()
    info = check_latest_version()
    latest = info.get("latest_version")
    update_available = bool(latest and _version_gt(latest, installed))

    last_update: dict = {}
    try:
        last_update = read_json(_sys() / "update_status.json")
    except Exception:
        pass

    return {
        "current_version": installed,
        "latest_version": latest,
        "update_available": update_available,
        "release_url": info.get("release_url"),
        "release_name": info.get("release_name"),
        "last_checked": info.get("cached_at"),
        "check_error": info.get("error"),
        "update_pending": (_sys() / "pending_update").exists(),
        "update_running": (_sys() / "update_running").exists(),
        "last_update": last_update,
        "daemon_active": daemon_is_active(),
        "auto_update_enabled": get_auto_update_enabled(),
    }


def trigger_update() -> dict:
    """Write the pending_update flag. The host-side update.sh --watch picks this up."""
    flag = _sys() / "pending_update"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text(datetime.now(timezone.utc).isoformat())
    logger.info("update triggered via Admin UI")
    return {"triggered": True}


def get_update_log(lines: int = 100) -> list[str]:
    """Return the last N lines from the host-written update log."""
    try:
        content = (_sys() / "update.log").read_text()
        return content.splitlines()[-lines:]
    except Exception:
        return []


def refresh_version_cache() -> None:
    """Force-refresh the GitHub version cache. Called by the daily scheduler job."""
    try:
        cache_path = _sys() / "update_cache.json"
        # Expire the cache so check_latest_version fetches fresh data
        try:
            cached = read_json(cache_path)
            cached["cached_at"] = 0
            write_json(cache_path, cached)
        except Exception:
            pass
        check_latest_version()
    except Exception:
        logger.exception("version cache refresh failed")
