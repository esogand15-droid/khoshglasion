"""Publish a draft into the target channel. The beautifier then edits it."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def publish_text(chat_id: int, text: str) -> tuple[int | None, str | None]:
    from backend.app.telegram.bot import get_bot
    from backend.app.telegram.user_editor import get_user_client

    bot = get_bot()
    if bot is not None:
        try:
            sent = await bot.send_message(chat_id, text[:4000])
            return int(sent.message_id), None
        except Exception as exc:
            logger.info("bot publish failed: %s", type(exc).__name__)
    client = await get_user_client()
    if client is None:
        return None, "ربات نتوانست پست بگذارد و نشست پرمیوم وصل نیست. ربات باید ادمین کانال باشد"
    try:
        sent = await client.send_message(int(chat_id), text[:4000])
        return int(sent.id), None
    except Exception as exc:
        logger.info("user publish failed: %s", type(exc).__name__)
        return None, "نه ربات و نه نشست پرمیوم نتوانستند در کانال بنویسند"
