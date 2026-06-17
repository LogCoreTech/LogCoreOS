import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import settings
from routers import auth, tasks, priorities, chat, setup, health
from scheduler import start as start_scheduler

logger = logging.getLogger("logcore")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _startup_checks()
    start_scheduler()
    yield


def _startup_checks() -> None:
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


app = FastAPI(title="LogCore OS", version="0.1.0", lifespan=lifespan)

_origins = (
    ["*"]
    if settings.allowed_origins.strip() == "*"
    else [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router,     prefix="/api/health",     tags=["health"])
app.include_router(auth.router,       prefix="/api/auth",       tags=["auth"])
app.include_router(tasks.router,      prefix="/api/tasks",      tags=["tasks"])
app.include_router(priorities.router, prefix="/api/priorities", tags=["priorities"])
app.include_router(chat.router,       prefix="/api/chat",       tags=["chat"])
app.include_router(setup.router,      prefix="/api/setup",      tags=["setup"])

# Serve React frontend — must come last
static_dir = Path(__file__).parent.parent / "frontend" / "dist"
if static_dir.exists():
    # Serve static assets (JS/CSS/images) directly
    app.mount("/assets", StaticFiles(directory=str(static_dir / "assets")), name="assets")

    # Serve any file that exists at the root of dist (icons, manifest, sw.js, etc.)
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        """SPA catch-all — serve the file if it exists, otherwise index.html for client-side routing."""
        candidate = static_dir / full_path
        if candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(static_dir / "index.html"))
