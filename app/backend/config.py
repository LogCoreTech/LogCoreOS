from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    brain_path: Path = Path("/data/brain")
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7 days
    anthropic_api_key: str = ""
    ai_model: str = "claude-sonnet-4-6"
    ntfy_url: str = "http://ntfy:80"

    class Config:
        env_file = ".env"


settings = Settings()
