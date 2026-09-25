"""Read recent public posts through the saved premium session."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def read_channel_posts(username: str, *, min_id: int = 0, limit: int = 8) -> tuple[list[dict], str | None]:
    from backend.app.telegram.user_editor import get_user_client

    client = await get_user_client()
    if client is None:
        return [], "نشست پرمیوم وصل نیست"
    try:
        entity = await client.get_entity(username)
    except Exception as exc:
        logger.info("source resolve failed: %s", type(exc).__name__)
        return [], "این کانال با نشست فعلی باز نشد. کانال باید عمومی باشد یا اکانت عضو آن باشد"
    found: list[dict] = []
    try:
        async for message in client.iter_messages(entity, limit=limit, min_id=min_id or 0):
            text = (getattr(message, "message", None) or "").strip()
            if len(text) < 40:
                continue
            found.append({
                "id": int(message.id),
                "text": text[:1800],
                "title": getattr(entity, "title", None) or username,
            })
    except Exception as exc:
        logger.info("source read failed: %s", type(exc).__name__)
        return found, "خواندن پیام‌های کانال انجام نشد"
    return found, None
