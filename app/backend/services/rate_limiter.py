"""Simple in-memory IP-based rate limiter — no external dependency needed."""
import time

from fastapi import HTTPException, Request

from config import settings

_hits: dict[str, list[float]] = {}
_sweep_n = 0


def _sweep(now: float) -> None:
    """Remove stale entries to prevent unbounded dict growth."""
    dead = [k for k, ts in list(_hits.items()) if not ts or now - ts[-1] >= 3600]
    for k in dead:
        _hits.pop(k, None)


def _client_ip(request: Request) -> str:
    """Return the real client IP.

    X-Forwarded-For is only trusted when TRUST_PROXY_HEADERS=true, preventing
    attackers from spoofing IPs to bypass rate limits when the app is exposed directly.
    """
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            candidate = forwarded.split(",")[0].strip()
            if candidate:
                return candidate
    return request.client.host if request.client else "unknown"


def rate_limit(max_calls: int, window_seconds: int):
    """Returns a FastAPI dependency that enforces max_calls per window per IP."""
    def dependency(request: Request) -> None:
        global _sweep_n
        ip = _client_ip(request)
        key = f"{request.url.path}:{ip}"
        now = time.monotonic()

        _sweep_n += 1
        if _sweep_n >= 5_000:
            _sweep_n = 0
            _sweep(now)

        recent = [t for t in _hits.get(key, []) if now - t < window_seconds]
        if len(recent) >= max_calls:
            raise HTTPException(
                status_code=429,
                detail="Too many requests — please wait before trying again.",
            )
        recent.append(now)
        _hits[key] = recent
    return dependency
