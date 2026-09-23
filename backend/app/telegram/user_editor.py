"""Optional premium-emoji editor through the owner's user account.

Bot API can attach custom emoji when the bot owner has Telegram Premium, but
channel posts are still the unreliable case. A user session that is admin of
the channel can place animated custom-emoji entities directly. The session
string stays in the environment and is never written to the database or panel.
"""
from __future__ import annotations

import logging

from backend.app.core.config import get_settings
from backend.app.formatting.textutil import utf16_len

logger = logging.getLogger(__name__)

_client = None


def session_configured() -> bool:
    settings = get_settings()
    return bool(settings.tg_api_id and settings.tg_api_hash and settings.tg_session_string)


async def get_user_client():
    global _client
    settings = get_settings()
    if not session_configured():
        return None
    if _client is not None and _client.is_connected():
        return _client
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError:
        logger.warning("telethon is not installed; user-session premium editor disabled")
        return None
    try:
        client = TelegramClient(StringSession(settings.tg_session_string), int(settings.tg_api_id), settings.tg_api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            logger.error("TG_SESSION_STRING is not authorized")
            await client.disconnect()
            return None
        _client = client
        return client
    except Exception as exc:
        logger.error("Could not start user session: %s", exc)
        return None


async def close_user_client() -> None:
    global _client
    if _client is not None:
        try:
            await _client.disconnect()
        except Exception:
            pass
        _client = None


def _entities(text: str, spans: list[tuple[int, int, str]]):
    from telethon.tl.types import MessageEntityCustomEmoji

    entities = []
    for start, end, custom_id in spans:
        if not str(custom_id).isdigit():
            continue
        entities.append(MessageEntityCustomEmoji(
            offset=utf16_len(text[:start]),
            length=utf16_len(text[start:end]),
            document_id=int(custom_id),
        ))
    return entities


async def edit_via_user(
    chat_id: int,
    message_id: int,
    text: str,
    spans: list[tuple[int, int, str]],
) -> dict:
    client = await get_user_client()
    if client is None:
        return {"ok": False, "error": "user_session_not_configured"}
    try:
        entities = _entities(text, spans) if spans else None
        await client.edit_message(chat_id, message_id, text, formatting_entities=entities)
        return {"ok": True, "method": "user_session"}
    except Exception as exc:
        message = str(exc)
        lowered = message.lower()
        if "not modified" in lowered or "message was not modified" in lowered:
            return {"ok": True, "method": "user_session", "warning": "not_modified"}
        logger.warning("User-session edit failed: %s", message)
        return {"ok": False, "error": message, "method": "user_session"}


async def user_session_status() -> dict:
    settings = get_settings()
    configured = session_configured()
    if not configured:
        return {"configured": False, "authorized": False}
    client = await get_user_client()
    if client is None:
        return {"configured": True, "authorized": False, "api_id_set": bool(settings.tg_api_id)}
    me = await client.get_me()
    return {
        "configured": True,
        "authorized": True,
        "user_id": getattr(me, "id", None),
        "username": getattr(me, "username", None),
        "premium": bool(getattr(me, "premium", False)),
    }
