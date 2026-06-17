from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    brain_path: Path = Path("/data/brain")
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7 days

    # AI provider — only "anthropic" is wired up; structure is ready for others
    ai_provider: str = "anthropic"
    anthropic_api_key: str = ""
    ai_model: str = "claude-sonnet-4-6"

    # Notifications
    ntfy_url: str = "http://ntfy:80"

    # CORS — comma-separated origins, or "*" for development
    allowed_origins: str = "*"

    # Scheduler timezone — must be a valid IANA tz string
    scheduler_timezone: str = "America/Chicago"
    morning_digest_hour: int = 6   # 0–23, in scheduler_timezone
    overdue_check_hour: int = 19   # 0–23, in scheduler_timezone

    # When False (default), only the first user can self-register.
    # Subsequent users must be added by an admin.
    # Set to true to allow open registration (dev/testing only).
    allow_open_registration: bool = False

    class Config:
        env_file = ".env"


settings = Settings()
