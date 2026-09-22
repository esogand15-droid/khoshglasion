from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional

class Settings(BaseSettings):
    app_env: str = "development"
    log_level: str = "INFO"
    default_timezone: str = "Asia/Tehran"

    bot_token: str = ""
    bot_username: str = ""

    database_url: str = "sqlite+aiosqlite:///./data/khoshgelasion.db"
    redis_url: Optional[str] = None

    webhook_url: str = ""
    webhook_secret: str = ""
    webhook_path: str = "/telegram/webhook"

    admin_secret: str = "admin"
    session_secret: str = "change-me-32-chars-minimum-secret"
    jwt_secret: str = "change-me-jwt-secret"
    jwt_expire_minutes: int = 60 * 24

    dry_run: bool = False
    safe_mode: bool = True
    kill_switch: bool = False

    max_concurrent_processing: int = 5

    cors_origins: str = "*"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_sqlite(self) -> bool:
        return "sqlite" in self.database_url

@lru_cache
def get_settings() -> Settings:
    return Settings()
