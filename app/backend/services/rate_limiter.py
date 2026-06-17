"""Simple in-memory IP-based rate limiter — no external dependency needed."""
import time
from collections import defaultdict

from fastapi import HTTPException, Request

_hits: dict[str, list[float]] = defaultdict(list)


def _client_ip(request: Request) -> str:
    """Return the real client IP, honouring X-Forwarded-For behind a reverse proxy."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(max_calls: int, window_seconds: int):
    """Returns a FastAPI dependency that enforces max_calls per window per IP."""
    def dependency(request: Request) -> None:
        ip = _client_ip(request)
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
