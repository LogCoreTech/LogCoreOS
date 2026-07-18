"""whats_new_service.py — announce an app update to every user once, and drive the
few-day What's-New banner.

On boot we compare the running version (written by launch.sh/update.sh) against the
last version we announced. When it goes up and the authored `whats_new` list has a
matching entry, we drop a one-time note into every user's inbox and open a banner
window. Fresh installs set a silent baseline (no "you updated" spam on first run).
"""

import logging
from datetime import datetime, timedelta, timezone

from config import settings
from services import help_service, update_service
from services.file_service import read_json, write_json

logger = logging.getLogger("logcore.whats_new")


def _state_path():
    return settings.brain_path / "_system" / "whats_new_state.json"


def _matching_entry(version: str) -> dict | None:
    for entry in help_service.get_content().get("whats_new", []):
        if entry.get("version") == version:
            return entry
    return None


def announce_if_updated() -> dict:
    """Notify every user once when the running version is newer than the last announced.

    Returns a small summary dict (for logging/tests): {announced, version, notified}.
    Never raises — notification failures must not break startup.
    """
    try:
        running = update_service.get_installed_version()
        state = read_json(_state_path(), default={})
        announced = state.get("announced_version")

        # First run with this feature (or fresh install): set a silent baseline so we
        # don't announce the version the user is already on.
        if not announced:
            write_json(_state_path(), {"announced_version": running, "announced_at": None})
            return {"announced": False, "version": running, "notified": 0, "reason": "baseline"}

        if not update_service._version_gt(running, announced):
            return {"announced": False, "version": running, "notified": 0, "reason": "not-newer"}

        entry = _matching_entry(running)
        if entry is None:
            # Version moved but we have no authored highlights for it — don't announce
            # stale notes. Leave the baseline so it fires once the entry is added.
            return {"announced": False, "version": running, "notified": 0, "reason": "no-entry"}

        highlights = entry.get("highlights", [])
        body = highlights[0] if highlights else "See what's new in this update."
        if len(highlights) > 1:
            body += f" (+{len(highlights) - 1} more)"

        from services import auth_service
        from services.suggestions_service import notify_user

        notified = 0
        for u in auth_service.list_users():
            name = u.get("name")
            if not name:
                continue
            try:
                notify_user(
                    name,
                    f"🎉 LogCore updated to v{running}",
                    body,
                    source="system",
                    url="/help#whats-new",
                )
                notified += 1
            except Exception:
                logger.exception("whats-new notify failed for %s", name)

        write_json(
            _state_path(),
            {
                "announced_version": running,
                "announced_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        logger.info("announced v%s to %d users", running, notified)
        return {"announced": True, "version": running, "notified": notified}
    except Exception:
        logger.exception("whats-new announce failed")
        return {"announced": False, "version": None, "notified": 0, "reason": "error"}


def get_banner() -> dict:
    """Banner state for the current user's session. Empty `version` once the window
    has passed or nothing has been announced yet."""
    state = read_json(_state_path(), default={})
    announced_at = state.get("announced_at")
    version = state.get("announced_version")
    if not announced_at or not version:
        return {"version": None}
    try:
        started = datetime.fromisoformat(announced_at)
    except (TypeError, ValueError):
        return {"version": None}
    until = started + timedelta(days=settings.whats_new_days)
    if datetime.now(timezone.utc) >= until:
        return {"version": None}

    entry = _matching_entry(version) or {}
    return {
        "version": version,
        "until": until.isoformat(),
        "highlights": entry.get("highlights", []),
        "date": entry.get("date"),
    }
