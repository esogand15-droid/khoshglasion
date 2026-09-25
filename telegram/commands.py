"""Private-chat controls and premium-emoji capture."""
from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.runtime import RuntimeState, load_runtime, save_runtime_values
from backend.app.formatting.richtext import role_for_raw_entity
from backend.app.telegram.emoji_pack import fetch_sticker_set, import_pack_names, parse_pack_names
from backend.app.formatting.textutil import utf16_slice
from backend.app.models.emoji import EmojiMapping
from backend.app.telegram.bot import get_bot
from backend.app.telegram.pipeline import reprocess_log
from backend.app.models.message_log import MessageLog

logger = logging.getLogger(__name__)

HELP = """خوشگلاسیون آماده‌ست.

کار اصلی‌ام این است: توی کانال، پست ادمین را می‌خوانم، خوشگل می‌کنم و همان پیام را ادیت می‌کنم.

دستورها:
/status وضعیت ربات
/id آیدی عددی تو
/dry on یا /dry off
/pause توقف کامل
/resume ادامه پردازش

برای پر کردن کتابخانه، ایموجی پرمیوم را همین‌جا بفرست یا لینک پک را بده:
https://t.me/addemoji/نام‌پک
/pack نام‌پک
اول در پنل، آیدی عددی‌ات را در «ادمین‌های تلگرام» بگذار تا دستورهای حساس قفل شود."""


def _allowed(user_id: int | None, runtime: RuntimeState, sensitive: bool = False) -> bool:
    if user_id is None:
        return False
    ids = runtime.admin_ids
    if not ids:
        return not sensitive
    return user_id in ids


async def _reply(chat_id: int, text: str) -> None:
    bot = get_bot()
    if not bot:
        return
    try:
        await bot.send_message(chat_id, text[:4000])
    except Exception as exc:
        logger.warning("command reply failed: %s", exc)


async def capture_custom_emoji(db: AsyncSession, message: dict) -> int:
    text = message.get("text") or message.get("caption") or ""
    entities = message.get("entities") or message.get("caption_entities") or []
    saved = 0
    for entity in entities:
        if entity.get("type") != "custom_emoji":
            continue
        custom_id = str(entity.get("custom_emoji_id") or "")
        if not custom_id.isdigit():
            continue
        offset = int(entity.get("offset") or 0)
        length = int(entity.get("length") or 0)
        emoji = utf16_slice(text, offset, length)
        if not emoji:
            continue
        role = role_for_raw_entity(text, entity)
        category = role if role in {"divider", "membership", "support"} else None
        existing = (
            await db.execute(
                select(EmojiMapping).where(
                    EmojiMapping.unicode_emoji == emoji,
                    EmojiMapping.custom_emoji_id == custom_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.enabled = True
            existing.source = existing.source or "capture"
            if category and not existing.category:
                existing.category = category
                existing.priority = max(existing.priority or 0, 90)
            continue
        db.add(EmojiMapping(
            unicode_emoji=emoji,
            custom_emoji_id=custom_id,
            enabled=True,
            category=category,
            priority=90 if category else 80,
            source="capture",
            label="گرفته‌شده از فوروارد",
        ))
        saved += 1
    if saved:
        await db.flush()
    return saved


async def handle_private_message(db: AsyncSession, message: dict, runtime: RuntimeState | None = None) -> dict:
    runtime = runtime or await load_runtime(db)
    chat = message.get("chat") or {}
    if chat.get("type") != "private":
        return {"ok": True, "skipped": "not_private"}
    user = message.get("from") or {}
    user_id = user.get("id")
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip()
    command = text.split()[0].split("@")[0].lower() if text.startswith("/") else ""

    captured = await capture_custom_emoji(db, message)
    pack_names = parse_pack_names(text, allow_bare=command == "/pack")
    if pack_names and command in {"", "/pack"}:
        if not _allowed(user_id, runtime, sensitive=bool(runtime.admin_ids)):
            await _reply(chat_id, "وارد کردن پک فقط برای ادمین ربات است.")
            return {"ok": True, "skipped": "not_admin"}
        result = await import_pack_names(db, pack_names, fetch_sticker_set)
        note = ""
        if captured:
            note = f"\n{captured} ایموجی همین پیام هم ذخیره شد."
        if not runtime.admin_ids:
            note += "\nهشدار: ادمین تلگرام هنوز قفل نشده. /id را در پنل بگذار."
        await _reply(chat_id, result["message"] + note)
        return {"ok": True, "captured": captured, "imported": result["imported"]}

    if captured and _allowed(user_id, runtime, sensitive=False):
        await _reply(chat_id, f"{captured} ایموجی پرمیوم به کتابخانه اضافه شد.")
        if not command:
            return {"ok": True, "captured": captured}

    if not command:
        return {"ok": True, "captured": captured}

    if not _allowed(user_id, runtime, sensitive=command in {"/pause", "/resume", "/kill", "/dry"}):
        if not runtime.admin_ids and command in {"/pause", "/resume", "/kill", "/dry"}:
            await _reply(chat_id, "این دستور قفل است. اول با /id آیدی‌ات را بگیر و در پنل، فیلد ادمین‌های تلگرام بگذار.")
        else:
            await _reply(chat_id, "این دستور فقط برای ادمین ربات است.")
        return {"ok": True, "skipped": "not_admin"}

    if command in {"/start", "/help"}:
        extra = ""
        if not runtime.admin_ids:
            extra = "\n\nهشدار: هنوز ادمین تلگرام تنظیم نشده. /id را بفرست و عدد را در پنل ذخیره کن."
        await _reply(chat_id, HELP + extra)
    elif command == "/id":
        await _reply(chat_id, f"آیدی عددی تو: {user_id}")
    elif command == "/status":
        await _reply(chat_id, _status_text(runtime))
    elif command in {"/pause", "/kill"}:
        arg = text.split()[1].lower() if len(text.split()) > 1 else "on"
        enabled = arg not in {"off", "0", "resume"}
        await save_runtime_values(db, {"kill_switch": str(enabled).lower()})
        await _reply(chat_id, "پردازش متوقف شد." if enabled else "پردازش دوباره روشن شد.")
    elif command == "/resume":
        await save_runtime_values(db, {"kill_switch": "false"})
        await _reply(chat_id, "پردازش روشن شد.")
    elif command == "/pack":
        await _reply(chat_id, "لینک پک را بفرست. نمونه: /pack https://t.me/addemoji/Name")
    elif command == "/dry":
        arg = text.split()[1].lower() if len(text.split()) > 1 else "on"
        enabled = arg not in {"off", "0", "false"}
        await save_runtime_values(db, {"dry_run": str(enabled).lower()})
        await _reply(chat_id, "حالت آزمایشی روشن شد؛ پیام واقعی ادیت نمی‌شود." if enabled else "حالت آزمایشی خاموش شد.")
    else:
        await _reply(chat_id, "دستور را نشناختم. /help")
    return {"ok": True, "command": command, "captured": captured}


async def handle_callback(db: AsyncSession, callback: dict, runtime: RuntimeState | None = None) -> dict:
    runtime = runtime or await load_runtime(db)
    user_id = (callback.get("from") or {}).get("id")
    data = callback.get("data") or ""
    bot = get_bot()
    allowed_ids = set(runtime.admin_ids)
    if runtime.notify_id:
        allowed_ids.add(runtime.notify_id)
    if allowed_ids and user_id not in allowed_ids:
        if bot:
            await bot.answer_callback_query(callback.get("id"), "فقط ادمین", show_alert=True)
        return {"ok": False, "reason": "not_admin"}
    if data.startswith("retry:"):
        try:
            _, chat_raw, message_raw = data.split(":", 2)
            chat_id, message_id = int(chat_raw), int(message_raw)
        except ValueError:
            return {"ok": False, "reason": "bad_callback"}
        log = (
            await db.execute(select(MessageLog).where(MessageLog.chat_id == chat_id, MessageLog.message_id == message_id))
        ).scalar_one_or_none()
        if log is None:
            if bot:
                await bot.answer_callback_query(callback.get("id"), "لاگ پیام پیدا نشد", show_alert=True)
            return {"ok": False, "reason": "missing"}
        result = await reprocess_log(db, log, runtime)
        if bot:
            await bot.answer_callback_query(callback.get("id"), f"نتیجه: {result.get('status')}")
        return result
    return {"ok": True, "skipped": "unknown_callback"}


def _status_text(runtime: RuntimeState) -> str:
    return "\n".join([
        "وضعیت خوشگلاسیون",
        f"توقف اضطراری: {'روشن' if runtime.kill_switch else 'خاموش'}",
        f"حالت آزمایشی: {'روشن' if runtime.dry_run else 'خاموش'}",
        f"هوش مصنوعی: {'آماده' if runtime.ai_ready else 'خاموش'}",
        f"ثبت خودکار کانال: {'روشن' if runtime.auto_register_channels else 'خاموش'}",
        f"حالت ایموجی: {runtime.premium_mode}",
        f"تأخیر ادیت: {runtime.edit_delay_seconds} ثانیه",
    ])


def callback_chat_id(callback: dict) -> int | None:
    message = callback.get("message") or {}
    chat = message.get("chat") or {}
    return chat.get("id")
