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

    # How many days the "What's New" banner stays visible after an app update.
    whats_new_days: int = Field(5, ge=0, le=60)

    # Web Push / VAPID
    # Must be a mailto: or https: URL identifying the push sender
    vapid_subject: str = "logcore@localhost"

    # n8n workflow automation — bundled service default; override via Admin → n8n
    n8n_url: str = "http://n8n:5678"
    n8n_api_key: str = ""

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

    # Set to true when running behind a trusted reverse proxy (nginx, Caddy).
    # Allows the rate limiter to read the real client IP from X-Forwarded-For.
    # Leave false when the app is exposed directly — otherwise clients can spoof IPs.
    trust_proxy_headers: bool = False

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
