"""Panel overrides for secrets that used to live only in the process environment.

The values stay in the database and an in-memory cache. They are never logged
and never returned by the settings API.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import get_settings
from backend.app.models.system import SystemSetting

PANEL_SECRET_KEYS = ("bot_token", "webhook_secret", "webhook_url", "jwt_secret")
_overrides: dict[str, str] = {}


def peek(key: str) -> str:
    override = (_overrides.get(key) or "").strip()
    if override:
        return override
    return str(getattr(get_settings(), key, "") or "").strip()


def resolved_webhook_url() -> str:
    override = (_overrides.get("webhook_url") or "").strip()
    if override:
        return override
    return get_settings().resolved_webhook_url


async def refresh_secrets(db: AsyncSession) -> None:
    rows = (
        await db.execute(select(SystemSetting).where(SystemSetting.key.in_(PANEL_SECRET_KEYS)))
    ).scalars().all()
    found = {row.key: (row.value or "").strip() for row in rows}
    for key in PANEL_SECRET_KEYS:
        if found.get(key):
            _overrides[key] = found[key]
        else:
            _overrides.pop(key, None)


async def ensure_webhook_secret(db: AsyncSession) -> bool:
    """Create a webhook secret once. Never log or return the value."""
    if peek("webhook_secret"):
        return False
    import secrets

    await save_secret(db, "webhook_secret", secrets.token_urlsafe(24))
    return True


async def save_secret(db: AsyncSession, key: str, value: str) -> None:
    if key not in PANEL_SECRET_KEYS:
        raise ValueError("unknown secret")
    cleaned = (value or "").strip()
    row = (await db.execute(select(SystemSetting).where(SystemSetting.key == key))).scalar_one_or_none()
    if not cleaned:
        if row:
            await db.delete(row)
        _overrides.pop(key, None)
        return
    if row is None:
        db.add(SystemSetting(key=key, value=cleaned, description="panel"))
    else:
        row.value = cleaned
    _overrides[key] = cleaned
    await db.flush()
