from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import get_settings
from backend.app.core.runtime import RUNTIME_KEYS, load_runtime, save_runtime_values
from backend.app.db.base import get_db
from backend.app.db.url import driver_name, is_external_database
from backend.app.models.admin import Admin
from backend.app.models.audit import AuditLog
from backend.app.models.channel import Channel
from backend.app.models.emoji import EmojiMapping
from backend.app.models.message_log import MessageLog
from backend.app.models.style import StylePreset
from backend.app.models.system import SystemSetting
from backend.app.security.auth import hash_password
from backend.app.security.deps import assert_editor, get_current_admin, require_role
from backend.app.services.ai import test_ai_connection
from backend.app.services.ai_provider import detect_provider, resolve_chat_completions_url
from backend.app.services.audit import write_audit
from backend.app.telegram.bot import get_bot
from backend.app.telegram.session_login import (
    SessionLoginError,
    cancel_login,
    check_saved_session,
    disconnect_session,
    is_secret_setting,
    refresh_user_credentials,
    resend_login_code,
    session_public_status,
    start_login,
    submit_code,
    submit_password,
)
from backend.app.telegram.user_editor import session_configured, user_session_status

router = APIRouter(prefix="/api/system", tags=["system"])

SECRET_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,256}$")


class RuntimePatch(BaseModel):
    dry_run: bool | None = None
    kill_switch: bool | None = None
    safe_mode: bool | None = None
    ai_enabled: bool | None = None
    ai_base_url: str | None = None
    ai_model: str | None = None
    ai_api_key: str | None = None
    ai_temperature: float | None = Field(default=None, ge=0, le=1.5)
    ai_max_tokens: int | None = Field(default=None, ge=64, le=4000)
    ai_min_chars: int | None = Field(default=None, ge=0, le=500)
    edit_delay_seconds: float | None = Field(default=None, ge=0, le=30)
    auto_register_channels: bool | None = None
    reprocess_edits: bool | None = None
    persian_normalize: bool | None = None
    max_emoji_per_post: int | None = Field(default=None, ge=0, le=30)
    preserve_links: bool | None = None
    notify_chat_id: str | None = None
    admin_telegram_ids: str | None = None
    premium_mode: str | None = None
    default_footer: str | None = None
    footer_url: str | None = None
    support_username: str | None = None


class SessionStart(BaseModel):
    api_id: str = Field(min_length=1, max_length=12)
    api_hash: str = Field(min_length=16, max_length=64)
    phone: str = Field(min_length=8, max_length=32)


class SessionCode(BaseModel):
    code: str = Field(min_length=1, max_length=16)


class SessionPassword(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class AdminCreate(BaseModel):
    username: str
    password: str
    role: str = "ADMIN"
    display_name: str | None = None
    telegram_id: int | None = None


def _runtime_updates(payload: RuntimePatch, current_key: str) -> dict[str, str]:
    data = payload.model_dump(exclude_unset=True)
    updates: dict[str, str] = {}
    for key, value in data.items():
        if key not in RUNTIME_KEYS or value is None and key != "default_footer":
            continue
        if key == "ai_api_key":
            if not value or value == "••••" or "…" in str(value):
                continue
            updates[key] = str(value)
            continue
        if isinstance(value, bool):
            updates[key] = str(value).lower()
        else:
            updates[key] = "" if value is None else str(value)
    if "premium_mode" in updates and updates["premium_mode"] not in {"auto", "bot", "user", "off"}:
        updates["premium_mode"] = "auto"
    return updates


def webhook_secret_alert(secret: str | None) -> dict | None:
    if (secret or "").strip():
        return None
    return {
        "level": "warn",
        "text": "WEBHOOK_SECRET خالی است. هر کسی که آدرس وبهوک را بداند می‌تواند آپدیت جعلی بفرستد.",
    }


async def _alerts(db: AsyncSession, runtime, settings) -> list[dict]:
    alerts = []
    secret_alert = webhook_secret_alert(settings.webhook_secret)
    if secret_alert:
        alerts.append(secret_alert)
    external = is_external_database(settings.database_url)
    if not external:
        alerts.append({
            "level": "danger",
            "text": "دیتابیس هنوز داخلی (SQLite) است. با هر دیپلوی روی Railway پاک می‌شود. پلاگین Postgres را وصل کن و DATABASE_URL را بگذار.",
        })
    if not settings.bot_token:
        alerts.append({"level": "danger", "text": "BOT_TOKEN تنظیم نشده. ربات نمی‌تواند پیام را ادیت کند."})
    if not settings.resolved_webhook_url:
        alerts.append({"level": "warn", "text": "آدرس وبهوک پیدا نشد. WEBHOOK_URL یا دامنه Railway را تنظیم کن."})
    if settings.jwt_secret.startswith("change-me") or settings.admin_secret in {"admin", "changeme"}:
        alerts.append({"level": "warn", "text": "رمز ادمین یا JWT هنوز پیش‌فرض است. قبل از استفاده واقعی عوضش کن."})
    if runtime.kill_switch:
        alerts.append({"level": "warn", "text": "توقف اضطراری روشن است. هیچ پستی پردازش نمی‌شود."})
    if runtime.dry_run:
        alerts.append({"level": "info", "text": "حالت آزمایشی روشن است. متن ساخته می‌شود ولی در تلگرام ادیت نمی‌شود."})
    channels = (await db.execute(select(func.count()).select_from(Channel))).scalar() or 0
    if channels == 0:
        alerts.append({"level": "info", "text": "هنوز کانالی ثبت نشده. ربات را ادمین کانال کن تا خودکار ثبت شود."})
    if runtime.ai_enabled and not runtime.ai_ready:
        alerts.append({"level": "warn", "text": "هوش مصنوعی روشن است ولی آدرس، مدل یا کلید کامل نیست."})
    last_emoji = (await db.execute(select(SystemSetting).where(SystemSetting.key == "last_emoji_error"))).scalar_one_or_none()
    if last_emoji and last_emoji.value:
        alerts.append({"level": "warn", "text": f"آخرین رد شدن ایموجی پرمیوم: {last_emoji.value[:180]}"})
    if runtime.premium_mode in {"auto", "user"}:
        session = await session_public_status(db)
        if not session["configured"]:
            alerts.append({
                "level": "warn",
                "text": "نشست پرمیوم داخل پنل وصل نیست. از تنظیمات، تب نشست، با شماره و کد تلگرام وصلش کن. بدون آن ایموجی متحرک داخل کانال ساده می‌ماند.",
            })
        elif session.get("premium") is False:
            alerts.append({
                "level": "warn",
                "text": "نشست وصل است ولی این اکانت تلگرام پرمیوم نیست. خط طلایی داخل کانال با اکانت بدون پرمیوم ساخته نمی‌شود.",
            })
    return alerts


@router.get("/health")
async def system_health(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    settings = get_settings()
    runtime = await load_runtime(db)
    session = await session_public_status(db)
    db_ok = True
    db_error = None
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        db_ok = False
        db_error = str(exc)
    bot = get_bot()
    me = None
    webhook = None
    if bot:
        try:
            raw = await bot.get_me()
            me = {"id": raw.id, "username": raw.username, "name": raw.full_name}
        except Exception as exc:
            me = {"error": str(exc)}
        try:
            info = await bot.get_webhook_info()
            webhook = {
                "url": info.url,
                "pending_update_count": info.pending_update_count,
                "last_error_message": info.last_error_message,
                "last_error_date": info.last_error_date.isoformat() if info.last_error_date else None,
                "max_connections": info.max_connections,
            }
        except Exception as exc:
            webhook = {"error": str(exc)}
    return {
        "database": "connected" if db_ok else "disconnected",
        "database_error": db_error,
        "driver": driver_name(settings.database_url),
        "external_database": is_external_database(settings.database_url),
        "bot": "connected" if me and "id" in me else "not_configured",
        "bot_info": me,
        "webhook": webhook or {"url": settings.resolved_webhook_url or "not_set"},
        "webhook_url": settings.resolved_webhook_url,
        "dry_run": runtime.dry_run,
        "safe_mode": runtime.safe_mode,
        "kill_switch": runtime.kill_switch,
        "env": settings.app_env,
        "version": settings.app_version,
        "premium_mode": runtime.premium_mode,
        "user_session_configured": session["configured"],
        "user_session_premium": session.get("premium"),
        "user_session_username": session.get("username"),
        "alerts": await _alerts(db, runtime, settings),
    }


@router.get("/overview")
async def overview(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    health = await system_health(db, admin)
    runtime = await load_runtime(db)
    channels = (await db.execute(select(func.count()).select_from(Channel))).scalar() or 0
    emojis = (await db.execute(select(func.count()).select_from(EmojiMapping).where(EmojiMapping.enabled == True))).scalar() or 0  # noqa: E712
    return {
        "health": health,
        "runtime": runtime.public_dict(),
        "counts": {"channels": channels, "emojis": emojis},
        "alerts": health["alerts"],
    }


@router.get("/settings")
async def get_settings_api(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    runtime = await load_runtime(db)
    settings = get_settings()
    await refresh_user_credentials(db)
    data = runtime.public_dict()
    data.update({
        "webhook_url": settings.resolved_webhook_url,
        "app_env": settings.app_env,
        "version": settings.app_version,
        "driver": driver_name(settings.database_url),
        "external_database": is_external_database(settings.database_url),
        "user_session_configured": session_configured(),
        "bot_configured": bool(settings.bot_token),
    })
    return _annotate_ai(data, runtime.ai_base_url)


@router.post("/settings")
async def update_settings(payload: RuntimePatch, request: Request, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    runtime = await load_runtime(db)
    updates = _runtime_updates(payload, runtime.ai_api_key)
    saved = await save_runtime_values(db, updates)
    await write_audit(
        db, admin=admin, action="update", resource="runtime",
        new_value={k: ("***" if k == "ai_api_key" else v) for k, v in updates.items()},
        ip_address=request.client.host if request.client else None,
    )
    return _annotate_ai(saved.public_dict(), saved.ai_base_url)


def _annotate_ai(data: dict, base_url: str) -> dict:
    data["ai_provider"] = detect_provider(base_url)
    data["ai_endpoint"] = _safe_endpoint(base_url)
    return data


def _safe_endpoint(base_url: str) -> str:
    try:
        return resolve_chat_completions_url(base_url) if base_url else ""
    except ValueError:
        return ""


@router.post("/ai/test")
async def test_ai(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    runtime = await load_runtime(db, force=True)
    return await test_ai_connection(runtime)


@router.get("/ai/config")
async def ai_config(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    runtime = await load_runtime(db)
    data = runtime.public_dict()
    return {
        "enabled": data["ai_enabled"],
        "base_url": data["ai_base_url"],
        "model": data["ai_model"],
        "api_key_set": data["ai_api_key_set"],
        "api_key_masked": data["ai_api_key_masked"],
        "temperature": data["ai_temperature"],
        "max_tokens": data["ai_max_tokens"],
        "ready": data["ai_ready"],
    }


@router.post("/ai/config")
async def update_ai_config(payload: RuntimePatch, request: Request, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    return await update_settings(payload, request, db, admin)


@router.post("/webhook/reset")
async def reset_webhook(db: AsyncSession = Depends(get_db), admin=Depends(require_role("OWNER", "ADMIN"))):
    settings = get_settings()
    bot = get_bot()
    url = settings.resolved_webhook_url
    if not bot or not url:
        raise HTTPException(status_code=400, detail="توکن یا آدرس عمومی وبهوک موجود نیست")
    secret = settings.webhook_secret or None
    if secret and not SECRET_TOKEN_RE.match(secret):
        raise HTTPException(status_code=400, detail="WEBHOOK_SECRET فقط حروف، عدد، _ و - می‌پذیرد")
    await bot.set_webhook(
        url=url,
        secret_token=secret,
        drop_pending_updates=False,
        allowed_updates=["channel_post", "edited_channel_post", "message", "edited_message", "my_chat_member", "callback_query"],
    )
    info = await bot.get_webhook_info()
    return {"ok": True, "url": info.url, "pending": info.pending_update_count, "last_error": info.last_error_message}


def _session_http(exc: SessionLoginError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=exc.message)


@router.get("/telegram-session")
async def telegram_session_status(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    return await session_public_status(db)


@router.post("/telegram-session/start")
async def telegram_session_start(
    payload: SessionStart,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_role("OWNER", "ADMIN")),
):
    try:
        result = await start_login(db, payload.api_id, payload.api_hash, payload.phone)
    except SessionLoginError as exc:
        raise _session_http(exc) from None
    await write_audit(
        db, admin=admin, action="start", resource="telegram_session",
        new_value={"step": result.get("step"), "phone_masked": result.get("phone_masked")},
        ip_address=request.client.host if request.client else None,
    )
    return result


@router.post("/telegram-session/code")
async def telegram_session_code(
    payload: SessionCode,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_role("OWNER", "ADMIN")),
):
    try:
        result = await submit_code(db, payload.code)
    except SessionLoginError as exc:
        raise _session_http(exc) from None
    if result.get("step") == "ready":
        await write_audit(
            db, admin=admin, action="connect", resource="telegram_session",
            new_value={"user_id": result.get("user_id"), "premium": result.get("premium")},
            ip_address=request.client.host if request.client else None,
        )
    return result


@router.post("/telegram-session/password")
async def telegram_session_password(
    payload: SessionPassword,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_role("OWNER", "ADMIN")),
):
    try:
        result = await submit_password(db, payload.password)
    except SessionLoginError as exc:
        raise _session_http(exc) from None
    await write_audit(
        db, admin=admin, action="connect", resource="telegram_session",
        new_value={"user_id": result.get("user_id"), "premium": result.get("premium")},
        ip_address=request.client.host if request.client else None,
    )
    return result


@router.post("/telegram-session/resend")
async def telegram_session_resend(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_role("OWNER", "ADMIN")),
):
    try:
        result = await resend_login_code(db)
    except SessionLoginError as exc:
        raise _session_http(exc) from None
    await write_audit(
        db, admin=admin, action="resend", resource="telegram_session",
        new_value={"step": result.get("step"), "phone_masked": result.get("phone_masked")},
        ip_address=request.client.host if request.client else None,
    )
    return result


@router.post("/telegram-session/check")
async def telegram_session_check(db: AsyncSession = Depends(get_db), admin=Depends(require_role("OWNER", "ADMIN"))):
    return await check_saved_session(db)


@router.post("/telegram-session/cancel")
async def telegram_session_cancel(db: AsyncSession = Depends(get_db), admin=Depends(require_role("OWNER", "ADMIN"))):
    return await cancel_login(db)


@router.post("/telegram-session/disconnect")
async def telegram_session_disconnect(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_role("OWNER", "ADMIN")),
):
    result = await disconnect_session(db)
    await write_audit(
        db, admin=admin, action="disconnect", resource="telegram_session",
        ip_address=request.client.host if request.client else None,
    )
    return result


@router.get("/premium")
async def premium_status(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    await refresh_user_credentials(db)
    return await user_session_status()


@router.get("/admins")
async def list_admins(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    rows = (await db.execute(select(Admin).order_by(Admin.created_at.asc()))).scalars().all()
    return [{
        "id": row.id,
        "username": row.username,
        "role": row.role,
        "display_name": row.display_name,
        "telegram_id": row.telegram_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "last_login_at": row.last_login_at.isoformat() if row.last_login_at else None,
    } for row in rows]


@router.post("/admins")
async def create_admin(payload: AdminCreate, request: Request, db: AsyncSession = Depends(get_db), admin=Depends(require_role("OWNER"))):
    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="رمز حداقل ۸ کاراکتر باشد")
    exists = (await db.execute(select(Admin).where(Admin.username == payload.username))).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="این نام کاربری وجود دارد")
    row = Admin(
        username=payload.username.strip(),
        password_hash=hash_password(payload.password),
        role=payload.role if payload.role in {"OWNER", "ADMIN", "EDITOR", "VIEWER"} else "ADMIN",
        display_name=payload.display_name,
        telegram_id=payload.telegram_id,
    )
    db.add(row)
    await db.flush()
    await write_audit(db, admin=admin, action="create", resource="admin", resource_id=row.id, ip_address=request.client.host if request.client else None)
    return {"id": row.id, "username": row.username}


@router.get("/audit")
async def audit(limit: int = 80, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    rows = (await db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 200)))).scalars().all()
    return [{
        "id": row.id,
        "admin_username": row.admin_username,
        "action": row.action,
        "resource": row.resource,
        "resource_id": row.resource_id,
        "new_value": row.new_value,
        "ip_address": row.ip_address,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    } for row in rows]


@router.get("/backup")
async def backup(include_secrets: bool = False, db: AsyncSession = Depends(get_db), admin=Depends(require_role("OWNER"))):
    channels = (await db.execute(select(Channel))).scalars().all()
    emojis = (await db.execute(select(EmojiMapping))).scalars().all()
    styles = (await db.execute(select(StylePreset))).scalars().all()
    settings_rows = (await db.execute(select(SystemSetting))).scalars().all()
    runtime = {}
    for row in settings_rows:
        if row.key == "ai_api_key" and not include_secrets:
            continue
        if is_secret_setting(row.key):
            continue
        runtime[row.key] = row.value
    return {
        "version": 2,
        "channels": [{
            "chat_id": c.chat_id, "username": c.username, "title": c.title, "enabled": c.enabled,
            "auto_beautify": c.auto_beautify, "emoji_replacement": c.emoji_replacement,
            "style_id": c.style_id, "footer_text": c.footer_text, "header_enabled": c.header_enabled,
            "ai_rewrite": c.ai_rewrite, "edit_delay_seconds": c.edit_delay_seconds,
            "signature_text": c.signature_text, "signature_url": c.signature_url,
            "skip_keywords": c.skip_keywords, "min_chars": c.min_chars,
            "preserve_buttons": c.preserve_buttons, "notes": c.notes,
        } for c in channels],
        "emojis": [{
            "unicode_emoji": e.unicode_emoji, "custom_emoji_id": e.custom_emoji_id,
            "enabled": e.enabled, "category": e.category, "contexts": e.contexts,
            "priority": e.priority, "label": e.label,
        } for e in emojis],
        "styles": [{"name": s.name, "slug": s.slug, "description": s.description, "config": s.config} for s in styles],
        "runtime": runtime,
    }


@router.post("/restore")
async def restore(payload: dict, request: Request, db: AsyncSession = Depends(get_db), admin=Depends(require_role("OWNER"))):
    restored = {"channels": 0, "emojis": 0, "styles": 0, "runtime": 0}
    for item in payload.get("channels") or []:
        chat_id = item.get("chat_id")
        if chat_id is None:
            continue
        row = (await db.execute(select(Channel).where(Channel.chat_id == int(chat_id)))).scalar_one_or_none()
        if row is None:
            row = Channel(chat_id=int(chat_id))
            db.add(row)
        for key in ("username", "title", "enabled", "auto_beautify", "emoji_replacement", "style_id", "footer_text", "header_enabled", "ai_rewrite", "edit_delay_seconds", "signature_text", "signature_url", "skip_keywords", "min_chars", "preserve_buttons", "notes"):
            if key in item:
                setattr(row, key, item[key])
        restored["channels"] += 1
    for item in payload.get("emojis") or []:
        emoji = item.get("unicode_emoji")
        custom_id = str(item.get("custom_emoji_id") or "")
        if not emoji or not custom_id:
            continue
        row = (await db.execute(select(EmojiMapping).where(EmojiMapping.unicode_emoji == emoji, EmojiMapping.custom_emoji_id == custom_id))).scalar_one_or_none()
        if row is None:
            row = EmojiMapping(unicode_emoji=emoji, custom_emoji_id=custom_id, source="restore")
            db.add(row)
        for key in ("enabled", "category", "contexts", "priority", "label"):
            if key in item:
                setattr(row, key, item[key])
        restored["emojis"] += 1
    for item in payload.get("styles") or []:
        slug = item.get("slug")
        if not slug:
            continue
        row = (await db.execute(select(StylePreset).where(StylePreset.slug == slug))).scalar_one_or_none()
        config = item.get("config")
        if not isinstance(config, str):
            config = json.dumps(config or {}, ensure_ascii=False)
        if row is None:
            db.add(StylePreset(name=item.get("name") or slug, slug=slug, description=item.get("description"), config=config))
        else:
            row.name = item.get("name") or row.name
            row.config = config
        restored["styles"] += 1
    runtime = payload.get("runtime") or {}
    if isinstance(runtime, dict) and runtime:
        clean = {k: str(v) for k, v in runtime.items() if k in RUNTIME_KEYS and v is not None}
        await save_runtime_values(db, clean)
        restored["runtime"] = len(clean)
    await write_audit(db, admin=admin, action="restore", resource="backup", new_value=restored, ip_address=request.client.host if request.client else None)
    return {"ok": True, "restored": restored}
