"""Push notifications via ntfy (self-hosted)."""
import httpx
from config import settings


def send(channel: str, title: str, message: str, priority: str = "default") -> bool:
    try:
        url = f"{settings.ntfy_url}/{channel}"
        httpx.post(url, content=message, headers={
            "Title": title,
            "Priority": priority,
            "Content-Type": "text/plain",
        }, timeout=5)
        return True
    except Exception:
        return False
