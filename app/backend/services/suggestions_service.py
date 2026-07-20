"""Proactive suggestions — per-user config, notification inbox, and suggestion dispatch."""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from config import settings
from services.auth_service import (
    get_user_by_id,
    get_user_by_name,
    list_users,
    today_for_user,
    update_user,
)
from services.file_service import history_path, read_json, tasks_path, user_path, write_json

logger = logging.getLogger("logcore.suggestions")

_NOTIF_CAP = 50

_BUILTIN_DEFAULTS: dict[str, dict] = {
    "daily_digest": {
        "enabled": True,
        "hour": None,  # None → settings.morning_digest_hour
        "delivery": ["push"],
    },
    "overdue_alert": {
        "enabled": True,
        "hour": None,  # None → settings.overdue_check_hour
        "delivery": ["push"],
    },
    "weekly_review": {
        "enabled": True,
        "delivery": ["push"],
    },
    "goal_drift": {
        "enabled": True,
        "days_threshold": 14,
        "delivery": ["push", "in_app"],
    },
}


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def _suggestions_path(user_name: str):
    return user_path(user_name) / "suggestions.json"


def _notifications_path(user_name: str):
    return user_path(user_name) / "notifications.json"


def _ntfy_channel(user_name: str) -> str:
    user = get_user_by_name(user_name)
    if user and user.get("notification_channel"):
        return user["notification_channel"]
    return f"logcore-{user_name.lower().replace(' ', '-')}"


# ---------------------------------------------------------------------------
# Config CRUD
# ---------------------------------------------------------------------------


def get_config(user_name: str) -> dict:
    """Get per-user suggestion config merged with defaults."""
    data = read_json(_suggestions_path(user_name), default={})
    result: dict[str, Any] = {}
    for key, defaults in _BUILTIN_DEFAULTS.items():
        result[key] = {**defaults, **data.get(key, {})}
    result["custom"] = data.get("custom", [])
    return result


def update_config(user_name: str, suggestion_id: str, updates: dict) -> dict:
    """Patch fields on one suggestion (builtin or custom by ID)."""
    data = read_json(_suggestions_path(user_name), default={})
    if suggestion_id in _BUILTIN_DEFAULTS:
        current = {**_BUILTIN_DEFAULTS[suggestion_id], **data.get(suggestion_id, {})}
        current.update(updates)
        data[suggestion_id] = current
    else:
        customs = data.get("custom", [])
        for c in customs:
            if c["id"] == suggestion_id:
                c.update(updates)
                break
        data["custom"] = customs
    write_json(_suggestions_path(user_name), data)
    return get_config(user_name)


def create_custom(user_name: str, suggestion_data: dict) -> dict:
    """Add a new custom suggestion and return it."""
    path = _suggestions_path(user_name)
    data = read_json(path, default={})
    customs = data.get("custom", [])
    new_s = {
        "id": str(uuid.uuid4()),
        "name": suggestion_data["name"],
        "prompt": suggestion_data["prompt"],
        "schedule": suggestion_data.get("schedule", "daily"),
        "interval_days": suggestion_data.get("interval_days"),
        "day_of_week": suggestion_data.get("day_of_week"),
        "hour": suggestion_data["hour"],
        "delivery": suggestion_data.get("delivery", ["in_app"]),
        "enabled": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    customs.append(new_s)
    data["custom"] = customs
    write_json(path, data)
    return new_s


def delete_custom(user_name: str, suggestion_id: str) -> bool:
    """Remove a custom suggestion; returns True if found and deleted."""
    path = _suggestions_path(user_name)
    data = read_json(path, default={})
    customs = data.get("custom", [])
    filtered = [c for c in customs if c["id"] != suggestion_id]
    if len(filtered) == len(customs):
        return False
    data["custom"] = filtered
    write_json(path, data)
    return True


# ---------------------------------------------------------------------------
# Notification inbox
# ---------------------------------------------------------------------------


def get_notifications(user_name: str, limit: int = 20, delivery: str | None = None) -> list:
    data = read_json(_notifications_path(user_name), default={"notifications": []})
    notifs = data.get("notifications", [])
    if delivery:
        notifs = [n for n in notifs if n.get("delivery") == delivery]
    return list(reversed(notifs))[:limit]


def add_notification(
    user_name: str,
    title: str,
    body: str,
    source: str,
    delivery: str,
    action: dict | None = None,
) -> dict:
    path = _notifications_path(user_name)
    data = read_json(path, default={"notifications": []})
    notif = {
        "id": str(uuid.uuid4()),
        "title": title,
        "body": body,
        "source": source,
        "delivery": delivery,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "read": False,
    }
    if action is not None:
        # Actionable notification (accept/decline handshake). status: pending → resolved.
        notif["action"] = action
        notif["status"] = "pending"
    data["notifications"].append(notif)
    data["notifications"] = data["notifications"][-_NOTIF_CAP:]
    write_json(path, data)
    return notif


def resolve_notification(user_name: str, notif_id: str) -> dict | None:
    """Mark an actionable notification resolved (+read) and return its record so the
    caller can execute its action. Returns None if not found."""
    path = _notifications_path(user_name)
    data = read_json(path, default={"notifications": []})
    for n in data["notifications"]:
        if n["id"] == notif_id:
            n["status"] = "resolved"
            n["read"] = True
            write_json(path, data)
            return n
    return None


def mark_read(user_name: str, notif_id: str) -> bool:
    path = _notifications_path(user_name)
    data = read_json(path, default={"notifications": []})
    for n in data["notifications"]:
        if n["id"] == notif_id:
            n["read"] = True
            write_json(path, data)
            return True
    return False


def clear_notifications(user_name: str) -> None:
    path = _notifications_path(user_name)
    data = read_json(path, default={"notifications": []})
    for n in data["notifications"]:
        n["read"] = True
    write_json(path, data)


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


def _deliver(
    user_name: str, title: str, body: str, source: str, delivery: list, url: str = "/"
) -> None:
    """Send via all configured delivery channels."""
    from services.notification_service import send
    from services.push_service import get_subscription, send_push

    if "push" in delivery:
        send(channel=_ntfy_channel(user_name), title=title, message=body, priority="default")
        if get_subscription(user_name):
            send_push(user_name, title, body, url=url)
    if "in_app" in delivery:
        add_notification(user_name, title, body, source, "in_app")
    if "chat" in delivery:
        add_notification(user_name, title, body, source, "chat")


def notify_user(
    user_name: str,
    title: str,
    body: str,
    source: str = "system",
    action: dict | None = None,
    url: str = "/",
) -> None:
    """In-app notification (optionally actionable) + push channels, best-effort.
    Unlike _deliver, the in-app entry can carry an `action` (e.g. open_asset) and
    the web push carries a deep-link `url`."""
    add_notification(user_name, title, body, source, "in_app", action=action)
    try:
        from services.notification_service import send
        from services.push_service import get_subscription, send_push

        send(channel=_ntfy_channel(user_name), title=title, message=body, priority="default")
        if get_subscription(user_name):
            send_push(user_name, title, body, url=url)
    except Exception:  # push delivery must never break the write path
        pass


# ---------------------------------------------------------------------------
# Channel rotation reminders
# ---------------------------------------------------------------------------

ROTATION_REMINDER_DAYS = 30


def _parse_utc(raw: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def run_channel_rotation_reminders(now: datetime | None = None) -> int:
    """Nudge each user to rotate their ntfy channel ID once it is 30+ days old.

    The channel ID is the only lock on a user's notification stream, so rotation
    is the revocation mechanism. Fires monthly (channel_reminder_at dedup) until
    the user rotates; rotating stamps channel_rotated_at, which resets the clock.
    Users who never rotated are measured from created_at.
    """
    now = now or datetime.now(timezone.utc)
    window = timedelta(days=ROTATION_REMINDER_DAYS)
    sent = 0
    for entry in list_users():
        user = get_user_by_id(entry["id"])
        if not user:
            continue
        baseline = _parse_utc(user.get("channel_rotated_at") or user.get("created_at") or "")
        if baseline is None or now - baseline < window:
            continue
        reminded = _parse_utc(user.get("channel_reminder_at") or "")
        if reminded is not None and now - reminded < window:
            continue
        notify_user(
            user["name"],
            "Rotate your notification channel",
            "Your ntfy channel ID is over a month old. Rotate it in Settings → "
            "Notifications, then update the subscription in your ntfy app.",
            action={"type": "open_settings"},
            url="/settings",
        )
        update_user(user["id"], {"channel_reminder_at": now.isoformat()})
        sent += 1
    return sent


# ---------------------------------------------------------------------------
# Per-user suggestion runners (sync — safe for scheduler + run-now)
# ---------------------------------------------------------------------------


def _run_daily_digest(user_name: str, cfg: dict, workspace: str = "personal") -> dict:
    from services.priority_service import get_top3

    today = today_for_user(user_name)
    top3 = get_top3(user_name, workspace)
    if not top3:
        return {"ok": False, "reason": "no tasks"}
    date_str = f"{today.strftime('%A, %B')} {today.day}"
    lines = "\n".join(f"{i+1}. [{t['category']}] {t['title']}" for i, t in enumerate(top3))
    ws_label = f" [{workspace}]" if workspace != "personal" else ""
    title = f"Good morning, {user_name.split()[0]}!{ws_label} — {date_str}"
    body = f"Your top 3 today:\n\n{lines}"
    _deliver(user_name, title, body, "daily_digest", cfg.get("delivery", ["push"]), url="/tasks")
    return {"ok": True, "fired": "daily_digest"}


def _run_overdue_alert(user_name: str, cfg: dict, workspace: str = "personal") -> dict:
    today_iso = today_for_user(user_name).isoformat()
    data = read_json(tasks_path(user_name, workspace), default={"tasks": []})
    overdue = [
        t
        for t in data.get("tasks", [])
        if t.get("status") == "pending" and t.get("due_date") and t["due_date"] < today_iso
    ]
    if not overdue:
        return {"ok": False, "reason": "no overdue tasks"}
    lines = "\n".join(f"• [{t['category']}] {t['title']} (due {t['due_date']})" for t in overdue)
    ws_label = f" [{workspace}]" if workspace != "personal" else ""
    title = f"{len(overdue)} overdue task{'s' if len(overdue) > 1 else ''}{ws_label}"
    _deliver(user_name, title, lines, "overdue_alert", cfg.get("delivery", ["push"]), url="/tasks")
    return {"ok": True, "fired": "overdue_alert", "count": len(overdue)}


def _run_weekly_review(user_name: str, cfg: dict, workspace: str = "personal") -> dict:
    week_ago = (today_for_user(user_name) - timedelta(days=7)).isoformat()
    hpath = history_path(user_name, workspace)
    if not hpath.exists():
        return {"ok": False, "reason": "no history"}
    history = read_json(hpath, default={"tasks": []}).get("tasks", [])
    this_week = [t for t in history if (t.get("completed_at") or "") >= week_ago]
    if not this_week:
        return {"ok": False, "reason": "no completed tasks this week"}
    by_cat: dict[str, int] = {}
    for t in this_week:
        by_cat[t["category"]] = by_cat.get(t["category"], 0) + 1
    lines = "\n".join(
        f"• {cat}: {count} task{'s' if count > 1 else ''}"
        for cat, count in sorted(by_cat.items(), key=lambda x: -x[1])
    )
    ws_label = f" [{workspace}]" if workspace != "personal" else ""
    title = f"Weekly review{ws_label} — {len(this_week)} tasks completed"
    body = f"Great week, {user_name.split()[0]}!\n\n{lines}"
    _deliver(user_name, title, body, "weekly_review", cfg.get("delivery", ["push"]))
    return {"ok": True, "fired": "weekly_review", "count": len(this_week)}


def _run_goal_drift(user_name: str, cfg: dict, workspace: str = "personal") -> dict:
    days_threshold = cfg.get("days_threshold", 14)
    today = today_for_user(user_name)
    cutoff = (today - timedelta(days=days_threshold)).isoformat()
    data = read_json(tasks_path(user_name, workspace), default={"tasks": []})
    drifting = [
        t
        for t in data.get("tasks", [])
        if t.get("type") == "goal"
        and t.get("status") == "pending"
        and (
            (not t.get("last_completed_date") and (t.get("created_at") or "")[:10] <= cutoff)
            or (t.get("last_completed_date") and t["last_completed_date"] <= cutoff)
        )
    ]
    if not drifting:
        return {"ok": False, "reason": "no drifting goals"}
    names = ", ".join(t["title"] for t in drifting[:3])
    if len(drifting) > 3:
        names += f" and {len(drifting) - 3} more"
    ws_label = f" [{workspace}]" if workspace != "personal" else ""
    title = f"{len(drifting)} goal{'s' if len(drifting) > 1 else ''}{ws_label} need{'s' if len(drifting) == 1 else ''} attention"
    body = f"You haven't made progress on: {names}"
    _deliver(
        user_name, title, body, "goal_drift", cfg.get("delivery", ["push", "in_app"]), url="/tasks"
    )
    return {"ok": True, "fired": "goal_drift", "count": len(drifting)}


def _run_custom_sync(user_name: str, suggestion: dict) -> dict:
    """Run a custom AI-powered suggestion (sync wrapper — safe for scheduler threads)."""
    import asyncio

    try:
        return asyncio.run(_run_custom_async(user_name, suggestion))
    except Exception as e:
        logger.exception("custom suggestion %s failed for %s", suggestion.get("id"), user_name)
        return {"ok": False, "reason": str(e)}


async def _run_custom_async(user_name: str, suggestion: dict) -> dict:
    """Run a custom AI-powered suggestion (async — for API endpoints)."""
    from zoneinfo import ZoneInfo

    from services.ai_provider import chat_completion

    user = get_user_by_name(user_name)
    tz = user.get("timezone", "UTC") if user else "UTC"
    try:
        now_local = datetime.now(ZoneInfo(tz))
    except Exception:
        now_local = datetime.now(ZoneInfo("UTC"))
    today_str = now_local.strftime("%A, %B %d, %Y")
    system = (
        f"You are the AI layer of LogCore Brain for {user_name}. "
        f"Today is {today_str}. Be direct and concise. Max 3 paragraphs."
    )
    try:
        result = await chat_completion(system, [{"role": "user", "content": suggestion["prompt"]}])
    except Exception as e:
        return {"ok": False, "reason": str(e)}
    title = suggestion["name"]
    _deliver(
        user_name,
        title,
        result.strip(),
        f"custom:{suggestion['id']}",
        suggestion.get("delivery", ["in_app"]),
    )
    return {"ok": True, "fired": suggestion["id"]}


def run_suggestion_sync(user_name: str, suggestion_id: str, workspace: str = "personal") -> dict:
    """Dispatch and run a suggestion synchronously (scheduler / agent tool)."""
    cfg = get_config(user_name)
    if suggestion_id == "daily_digest":
        c = cfg["daily_digest"]
        if not c.get("enabled", True):
            return {"ok": False, "reason": "disabled"}
        return _run_daily_digest(user_name, c, workspace)
    if suggestion_id == "overdue_alert":
        c = cfg["overdue_alert"]
        if not c.get("enabled", True):
            return {"ok": False, "reason": "disabled"}
        return _run_overdue_alert(user_name, c, workspace)
    if suggestion_id == "weekly_review":
        c = cfg["weekly_review"]
        if not c.get("enabled", True):
            return {"ok": False, "reason": "disabled"}
        return _run_weekly_review(user_name, c, workspace)
    if suggestion_id == "goal_drift":
        c = cfg["goal_drift"]
        if not c.get("enabled", True):
            return {"ok": False, "reason": "disabled"}
        return _run_goal_drift(user_name, c, workspace)
    for c in cfg.get("custom", []):
        if c["id"] == suggestion_id:
            if not c.get("enabled", True):
                return {"ok": False, "reason": "disabled"}
            return _run_custom_sync(user_name, c)
    return {"error": f"Suggestion {suggestion_id!r} not found"}


async def run_suggestion_async(
    user_name: str, suggestion_id: str, workspace: str = "personal"
) -> dict:
    """Dispatch and run a suggestion asynchronously (API endpoints)."""
    cfg = get_config(user_name)
    if suggestion_id == "daily_digest":
        c = cfg["daily_digest"]
        if not c.get("enabled", True):
            return {"ok": False, "reason": "disabled"}
        return _run_daily_digest(user_name, c, workspace)
    if suggestion_id == "overdue_alert":
        c = cfg["overdue_alert"]
        if not c.get("enabled", True):
            return {"ok": False, "reason": "disabled"}
        return _run_overdue_alert(user_name, c, workspace)
    if suggestion_id == "weekly_review":
        c = cfg["weekly_review"]
        if not c.get("enabled", True):
            return {"ok": False, "reason": "disabled"}
        return _run_weekly_review(user_name, c, workspace)
    if suggestion_id == "goal_drift":
        c = cfg["goal_drift"]
        if not c.get("enabled", True):
            return {"ok": False, "reason": "disabled"}
        return _run_goal_drift(user_name, c, workspace)
    for c in cfg.get("custom", []):
        if c["id"] == suggestion_id:
            if not c.get("enabled", True):
                return {"ok": False, "reason": "disabled"}
            return await _run_custom_async(user_name, c)
    return {"error": f"Suggestion {suggestion_id!r} not found"}
