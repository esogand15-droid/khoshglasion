"""Premium-emoji editor through a human account that can edit the channel.

Bot API custom emoji is documented for private, group and supergroup messages
the bot sends. Channel posts use this user session instead. Credentials come
from the panel store when that store has been written, otherwise from the
environment. The session string is never logged.
"""
from __future__ import annotations

import logging

from backend.app.core.config import get_settings
from backend.app.formatting.emoji import custom_emoji_span_valid
from backend.app.formatting.textutil import utf16_len

logger = logging.getLogger(__name__)

_clients: dict[str, object] = {}
_client_sessions: dict[str, str] = {}
_override: dict[str, str] | None = None


def set_credential_override(api_id: str, api_hash: str, session: str) -> None:
    global _override
    _override = {
        "api_id": str(api_id or "").strip(),
        "api_hash": str(api_hash or "").strip(),
        "session": str(session or "").strip(),
    }


def clear_credential_override() -> None:
    global _override
    _override = None


def current_credentials() -> tuple[str, str, str]:
    if _override is not None:
        return _override["api_id"], _override["api_hash"], _override["session"]
    settings = get_settings()
    return settings.tg_api_id, settings.tg_api_hash, settings.tg_session_string


def session_configured() -> bool:
    api_id, api_hash, session = current_credentials()
    return bool(api_id and api_hash and session)


async def _connect(key: str, api_id: str, api_hash: str, session: str):
    if not (api_id and api_hash and session):
        return None
    existing = _clients.get(key)
    if existing is not None and _client_sessions.get(key) == session and getattr(existing, "is_connected", lambda: False)():
        return existing
    if existing is not None:
        try:
            await existing.disconnect()
        except Exception:
            pass
        _clients.pop(key, None)
        _client_sessions.pop(key, None)
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError:
        logger.warning("telethon is not installed; user-session premium editor disabled")
        return None
    try:
        client = TelegramClient(StringSession(session), int(api_id), api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            logger.error("Stored user session is not authorized")
            await client.disconnect()
            return None
        _clients[key] = client
        _client_sessions[key] = session
        return client
    except Exception as exc:
        logger.error("Could not start user session: %s", type(exc).__name__)
        return None


async def get_user_client():
    from backend.app.telegram.accounts import pick_emoji

    picked = pick_emoji()
    if picked:
        return await _connect(picked["id"], picked["api_id"], picked["api_hash"], picked["session"])
    api_id, api_hash, session = current_credentials()
    return await _connect("legacy", api_id, api_hash, session)


async def get_news_client():
    from backend.app.telegram.accounts import pick_news

    picked = pick_news()
    if picked:
        return await _connect(picked["id"], picked["api_id"], picked["api_hash"], picked["session"])
    return await get_user_client()


async def close_user_client() -> None:
    for client in list(_clients.values()):
        try:
            await client.disconnect()
        except Exception:
            pass
    _clients.clear()
    _client_sessions.clear()


def _entities(text: str, spans: list[tuple[int, int, str]] | None = None, formatted: list[dict] | None = None):
    from telethon.tl.types import (
        MessageEntityBlockquote,
        MessageEntityBold,
        MessageEntityCode,
        MessageEntityCustomEmoji,
        MessageEntityItalic,
        MessageEntityPre,
        MessageEntitySpoiler,
        MessageEntityStrike,
        MessageEntityTextUrl,
        MessageEntityUnderline,
    )

    built = []
    if formatted:
        for item in formatted:
            start = int(item.get("offset") or 0)
            length = int(item.get("length") or 0)
            if length <= 0:
                continue
            offset = utf16_len(text[:start])
            utf_length = utf16_len(text[start:start + length])
            if utf_length <= 0:
                continue
            kind = item.get("type")
            if kind == "custom_emoji" and str(item.get("custom_emoji_id") or "").isdigit():
                built.append(MessageEntityCustomEmoji(offset=offset, length=utf_length, document_id=int(item["custom_emoji_id"])))
            elif kind == "text_link" and item.get("url"):
                built.append(MessageEntityTextUrl(offset=offset, length=utf_length, url=str(item["url"])))
            elif kind == "blockquote":
                built.append(MessageEntityBlockquote(offset=offset, length=utf_length, collapsed=False))
            elif kind == "expandable_blockquote":
                built.append(MessageEntityBlockquote(offset=offset, length=utf_length, collapsed=True))
            elif kind == "bold":
                built.append(MessageEntityBold(offset=offset, length=utf_length))
            elif kind == "italic":
                built.append(MessageEntityItalic(offset=offset, length=utf_length))
            elif kind == "underline":
                built.append(MessageEntityUnderline(offset=offset, length=utf_length))
            elif kind == "strikethrough":
                built.append(MessageEntityStrike(offset=offset, length=utf_length))
            elif kind == "spoiler":
                built.append(MessageEntitySpoiler(offset=offset, length=utf_length))
            elif kind == "code":
                built.append(MessageEntityCode(offset=offset, length=utf_length))
            elif kind == "pre":
                language = str(item.get("language") or "")
                if not language.replace("+", "").replace("-", "").replace("_", "").isalnum():
                    language = ""
                built.append(MessageEntityPre(offset=offset, length=utf_length, language=language[:32]))
        return built
    for start, end, custom_id in spans or []:
        if not str(custom_id).isdigit():
            continue
        built.append(MessageEntityCustomEmoji(
            offset=utf16_len(text[:start]),
            length=utf16_len(text[start:end]),
            document_id=int(custom_id),
        ))
    return built


def _reject_broken_emoji(text: str, entities: list[dict] | None) -> str | None:
    for item in entities or []:
        if item.get("type") != "custom_emoji":
            continue
        start = int(item.get("offset") or 0)
        length = int(item.get("length") or 0)
        if not custom_emoji_span_valid(text, start, length):
            return "custom_emoji_length_invalid"
    return None


async def edit_via_user(
    chat_id: int,
    message_id: int,
    text: str,
    spans: list[tuple[int, int, str]] | None = None,
    entities: list[dict] | None = None,
) -> dict:
    broken = _reject_broken_emoji(text, entities)
    if not broken and not entities:
        for start, end, _custom_id in spans or []:
            if not custom_emoji_span_valid(text, start, end - start):
                broken = "custom_emoji_length_invalid"
                break
    if broken:
        return {"ok": False, "error": broken, "method": "user_session", "emoji_rejected": True}
    client = await get_user_client()
    if client is None:
        return {"ok": False, "error": "user_session_not_configured"}
    try:
        formatting = _entities(text, spans, entities) if (entities or spans) else None
        await client.edit_message(chat_id, message_id, text, formatting_entities=formatting or None)
        return {"ok": True, "method": "user_session"}
    except Exception as exc:
        message = str(exc)
        lowered = message.lower()
        if "not modified" in lowered or "message was not modified" in lowered:
            return {"ok": True, "method": "user_session", "warning": "not_modified"}
        logger.warning("User-session edit failed: %s", message)
        return {"ok": False, "error": message, "method": "user_session"}


async def delete_via_user(chat_id: int, message_id: int) -> dict:
    client = await get_user_client()
    if client is None:
        return {"ok": False, "error": "user_session_not_configured"}
    try:
        await client.delete_messages(int(chat_id), [int(message_id)])
        return {"ok": True, "method": "user_session"}
    except Exception as exc:
        logger.warning("User-session delete failed: %s", type(exc).__name__)
        return {"ok": False, "error": type(exc).__name__}


async def send_via_user(chat_id: int, text: str, entities: list[dict] | None = None) -> dict:
    """Send a channel post with library emoji entities. Never logs the session."""
    broken = _reject_broken_emoji(text, entities)
    if broken:
        return {"ok": False, "error": broken, "method": "user_session", "emoji_rejected": True}
    client = await get_user_client()
    if client is None:
        return {"ok": False, "error": "user_session_not_configured"}
    try:
        formatting = _entities(text, None, entities) if entities else None
        sent = await client.send_message(int(chat_id), text[:4000], formatting_entities=formatting or None)
        return {"ok": True, "message_id": int(sent.id), "method": "user_session"}
    except Exception as exc:
        logger.warning("User-session send failed: %s", type(exc).__name__)
        return {"ok": False, "error": type(exc).__name__, "method": "user_session"}


async def send_photo_via_user(chat_id: int, caption: str, entities: list[dict] | None, photo_path: str) -> dict:
    """Send the source photo with a caption. Premium emoji stays on the caption, never as unicode."""
    broken = _reject_broken_emoji(caption, entities)
    if broken:
        return {"ok": False, "error": broken, "method": "user_session", "emoji_rejected": True}
    client = await get_user_client()
    if client is None:
        return {"ok": False, "error": "user_session_not_configured"}
    try:
        from io import BytesIO
        from pathlib import Path

        from backend.app.content.intake import photo_bytes_for_telegram

        payload, name = photo_bytes_for_telegram(Path(photo_path))
        blob = BytesIO(payload)
        blob.name = name
        formatting = _entities(caption, None, entities) if entities else None
        sent = await client.send_file(
            int(chat_id),
            blob,
            caption=(caption or "")[:1024],
            formatting_entities=formatting or None,
            force_document=False,
        )
        return {"ok": True, "message_id": int(sent.id), "method": "user_session"}
    except Exception as exc:
        logger.warning("User-session photo send failed: %s", type(exc).__name__)
        return {"ok": False, "error": type(exc).__name__, "method": "user_session"}


async def user_session_status() -> dict:
    api_id, _api_hash, _session = current_credentials()
    configured = session_configured()
    if not configured:
        return {"configured": False, "authorized": False, "api_id_set": bool(api_id)}
    client = await get_user_client()
    if client is None:
        return {"configured": True, "authorized": False, "api_id_set": bool(api_id)}
    me = await client.get_me()
    return {
        "configured": True,
        "authorized": True,
        "user_id": getattr(me, "id", None),
        "username": getattr(me, "username", None),
        "premium": bool(getattr(me, "premium", False)),
    }
