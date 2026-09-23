from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import select

from backend.app.core.config import get_settings
from backend.app.core.runtime import seed_runtime_defaults
from backend.app.db.base import get_session_factory
from backend.app.db.schema_sync import ensure_schema
from backend.app.db.url import driver_name, is_external_database, normalize_sync_url
from backend.app.models.admin import Admin
from backend.app.models.emoji import EmojiMapping
from backend.app.security.auth import hash_password

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[3]


def run_alembic() -> None:
    from alembic import command
    from alembic.config import Config

    ini = ROOT / "alembic.ini"
    if not ini.exists():
        logger.warning("alembic.ini not found, skipping migrations")
        return
    cfg = Config(str(ini))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", normalize_sync_url(get_settings().database_url))
    command.upgrade(cfg, "head")


async def seed_admin(db) -> None:
    settings = get_settings()
    admin = (await db.execute(select(Admin).where(Admin.username == "admin"))).scalar_one_or_none()
    secret = settings.admin_secret or "admin"
    if admin is None:
        db.add(Admin(username="admin", password_hash=hash_password(secret), role="OWNER", display_name="Owner"))
        logger.info("Seeded admin user")
        return
    if settings.reset_admin_on_boot:
        admin.password_hash = hash_password(secret)
        admin.role = "OWNER"
        logger.warning("Admin password reset because RESET_ADMIN_ON_BOOT=true")


async def seed_emojis(db) -> None:
    existing = (await db.execute(select(EmojiMapping.id).limit(1))).first()
    if existing:
        return
    seed_path = Path(__file__).resolve().parents[1] / "data" / "premium_emoji_seed.json"
    if not seed_path.exists():
        return
    raw = json.loads(seed_path.read_text(encoding="utf-8"))
    for item in raw:
        db.add(EmojiMapping(
            unicode_emoji=item["unicode_emoji"],
            custom_emoji_id=str(item["custom_emoji_id"]),
            category=item.get("category"),
            priority=item.get("priority", 50),
            label=item.get("label"),
            source="seed",
            enabled=True,
        ))
    logger.info("Seeded %s premium emoji mappings", len(raw))


async def bootstrap() -> None:
    settings = get_settings()
    logger.info(
        "Starting Khoshgelasion %s | db=%s | external=%s",
        settings.app_version,
        driver_name(settings.database_url),
        is_external_database(settings.database_url),
    )
    try:
        run_alembic()
    except Exception as exc:
        logger.warning("Alembic upgrade failed, continuing with schema sync: %s", exc)
    await ensure_schema()
    factory = get_session_factory()
    async with factory() as db:
        await seed_admin(db)
        await seed_emojis(db)
        await seed_runtime_defaults(db)
        from backend.app.telegram.session_login import refresh_user_credentials
        await refresh_user_credentials(db)
        await db.commit()
