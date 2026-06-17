"""Simple in-memory IP-based rate limiter — no external dependency needed."""
import time
from collections import defaultdict

from fastapi import HTTPException, Request

_hits: dict[str, list[float]] = defaultdict(list)


def rate_limit(max_calls: int, window_seconds: int):
    """Returns a FastAPI dependency that enforces max_calls per window per IP."""
    def dependency(request: Request) -> None:
        ip = request.client.host if request.client else "unknown"
        key = f"{request.url.path}:{ip}"
        now = time.monotonic()
        recent = [t for t in _hits[key] if now - t < window_seconds]
        if len(recent) >= max_calls:
            raise HTTPException(
                status_code=429,
                detail="Too many requests — please wait before trying again.",
            )
        recent.append(now)
        _hits[key] = recent
    return dependency
