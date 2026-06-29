import logging
from contextlib import asynccontextmanager
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Infisical must inject env vars before Settings() is instantiated at config import time
from services.infisical_loader import load_infisical_secrets
load_infisical_secrets()

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from config import settings
from migrations.runner import run_pending as run_migrations
from routers import auth, tasks, priorities, chat, setup, health, brain, export, shared, push, notes, journal, calendar, profile, suggestions, infisical, features, automations, home
from scheduler import start as start_scheduler
from services.hosting_service import effective_domain_url

logger = logging.getLogger("logcore")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _startup_checks()
    run_migrations()
    start_scheduler()
    yield


def _startup_checks() -> None:
    if settings.allowed_origins.strip() == "*":
        logger.warning(
            "CORS is set to allow all origins ('*'). "
            "This is only safe for development or LAN use. "
            "Set ALLOWED_ORIGINS to your domain in production."
        )

    if not settings.cookie_secure:
        logger.warning(
            "COOKIE_SECURE is False — auth cookies will be sent over plain HTTP. "
            "Only acceptable for local development. Set COOKIE_SECURE=true in production."
        )

    if settings.secret_key == "change-me-in-production":
        logger.critical(
            "\n"
            "╔══════════════════════════════════════════════════════╗\n"
            "║  SECURITY WARNING: SECRET_KEY is using the default   ║\n"
            "║  insecure value. Set SECRET_KEY in docker/.env        ║\n"
            "║  before exposing this server to any network.          ║\n"
            "╚══════════════════════════════════════════════════════╝"
        )

    bp = settings.brain_path
    if not bp.exists():
        logger.error(
            "Brain directory '%s' does not exist. "
            "Check your BRAIN_PATH env var and volume mount — the app will not work correctly.",
            bp,
        )
    else:
        template = bp / "USERS" / "_template"
        if not template.exists():
            logger.error(
                "Brain template missing at '%s'. "
                "The setup wizard will fail for new users. Restore from backup or re-clone the repo.",
                template,
            )
        system_files = ["AGENTS.md", "SOUL.md", "USERS.md"]
        for fname in system_files:
            if not (bp / fname).exists():
                logger.warning("Brain system file missing: '%s/%s'.", bp, fname)

    try:
        ZoneInfo(settings.scheduler_timezone)
    except (ZoneInfoNotFoundError, Exception):
        logger.error(
            "SCHEDULER_TIMEZONE '%s' is not a valid IANA timezone — "
            "the scheduler will fail to start. Check your .env file.",
            settings.scheduler_timezone,
        )


app = FastAPI(title="LogCore OS", version="0.1.0", lifespan=lifespan)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response


class DynamicCORSMiddleware(BaseHTTPMiddleware):
    """CORS middleware that reads allowed origins from brain/hosting.json at request time.

    Reflects the request Origin header (never sends '*') so credentials work per the CORS
    spec. When a domain_url is set via Admin → Hosting, only that origin is permitted.
    Falls back to settings.allowed_origins when no domain is configured.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        origin = request.headers.get("origin", "")

        if request.method == "OPTIONS":
            response = Response(status_code=200)
        else:
            response = await call_next(request)

        if origin and self._is_allowed(origin):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "*"
            if request.method == "OPTIONS":
                response.headers["Access-Control-Max-Age"] = "600"

        return response

    @staticmethod
    def _is_allowed(origin: str) -> bool:
        domain = effective_domain_url()
        if domain:
            return origin.rstrip("/") == domain.rstrip("/")
        # No domain configured: fall back to env-var setting
        allowed = settings.allowed_origins.strip()
        if allowed == "*":
            return True
        return origin in {o.strip() for o in allowed.split(",") if o.strip()}


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(DynamicCORSMiddleware)

app.include_router(health.router,     prefix="/api/v1/health",     tags=["health"])
app.include_router(auth.router,       prefix="/api/v1/auth",       tags=["auth"])
app.include_router(tasks.router,      prefix="/api/v1/tasks",      tags=["tasks"])
app.include_router(priorities.router, prefix="/api/v1/priorities", tags=["priorities"])
app.include_router(chat.router,       prefix="/api/v1/chat",       tags=["chat"])
app.include_router(setup.router,      prefix="/api/v1/setup",      tags=["setup"])
app.include_router(brain.router,      prefix="/api/v1/brain",      tags=["brain"])
app.include_router(export.router,     prefix="/api/v1/user",       tags=["export"])
app.include_router(shared.router,     prefix="/api/v1/shared",       tags=["shared"])
app.include_router(push.router,       prefix="/api/v1/push",         tags=["push"])
app.include_router(notes.router,      prefix="/api/v1/notes",        tags=["notes"])
app.include_router(journal.router,    prefix="/api/v1/journal",      tags=["journal"])
app.include_router(calendar.router,   prefix="/api/v1/calendar",     tags=["calendar"])
app.include_router(profile.router,    prefix="/api/v1/profile",      tags=["profile"])
app.include_router(suggestions.router, prefix="/api/v1/suggestions",  tags=["suggestions"])
app.include_router(infisical.router,  prefix="/api/v1/auth",          tags=["infisical"])
app.include_router(features.router,   prefix="/api/v1/auth",          tags=["features"])
app.include_router(automations.router, prefix="/api/v1/automations",    tags=["automations"])
app.include_router(home.router,        prefix="/api/v1/home",             tags=["home"])

# Serve React frontend — must come last
static_dir = Path(__file__).parent.parent / "frontend" / "dist"
if static_dir.exists():
    # Serve static assets (JS/CSS/images) directly
    app.mount("/assets", StaticFiles(directory=str(static_dir / "assets")), name="assets")

    # Serve any file that exists at the root of dist (icons, manifest, sw.js, etc.)
    _static_root = static_dir.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        """SPA catch-all — serve the file if it exists, otherwise index.html for client-side routing."""
        candidate = (static_dir / full_path).resolve()
        # Containment check prevents path traversal outside the dist directory
        if candidate.is_relative_to(_static_root) and candidate.is_file():
            return FileResponse(str(candidate))
        # no-cache: always revalidate before serving, but allow storage (needed for iOS PWA)
        return FileResponse(str(static_dir / "index.html"), headers={"Cache-Control": "no-cache"})
