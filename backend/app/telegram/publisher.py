"""Publish a rendered draft. Premium emoji uses the saved session.

A premium post is not retried as unicode emoji. If the session cannot send
the custom entities, the error is returned and nothing plain is published.
"""
from __future__ import annotations

import logging

from backend.app.telegram.edit import strip_custom_emoji_html

logger = logging.getLogger(__name__)


def _has_custom_emoji(entities: list[dict] | None) -> bool:
    return any(
        item.get("type") == "custom_emoji" and str(item.get("custom_emoji_id") or "").isdigit()
        for item in entities or []
    )


def requires_premium_send(entities: list[dict] | None, html_text: str | None) -> bool:
    if _has_custom_emoji(entities):
        return True
    return bool(html_text and "<tg-emoji" in html_text)


async def publish_rendered(
    chat_id: int,
    text: str,
    html_text: str | None = None,
    entities: list[dict] | None = None,
    photo_path: str | None = None,
) -> tuple[int | None, str | None]:
    from backend.app.content.intake import safe_photo_path
    from backend.app.telegram.bot import get_bot
    from backend.app.telegram.user_editor import send_photo_via_user, send_via_user

    body = (text or "")[:1024 if photo_path else 4000]
    if not body.strip():
        return None, "متن پیش‌نویس خالی است"
    photo = safe_photo_path(photo_path) if photo_path else None
    if photo_path and photo is None:
        return None, "عکس منبع پیدا نشد"
    if photo is not None and requires_premium_send(entities, html_text):
        sent = await send_photo_via_user(chat_id, body, entities, str(photo))
        if sent.get("ok"):
            return int(sent["message_id"]), None
        logger.info("premium photo send failed; unicode fallback removed: %s", sent.get("error"))
        return None, str(sent.get("error") or "premium_send_failed")
    if photo is not None:
        return await _send_photo(chat_id, body, html_text, str(photo))
    if requires_premium_send(entities, html_text):
        sent = await send_via_user(chat_id, body, entities)
        if sent.get("ok"):
            return int(sent["message_id"]), None
        logger.info("premium send failed; unicode fallback removed: %s", sent.get("error"))
        return None, str(sent.get("error") or "premium_send_failed")
    bot = get_bot()
    if bot is not None:
        plain_html = strip_custom_emoji_html(html_text)
        if plain_html:
            try:
                sent = await bot.send_message(chat_id, plain_html[:4000], parse_mode="HTML")
                return int(sent.message_id), None
            except Exception as exc:
                logger.info("bot html publish failed: %s", type(exc).__name__)
        try:
            sent = await bot.send_message(chat_id, body)
            return int(sent.message_id), None
        except Exception as exc:
            logger.info("bot publish failed: %s", type(exc).__name__)
    sent = await send_via_user(chat_id, body, None)
    if sent.get("ok"):
        return int(sent["message_id"]), None
    return None, "نه ربات و نه نشست پرمیوم نتوانستند در کانال بنویسند"


async def _send_photo(chat_id: int, caption: str, html_text: str | None, photo_path: str) -> tuple[int | None, str | None]:
    from pathlib import Path

    from aiogram.types import BufferedInputFile

    from backend.app.content.intake import photo_bytes_for_telegram
    from backend.app.telegram.bot import get_bot
    from backend.app.telegram.edit import strip_custom_emoji_html
    from backend.app.telegram.user_editor import send_photo_via_user

    payload, name = photo_bytes_for_telegram(Path(photo_path))
    bot = get_bot()
    plain = strip_custom_emoji_html(html_text) or caption
    if bot is not None:
        try:
            sent = await bot.send_photo(chat_id, BufferedInputFile(payload, filename=name), caption=plain[:1024])
            return int(sent.message_id), None
        except Exception as exc:
            logger.info("bot photo publish failed: %s", type(exc).__name__)
    sent = await send_photo_via_user(chat_id, caption, None, photo_path)
    if sent.get("ok"):
        return int(sent["message_id"]), None
    return None, "عکس با کپشن ارسال نشد"


async def delete_published(chat_id: int, message_id: int) -> str | None:
    from backend.app.telegram.bot import get_bot
    from backend.app.telegram.user_editor import delete_via_user

    bot = get_bot()
    if bot is not None:
        try:
            await bot.delete_message(chat_id, message_id)
            return None
        except Exception as exc:
            logger.info("bot delete failed: %s", type(exc).__name__)
    removed = await delete_via_user(chat_id, message_id)
    if removed.get("ok"):
        return None
    return "نه ربات و نه نشست پرمیوم نتوانستند پیام را از کانال حذف کنند"


async def publish_text(chat_id: int, text: str) -> tuple[int | None, str | None]:
    return await publish_rendered(chat_id, text)
