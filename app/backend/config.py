from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    brain_path: Path = Path("/data/brain")
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    # Fallback only — per-user session_minutes (set at registration or in Settings) takes precedence
    access_token_expire_minutes: int = 10080  # 7 days

    # AI provider — "anthropic" or "openai" (covers any OpenAI-compatible endpoint)
    ai_provider: str = "anthropic"
    anthropic_api_key: str = ""
    ai_model: str = "claude-sonnet-4-6"
    ai_api_key: str = ""  # generic key for OpenAI-compatible providers
    ai_base_url: str = ""  # custom endpoint; empty = provider default

    # Web Search — Tavily (https://tavily.com — free tier: 1 000 searches/month)
    # Required for Research mode web search. Leave empty to disable.
    tavily_api_key: str = ""

    # Notifications
    ntfy_url: str = "http://ntfy:80"
    # Access token for ntfy's admin publisher account — set automatically by
    # launch.sh once ntfy's default access is hardened to read-only (see
    # docker-compose.yml). Empty means ntfy is still in its default open-publish
    # mode, so no auth header is sent.
    ntfy_publish_token: str = ""

    # How many days the "What's New" banner stays visible after an app update.
    whats_new_days: int = Field(5, ge=0, le=60)

    # Web Push / VAPID — identifies the sender to a push service if it ever
    # needs to contact you about this instance's pushes (e.g. rate-limit
    # abuse). Set to a real email you control (bare address — wrapped in
    # mailto: automatically) or a full "https://your-domain" URL. The
    # placeholder default is syntactically valid but not a real contact point;
    # some push services (Apple's included) are stricter about honoring an
    # obviously-fake subject, so an unreachable placeholder is a plausible
    # cause of pushes silently not arriving. See docker/.env.example.
    vapid_subject: str = "logcore@localhost"

    # n8n workflow automation — bundled service default; override via Admin → n8n
    n8n_url: str = "http://n8n:5678"
    n8n_api_key: str = ""

    # Escape hatch for local development ONLY. When False (default) the app refuses
    # to start with the placeholder/empty SECRET_KEY, because that key lets anyone
    # mint a valid admin token offline. Set to true to run locally without setting a
    # real key. Never set this on a networked/production instance.
    allow_insecure_secret_key: bool = False

    # Escape hatch for local development ONLY. When False (default) the app refuses
    # to start with wildcard CORS (ALLOWED_ORIGINS="*"), because every real deployment
    # binds the port non-loopback (the Docker image always runs `uvicorn --host 0.0.0.0`)
    # and a wildcard origin lets any website read authenticated responses via a
    # victim's browser. Set to true to run locally with the "*" default unset.
    # Never set this on a networked/production instance.
    allow_insecure_cors: bool = False

    # Set to False only for local HTTP development; always True in production
    cookie_secure: bool = True

    # CORS — comma-separated origins, or "*" for development
    allowed_origins: str = "*"

    # Scheduler timezone — must be a valid IANA tz string
    scheduler_timezone: str = "America/Chicago"
    morning_digest_hour: int = Field(6, ge=0, le=23)  # 0–23, in scheduler_timezone
    overdue_check_hour: int = Field(19, ge=0, le=23)  # 0–23, in scheduler_timezone

    # When False (default), only the first user can self-register.
    # Subsequent users must be added by an admin.
    # Set to true to allow open registration (dev/testing only).
    allow_open_registration: bool = False

    # Marks this instance as a public demo (e.g. app.logcoretech.com) — surfaces
    # a "this is a demo, data resets nightly" banner in the UI, and is the
    # required safety gate for demo_reset.py (it refuses to delete anything
    # unless this is explicitly true, so a cron job copy-pasted onto a real
    # personal/family instance by mistake can't silently wipe real user data).
    # Never set this on a personal or managed-hosting instance.
    demo_mode: bool = False
    # Model forced for every AI call when demo_mode is on, regardless of whatever
    # ai_model an admin has configured — a demo instance takes unattended registrations,
    # so cost protection can't depend on an admin remembering to pick a cheap model.
    # Anthropic-only (matches this app's own default provider); has no effect when
    # ai_provider is "openai" — see ai_provider.py::_get_config().
    demo_ai_model: str = "claude-haiku-4-6"

    # Set to true when running behind a trusted reverse proxy (nginx, Caddy).
    # Allows the rate limiter to read the real client IP from X-Forwarded-For.
    # Leave false when the app is exposed directly — otherwise clients can spoof IPs.
    trust_proxy_headers: bool = False

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
