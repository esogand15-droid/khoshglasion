"""Panel-editable settings stored in Postgres/SQLite, layered over env defaults."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.models.system import SystemSetting

RUNTIME_KEYS = (
    "dry_run",
    "kill_switch",
    "safe_mode",
    "ai_enabled",
    "ai_base_url",
    "ai_model",
    "ai_api_key",
    "ai_temperature",
    "ai_max_tokens",
    "ai_min_chars",
    "edit_delay_seconds",
    "auto_register_channels",
    "reprocess_edits",
    "persian_normalize",
    "max_emoji_per_post",
    "preserve_links",
    "notify_chat_id",
    "admin_telegram_ids",
    "premium_mode",
    "default_footer",
)

_cache: dict = {"ts": 0.0, "data": None}
TTL_SECONDS = 2.0


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None, default: int) -> int:
    try:
        return int(float(value)) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _as_float(value: str | None, default: float) -> float:
    try:
        return float(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


def parse_id_list(raw: str | None) -> list[int]:
    if not raw:
        return []
    out: list[int] = []
    for part in raw.replace(";", ",").replace("\n", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            continue
    return out


@dataclass
class RuntimeState:
    dry_run: bool
    kill_switch: bool
    safe_mode: bool
    ai_enabled: bool
    ai_base_url: str
    ai_model: str
    ai_api_key: str
    ai_temperature: float
    ai_max_tokens: int
    ai_min_chars: int
    edit_delay_seconds: float
    auto_register_channels: bool
    reprocess_edits: bool
    persian_normalize: bool
    max_emoji_per_post: int
    preserve_links: bool
    notify_chat_id: str
    admin_telegram_ids: str
    premium_mode: str
    default_footer: str

    @property
    def admin_ids(self) -> list[int]:
        return parse_id_list(self.admin_telegram_ids)

    @property
    def notify_id(self) -> int | None:
        ids = parse_id_list(self.notify_chat_id)
        if ids:
            return ids[0]
        admins = self.admin_ids
        return admins[0] if admins else None

    @property
    def ai_ready(self) -> bool:
        return bool(self.ai_enabled and self.ai_base_url and self.ai_model and self.ai_api_key)

    def public_dict(self) -> dict:
        data = asdict(self)
        key = data.get("ai_api_key") or ""
        data["ai_api_key_set"] = bool(key)
        data["ai_api_key_masked"] = (key[:4] + "…" + key[-4:]) if len(key) > 10 else ("••••" if key else "")
        data.pop("ai_api_key", None)
        data["ai_ready"] = self.ai_ready
        data["admin_ids"] = self.admin_ids
        return data


def runtime_from_mapping(settings: Settings, mapping: dict[str, str | None]) -> RuntimeState:
    def raw(key: str) -> str | None:
        if key not in mapping:
            return None
        return mapping.get(key)

    return RuntimeState(
        dry_run=_as_bool(raw("dry_run"), settings.dry_run),
        kill_switch=_as_bool(raw("kill_switch"), settings.kill_switch),
        safe_mode=_as_bool(raw("safe_mode"), settings.safe_mode),
        ai_enabled=_as_bool(raw("ai_enabled"), settings.ai_enabled),
        ai_base_url=(raw("ai_base_url") if raw("ai_base_url") is not None else settings.ai_base_url) or "",
        ai_model=(raw("ai_model") if raw("ai_model") is not None else settings.ai_model) or "",
        ai_api_key=(raw("ai_api_key") if raw("ai_api_key") is not None else settings.ai_api_key) or "",
        ai_temperature=_as_float(raw("ai_temperature"), settings.ai_temperature),
        ai_max_tokens=_as_int(raw("ai_max_tokens"), settings.ai_max_tokens),
        ai_min_chars=_as_int(raw("ai_min_chars"), settings.ai_min_chars),
        edit_delay_seconds=_as_float(raw("edit_delay_seconds"), settings.edit_delay_seconds),
        auto_register_channels=_as_bool(raw("auto_register_channels"), settings.auto_register_channels),
        reprocess_edits=_as_bool(raw("reprocess_edits"), settings.reprocess_edits),
        persian_normalize=_as_bool(raw("persian_normalize"), settings.persian_normalize),
        max_emoji_per_post=_as_int(raw("max_emoji_per_post"), settings.max_emoji_per_post),
        preserve_links=_as_bool(raw("preserve_links"), settings.preserve_links),
        notify_chat_id=(raw("notify_chat_id") if raw("notify_chat_id") is not None else settings.notify_chat_id) or "",
        admin_telegram_ids=(raw("admin_telegram_ids") if raw("admin_telegram_ids") is not None else settings.admin_telegram_ids) or "",
        premium_mode=((raw("premium_mode") if raw("premium_mode") is not None else settings.premium_mode) or "auto").lower(),
        default_footer=(raw("default_footer") if raw("default_footer") is not None else "") or "",
    )


def invalidate_runtime() -> None:
    _cache["ts"] = 0.0
    _cache["data"] = None


async def load_runtime(db: AsyncSession, force: bool = False) -> RuntimeState:
    now = time.monotonic()
    if not force and _cache["data"] is not None and now - _cache["ts"] < TTL_SECONDS:
        return _cache["data"]
    rows = (await db.execute(select(SystemSetting))).scalars().all()
    mapping = {row.key: row.value for row in rows}
    state = runtime_from_mapping(get_settings(), mapping)
    _cache["data"] = state
    _cache["ts"] = now
    return state


def env_seed_values(settings: Settings | None = None) -> dict[str, str]:
    settings = settings or get_settings()
    values = {
        "dry_run": str(settings.dry_run).lower(),
        "kill_switch": str(settings.kill_switch).lower(),
        "safe_mode": str(settings.safe_mode).lower(),
        "ai_enabled": str(settings.ai_enabled).lower(),
        "ai_base_url": settings.ai_base_url or "",
        "ai_model": settings.ai_model or "",
        "ai_api_key": settings.ai_api_key or "",
        "ai_temperature": str(settings.ai_temperature),
        "ai_max_tokens": str(settings.ai_max_tokens),
        "ai_min_chars": str(settings.ai_min_chars),
        "edit_delay_seconds": str(settings.edit_delay_seconds),
        "auto_register_channels": str(settings.auto_register_channels).lower(),
        "reprocess_edits": str(settings.reprocess_edits).lower(),
        "persian_normalize": str(settings.persian_normalize).lower(),
        "max_emoji_per_post": str(settings.max_emoji_per_post),
        "preserve_links": str(settings.preserve_links).lower(),
        "notify_chat_id": settings.notify_chat_id or "",
        "admin_telegram_ids": settings.admin_telegram_ids or "",
        "premium_mode": settings.premium_mode or "auto",
        "default_footer": "",
    }
    return values


async def seed_runtime_defaults(db: AsyncSession) -> None:
    existing = {row.key for row in (await db.execute(select(SystemSetting.key))).scalars().all()}
    for key, value in env_seed_values().items():
        if key in existing:
            continue
        db.add(SystemSetting(key=key, value=value, description=f"runtime:{key}"))
    await db.flush()
    invalidate_runtime()


async def save_runtime_values(db: AsyncSession, updates: dict[str, str]) -> RuntimeState:
    if not updates:
        return await load_runtime(db, force=True)
    rows = (await db.execute(select(SystemSetting).where(SystemSetting.key.in_(list(updates))))).scalars().all()
    found = {row.key: row for row in rows}
    for key, value in updates.items():
        if key not in RUNTIME_KEYS:
            continue
        row = found.get(key)
        if row:
            row.value = value
        else:
            db.add(SystemSetting(key=key, value=value, description=f"runtime:{key}"))
    await db.flush()
    invalidate_runtime()
    return await load_runtime(db, force=True)


def runtime_field_names() -> set[str]:
    return {f.name for f in fields(RuntimeState)}
