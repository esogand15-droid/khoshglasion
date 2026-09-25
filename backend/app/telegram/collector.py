"""Read public news channels through the news session, oldest first.

A public username may be joined with JoinChannelRequest so the account can
read it. Invite links and private channels are refused. A full page means
older unread ids may still remain, so the caller must not jump the cursor
to the newest id.
"""
from __future__ import annotations

import logging
import re
import time

logger = logging.getLogger(__name__)
_PUBLIC = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")
_joins: list[float] = []


def _public_name(username: str) -> bool:
    return bool(_PUBLIC.fullmatch(username or ""))


def _allow_join() -> bool:
    now = time.monotonic()
    _joins[:] = [item for item in _joins if now - item < 60]
    if len(_joins) >= 8:
        return False
    _joins.append(now)
    return True


async def _news_client():
    from backend.app.telegram.user_editor import get_news_client

    return await get_news_client()


async def join_public_channel(client, username: str) -> str | None:
    """Join a public channel. Returns a Persian error, or None on success."""
    if not _public_name(username):
        return "فقط یوزرنیم کانال عمومی قابل عضویت است. لینک دعوت خصوصی قبول نیست"
    if not _allow_join():
        return "برای جلوگیری از محدودیت تلگرام، بقیهٔ عضویت‌ها را کمی بعد تکرار کن."
    try:
        entity = await client.get_entity(username)
    except Exception as exc:
        logger.info("public resolve failed: %s", type(exc).__name__)
        return "این یوزرنیم عمومی پیدا نشد"
    if not getattr(entity, "username", None):
        return "این کانال عمومی نیست. لینک دعوت خصوصی قبول نیست"
    try:
        from telethon.tl.functions.channels import JoinChannelRequest

        await client(JoinChannelRequest(entity))
    except Exception as exc:
        name = type(exc).__name__
        if name == "UserAlreadyParticipantError":
            return None
        logger.info("public join failed: %s", name)
        if name == "FloodWaitError":
            seconds = getattr(exc, "seconds", None)
            if isinstance(seconds, int) and 0 < seconds < 3600:
                return f"تلگرام گفته {seconds} ثانیه صبر کن، بعد دوباره عضو شو."
            return "تلگرام عضویت را موقتاً محدود کرده."
        if name in {"ChannelPrivateError", "ChannelInvalidError"}:
            return "این کانال عمومی نیست. لینک دعوت خصوصی قبول نیست"
        if name == "ChannelsTooMuchError":
            return "این اکانت به سقف کانال‌های تلگرام رسیده."
        if name == "InviteRequestSentError":
            return "این کانال عضویت را باید تأیید کند. جوین خودکار ممکن نیست."
        return "عضویت در کانال عمومی انجام نشد"
    return None


async def _entity(client, username: str):
    from backend.app.telegram.accounts import news_may_join

    try:
        return await client.get_entity(username), None
    except Exception as exc:
        logger.info("source resolve failed: %s", type(exc).__name__)
        if not (_public_name(username) and news_may_join()):
            return None, "این کانال با اکانت خبر باز نشد. کانال باید عمومی باشد یا اکانت از قبل عضو آن باشد"
        joined = await join_public_channel(client, username)
        if joined:
            return None, joined
        try:
            return await client.get_entity(username), None
        except Exception as nested:
            logger.info("source resolve after join failed: %s", type(nested).__name__)
            return None, "بعد از عضویت هم این کانال عمومی باز نشد"


async def _messages(client, entity, username: str, *, min_id: int, limit: int):
    from backend.app.telegram.accounts import news_may_join

    async def collect():
        found: list[dict] = []
        scanned = 0
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
        found.sort(key=lambda item: item["id"])
        return found, scanned

    try:
        found, scanned = await collect()
        return found, None, scanned >= limit
    except Exception as exc:
        logger.info("source read failed: %s", type(exc).__name__)
        if _public_name(username) and news_may_join():
            joined = await join_public_channel(client, username)
            if joined is None:
                try:
                    found, scanned = await collect()
                    return found, None, scanned >= limit
                except Exception as nested:
                    logger.info("source reread failed: %s", type(nested).__name__)
        return [], "خواندن پیام‌های کانال انجام نشد", True


async def read_channel_posts(username: str, *, min_id: int = 0, limit: int = 40) -> tuple[list[dict], str | None, bool]:
    client = await _news_client()
    if client is None:
        return [], "نشست خبر یا پرمیوم وصل نیست. از تنظیمات، تب نشست، یک اکانت با نقش خبر یا هر دو وصل کن", False
    entity, error = await _entity(client, username)
    if error or entity is None:
        return [], error or "این کانال باز نشد", False
    return await _messages(client, entity, username, min_id=min_id, limit=limit)


async def probe_channel(username: str) -> tuple[dict, str | None]:
    """Open a public source. Joins a public username when the news account is allowed to."""
    client = await _news_client()
    if client is None:
        return {}, "نشست خبر یا پرمیوم وصل نیست. از تنظیمات، تب نشست، یک اکانت با نقش خبر یا هر دو وصل کن"
    entity, error = await _entity(client, username)
    if error or entity is None:
        return {}, error or "این کانال باز نشد"
    latest = None
    try:
        async for message in client.iter_messages(entity, limit=1):
            latest = int(message.id)
            break
    except Exception as exc:
        logger.info("source probe read failed: %s", type(exc).__name__)
        if _public_name(username):
            joined = await join_public_channel(client, username)
            if joined:
                return {"title": getattr(entity, "title", None), "username": getattr(entity, "username", None)}, joined
        return {"title": getattr(entity, "title", None), "username": getattr(entity, "username", None)}, "خواندن پیام آزمایشی انجام نشد"
    return {
        "title": getattr(entity, "title", None),
        "username": getattr(entity, "username", None),
        "latest_id": latest,
    }, None


async def subscribe_public(db, raw: str) -> str:
    from sqlalchemy import select

    from backend.app.models.automation import NewsSource
    from backend.app.services.autopost import normalize_source
    from backend.app.telegram.session_login import refresh_user_credentials

    username = normalize_source(raw or "")
    if not username:
        return "فقط یوزرنیم کانال عمومی. لینک دعوت خصوصی قبول نیست."
    if username.lstrip("-").isdigit():
        return "برای عضویت خودکار یوزرنیم عمومی لازم است، نه آیدی عددی."
    await refresh_user_credentials(db)
    row = (await db.execute(select(NewsSource).where(NewsSource.username == username))).scalar_one_or_none()
    if row is None:
        row = NewsSource(username=username, enabled=True)
        db.add(row)
    else:
        row.enabled = True
    info, error = await probe_channel(username)
    row.title = info.get("title") or row.title
    row.last_error = error
    if not error and info.get("latest_id"):
        row.last_message_id = int(info["latest_id"])
    await db.flush()
    if error:
        return f"منبع ثبت شد ولی خوانده نشد: {error}"
    title = row.title or username
    return f"عضو شد و منبع خبر ثبت شد: {title}"


async def join_enabled_sources(db) -> dict:
    from sqlalchemy import select

    from backend.app.models.automation import NewsSource
    from backend.app.telegram.session_login import refresh_user_credentials

    await refresh_user_credentials(db)
    rows = (await db.execute(select(NewsSource).where(NewsSource.enabled == True))).scalars().all()  # noqa: E712
    joined = 0
    failed: list[str] = []
    for row in rows[:15]:
        if not _public_name(row.username):
            continue
        info, error = await probe_channel(row.username)
        row.title = info.get("title") or row.title
        row.last_error = error
        if error:
            failed.append(f"{row.username}: {error}")
            if "صبر کن" in error or "محدود" in error:
                break
        else:
            joined += 1
            if info.get("latest_id") and not row.last_message_id:
                row.last_message_id = int(info["latest_id"])
    await db.flush()
    return {
        "ok": True,
        "joined": joined,
        "failed": failed[:8],
        "message": f"عضویت بررسی شد: {joined} کانال" + (f" · {len(failed)} خطا" if failed else ""),
    }
