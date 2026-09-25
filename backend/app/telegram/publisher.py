"""Publish a rendered draft. Premium emoji uses the saved session.

A premium post is tried first. If that send fails, the photo or video still
goes out, but the custom-emoji spans are removed. They are not replaced with
a unicode lookalike, and no emoji id is invented.
"""
from __future__ import annotations

import logging

from backend.app.content.caption import clip_text_entities, strip_custom_emoji_spans
from backend.app.telegram.edit import strip_custom_emoji_html
from backend.app.telegram.sent_mark import forget_outgoing, remember_outgoing, remember_sent_id

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


def _mark_sent(chat_id: int, message_id: int | None) -> None:
    if message_id:
        remember_sent_id(chat_id, int(message_id))


async def publish_rendered(
    chat_id: int,
    text: str,
    html_text: str | None = None,
    entities: list[dict] | None = None,
    photo_path: str | None = None,
    photo_paths: list[str] | None = None,
    video_path: str | None = None,
) -> tuple[int | None, str | None]:
    from backend.app.content.intake import safe_media_path, safe_photo_path
    from backend.app.telegram.bot import get_bot
    from backend.app.telegram.user_editor import send_album_via_user, send_photo_via_user, send_via_user, send_video_via_user

    photos = [path for path in (photo_paths or []) if safe_photo_path(path)]
    photo = safe_photo_path(photo_path) if photo_path else None
    if photo is not None and str(photo) not in photos:
        photos.insert(0, str(photo))
    video = safe_media_path(video_path) if video_path else None
    limit = 1024 if photos or video else 4000
    body, clipped = clip_text_entities(text or "", entities, limit)
    if not body.strip():
        return None, "متن پیش‌نویس خالی است"
    if photo_path and not photos and video is None:
        return None, "عکس منبع پیدا نشد"
    if video_path and video is None and not photos:
        return None, "ویدیو منبع پیدا نشد"
    remembered: list[str] = []

    def mark_text(value: str) -> None:
        remember_outgoing(chat_id, value)
        remembered.append(value)

    def fail(error: str) -> tuple[None, str]:
        for item in remembered:
            forget_outgoing(chat_id, item)
        return None, error

    mark_text(body)

    if video is not None and requires_premium_send(clipped, html_text):
        sent = await send_video_via_user(chat_id, body, clipped, str(video))
        if sent.get("ok"):
            _mark_sent(chat_id, sent.get("message_id"))
            return int(sent["message_id"]), None
        logger.info("premium video send failed; photo-style plain retry: %s", sent.get("error"))
        plain = strip_custom_emoji_spans(body, clipped)
        if plain:
            mark_text(plain)
            sent = await send_video_via_user(chat_id, plain, None, str(video))
            if sent.get("ok"):
                _mark_sent(chat_id, sent.get("message_id"))
                return int(sent["message_id"]), None
        return fail(str(sent.get("error") or "ویدیو با کپشن ارسال نشد"))
    if video is not None:
        sent = await send_video_via_user(chat_id, body, None, str(video))
        if sent.get("ok"):
            _mark_sent(chat_id, sent.get("message_id"))
            return int(sent["message_id"]), None
        return fail(str(sent.get("error") or "ویدیو با کپشن ارسال نشد"))

    if len(photos) > 1:
        sent = await send_album_via_user(chat_id, body, clipped if requires_premium_send(clipped, html_text) else None, photos)
        if sent.get("ok"):
            for mid in sent.get("message_ids") or []:
                _mark_sent(chat_id, mid)
            return int(sent["message_id"]), None
        logger.info("album send failed; first photo retry: %s", sent.get("error"))
        photos = photos[:1]

    if photos and requires_premium_send(clipped, html_text):
        sent = await send_photo_via_user(chat_id, body, clipped, photos[0])
        if sent.get("ok"):
            _mark_sent(chat_id, sent.get("message_id"))
            return int(sent["message_id"]), None
        logger.info("premium photo send failed; sending the photo without custom emoji: %s", sent.get("error"))
        plain = strip_custom_emoji_spans(body, clipped)
        if not plain:
            return fail(str(sent.get("error") or "premium_send_failed"))
        mark_text(plain)
        fallback = await _send_photo(chat_id, plain, None, photos[0])
        if fallback[0]:
            _mark_sent(chat_id, fallback[0])
            return fallback
        return fail(fallback[1] or "عکس با کپشن ارسال نشد")
    if photos:
        result = await _send_photo(chat_id, body, html_text, photos[0])
        if result[0]:
            _mark_sent(chat_id, result[0])
            return result
        return fail(result[1] or "عکس با کپشن ارسال نشد")

    if requires_premium_send(clipped, html_text):
        sent = await send_via_user(chat_id, body, clipped)
        if sent.get("ok"):
            _mark_sent(chat_id, sent.get("message_id"))
            return int(sent["message_id"]), None
        logger.info("premium send failed; plain text retry without custom emoji: %s", sent.get("error"))
        plain = strip_custom_emoji_spans(body, clipped)
        if not plain:
            return fail(str(sent.get("error") or "premium_send_failed"))
        mark_text(plain)
        body = plain
        html_text = None
        clipped = None
    bot = get_bot()
    if bot is not None:
        plain_html = strip_custom_emoji_html(html_text) if clipped is None else None
        if plain_html:
            try:
                sent = await bot.send_message(chat_id, plain_html[:4000], parse_mode="HTML")
                _mark_sent(chat_id, sent.message_id)
                return int(sent.message_id), None
            except Exception as exc:
                logger.info("bot html publish failed: %s", type(exc).__name__)
        try:
            sent = await bot.send_message(chat_id, body)
            _mark_sent(chat_id, sent.message_id)
            return int(sent.message_id), None
        except Exception as exc:
            logger.info("bot publish failed: %s", type(exc).__name__)
    sent = await send_via_user(chat_id, body, clipped)
    if sent.get("ok"):
        _mark_sent(chat_id, sent.get("message_id"))
        return int(sent["message_id"]), None
    return fail("نه ربات و نه نشست پرمیوم نتوانستند در کانال بنویسند")


async def _send_photo(chat_id: int, caption: str, html_text: str | None, photo_path: str) -> tuple[int | None, str | None]:
    from pathlib import Path

    from aiogram.types import BufferedInputFile

    from backend.app.content.intake import photo_bytes_for_telegram
    from backend.app.telegram.bot import get_bot
    from backend.app.telegram.user_editor import send_photo_via_user

    payload, name = photo_bytes_for_telegram(Path(photo_path))
    bot = get_bot()
    plain = strip_custom_emoji_html(html_text) or caption
    plain, _entities = clip_text_entities(plain, None, 1024)
    if bot is not None and plain:
        try:
            sent = await bot.send_photo(chat_id, BufferedInputFile(payload, filename=name), caption=plain)
            return int(sent.message_id), None
        except Exception as exc:
            logger.info("bot photo publish failed: %s", type(exc).__name__)
    sent = await send_photo_via_user(chat_id, plain, None, photo_path)
    if sent.get("ok"):
        return int(sent.message_id), None
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
