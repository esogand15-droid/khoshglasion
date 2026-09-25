"""Read new posts through the saved premium session, oldest first.

The session only opens channels it can already see. It does not join invites.
A full page means older unread ids may still remain, so the caller must not
jump the cursor to the newest id.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def read_channel_posts(username: str, *, min_id: int = 0, limit: int = 40) -> tuple[list[dict], str | None, bool]:
    from backend.app.telegram.user_editor import get_user_client

    client = await get_user_client()
    if client is None:
        return [], "نشست پرمیوم وصل نیست", False
    try:
        entity = await client.get_entity(username)
    except Exception as exc:
        logger.info("source resolve failed: %s", type(exc).__name__)
        return [], "این کانال با نشست فعلی باز نشد. کانال باید عمومی باشد یا اکانت عضو آن باشد", False
    found: list[dict] = []
    scanned = 0
    try:
        async for message in client.iter_messages(entity, limit=limit, min_id=min_id or 0, reverse=True):
            scanned += 1
            text = (getattr(message, "message", None) or getattr(message, "text", None) or "").strip()
            has_media = bool(
                getattr(message, "photo", None)
                or getattr(message, "video", None)
                or getattr(message, "document", None)
                or getattr(message, "grouped_id", None)
            )
            found.append({
                "id": int(message.id),
                "text": text[:1800],
                "title": getattr(entity, "title", None) or username,
                "date": getattr(message, "date", None),
                "has_media": has_media,
                "usable": len(text) >= 40 or (has_media and len(text) >= 20),
            })
    except Exception as exc:
        logger.info("source read failed: %s", type(exc).__name__)
        return found, "خواندن پیام‌های کانال انجام نشد", True
    found.sort(key=lambda item: item["id"])
    return found, None, scanned >= limit


async def probe_channel(username: str) -> tuple[dict, str | None]:
    """Check that the saved session can already open this channel. Does not join."""
    from backend.app.telegram.user_editor import get_user_client

    client = await get_user_client()
    if client is None:
        return {}, "نشست پرمیوم وصل نیست"
    try:
        entity = await client.get_entity(username)
    except Exception as exc:
        logger.info("source probe failed: %s", type(exc).__name__)
        return {}, "این کانال با نشست فعلی باز نشد. کانال باید عمومی باشد یا اکانت عضو آن باشد"
    latest = None
    try:
        async for message in client.iter_messages(entity, limit=1):
            latest = int(message.id)
            break
    except Exception as exc:
        logger.info("source probe read failed: %s", type(exc).__name__)
        return {"title": getattr(entity, "title", None), "username": getattr(entity, "username", None)}, "خواندن پیام آزمایشی انجام نشد"
    return {
        "title": getattr(entity, "title", None),
        "username": getattr(entity, "username", None),
        "latest_id": latest,
    }, None
