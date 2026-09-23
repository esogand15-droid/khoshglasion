from __future__ import annotations

import asyncio
import logging
import re

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup

from backend.app.telegram.bot import get_bot

logger = logging.getLogger(__name__)

EMOJI_ERROR_HINTS = (
    "custom emoji",
    "emoji",
    "document_invalid",
    "entity_text_invalid",
    "can't parse entities",
    "cant parse entities",
    "can't parse",
    "purchased additional usernames",
    "premium_account",
)


def markup_from_raw(raw: dict | None) -> InlineKeyboardMarkup | None:
    if not raw or not isinstance(raw, dict):
        return None
    if not raw.get("inline_keyboard"):
        return None
    try:
        return InlineKeyboardMarkup.model_validate(raw)
    except Exception as exc:
        logger.warning("Ignoring invalid reply_markup: %s", exc)
        return None


def merge_signature(raw: dict | None, text: str | None, url: str | None) -> dict | None:
    if not text or not url:
        return raw
    button = {"text": text[:64], "url": url}
    keyboard = []
    if raw and isinstance(raw.get("inline_keyboard"), list):
        keyboard = [list(row) for row in raw["inline_keyboard"]]
        for row in keyboard:
            for existing in row:
                if isinstance(existing, dict) and existing.get("url") == url:
                    return {"inline_keyboard": keyboard}
    keyboard.append([button])
    return {"inline_keyboard": keyboard}


def strip_custom_emoji_html(html_text: str | None) -> str | None:
    if not html_text:
        return None
    stripped = re.sub(r"<tg-emoji\b[^>]*>(.*?)</tg-emoji>", r"\1", html_text, flags=re.DOTALL)
    return stripped if "<" in stripped else None


def is_emoji_rejection(message: str) -> bool:
    lowered = (message or "").lower()
    return any(hint in lowered for hint in EMOJI_ERROR_HINTS)


async def edit_telegram_message(
    chat_id: int,
    message_id: int,
    text: str,
    html_text: str | None = None,
    is_caption: bool = False,
    reply_markup: dict | None = None,
    prefer_html: bool = True,
    max_retries: int = 3,
) -> dict:
    bot = get_bot()
    if not bot:
        return {"ok": False, "error": "bot not configured"}

    markup = markup_from_raw(reply_markup)
    formatting_html = strip_custom_emoji_html(html_text)
    attempts = [
        ("bot_html", html_text, "HTML") if prefer_html and html_text else None,
        ("bot_html_text", formatting_html, "HTML") if formatting_html and formatting_html != html_text else None,
        ("bot_plain", text, None),
    ]
    attempts = [item for item in attempts if item]
    last_error = "edit_failed"
    emoji_rejected = False

    for method, payload, parse_mode in attempts:
        if not payload:
            continue
        attempt = 0
        while attempt <= max_retries:
            try:
                kwargs = {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "reply_markup": markup,
                }
                if parse_mode:
                    kwargs["parse_mode"] = parse_mode
                if is_caption:
                    await bot.edit_message_caption(caption=payload, **kwargs)
                else:
                    await bot.edit_message_text(text=payload, **kwargs)
                return {"ok": True, "method": method, "emoji_rejected": emoji_rejected}
            except TelegramRetryAfter as exc:
                wait = min(int(getattr(exc, "retry_after", 2) or 2), 30)
                logger.warning("Telegram rate limit, sleeping %ss", wait)
                await asyncio.sleep(wait)
                attempt += 1
                last_error = f"retry_after:{wait}"
            except TelegramBadRequest as exc:
                msg = str(exc)
                lowered = msg.lower()
                if "message is not modified" in lowered:
                    return {"ok": True, "method": method, "warning": "not_modified", "emoji_rejected": emoji_rejected}
                if "message to edit not found" in lowered or "message can't be edited" in lowered or "message_id_invalid" in lowered:
                    return {"ok": False, "error": f"not_editable: {msg}", "method": method}
                if method == "bot_html" and is_emoji_rejection(msg):
                    emoji_rejected = True
                    last_error = msg
                    logger.warning("Custom emoji rejected; keeping quote and links: %s", msg)
                    break
                return {"ok": False, "error": msg, "method": method, "emoji_rejected": emoji_rejected}
            except TelegramForbiddenError as exc:
                return {"ok": False, "error": f"forbidden: {exc}", "method": method}
            except TelegramNetworkError as exc:
                last_error = str(exc)
                logger.warning("Network error editing message: %s", exc)
                await asyncio.sleep(min(8, 2 ** attempt))
                attempt += 1
            except Exception as exc:
                logger.exception("Unexpected edit error")
                return {"ok": False, "error": str(exc), "method": method}
    return {"ok": False, "error": last_error, "emoji_rejected": emoji_rejected}
