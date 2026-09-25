from functools import lru_cache
import os
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    default_timezone: str = "Asia/Tehran"
    app_version: str = "2.0.0"

    bot_token: str = ""
    bot_username: str = ""

    # Railway Postgres plugin injects DATABASE_URL=postgresql://...
    # Also accept the public URL as a fallback name, never prefer it over private.
    database_url: str = "sqlite+aiosqlite:///./data/khoshgelasion.db"
    redis_url: Optional[str] = None

    webhook_url: str = ""
    webhook_secret: str = ""
    webhook_path: str = "/telegram/webhook"
    drop_pending_updates: bool = False

    admin_secret: str = "admin"
    session_secret: str = "change-me-32-chars-minimum-secret"
    jwt_secret: str = "change-me-jwt-secret"
    jwt_expire_minutes: int = 60 * 24 * 7
    reset_admin_on_boot: bool = False

    dry_run: bool = False
    safe_mode: bool = True
    kill_switch: bool = False

    max_concurrent_processing: int = 4
    edit_delay_seconds: float = 1.5

    cors_origins: str = "*"

    ai_base_url: str = ""
    ai_model: str = ""
    ai_api_key: str = ""
    ai_enabled: bool = False
    ai_temperature: float = 0.7
    ai_max_tokens: int = 1800
    ai_min_chars: int = 40
    ai_prompt_template: str = ""

    # auto | bot | user | off
    premium_mode: str = "auto"
    tg_api_id: str = ""
    tg_api_hash: str = ""
    tg_session_string: str = ""

    auto_register_channels: bool = True
    reprocess_edits: bool = True
    persian_normalize: bool = True
    max_emoji_per_post: int = 10
    preserve_links: bool = True
    notify_chat_id: str = ""
    admin_telegram_ids: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    @property
    def is_sqlite(self) -> bool:
        return "sqlite" in (self.database_url or "")

    @property
    def resolved_webhook_url(self) -> str:
        if self.webhook_url.strip():
            return self.webhook_url.strip()
        domain = os.getenv("RAILWAY_PUBLIC_DOMAIN") or os.getenv("RAILWAY_STATIC_URL") or ""
        domain = domain.strip().removeprefix("https://").removeprefix("http://").strip("/")
        if domain:
            return f"https://{domain}{self.webhook_path}"
        return ""

    @property
    def user_session_configured(self) -> bool:
        return bool(self.tg_api_id and self.tg_api_hash and self.tg_session_string)


@lru_cache
def get_settings() -> Settings:
    return Settings()
