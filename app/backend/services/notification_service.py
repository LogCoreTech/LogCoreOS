"""Push notifications via ntfy (self-hosted)."""

import httpx

from config import settings


def send(channel: str, title: str, message: str, priority: str = "default") -> bool:
    try:
        url = f"{settings.ntfy_url}/{channel}"
        headers = {
            "Title": title,
            "Priority": priority,
            "Content-Type": "text/plain",
        }
        # Once ntfy's default access is hardened to read-only (launch.sh
        # provisions this after creating the admin publisher account), publishing
        # requires this bearer token. Anonymous subscribing is unaffected —
        # only the ability to publish is gated.
        if settings.ntfy_publish_token:
            headers["Authorization"] = f"Bearer {settings.ntfy_publish_token}"
        httpx.post(url, content=message, headers=headers, timeout=5)
        return True
    except Exception:
        return False
