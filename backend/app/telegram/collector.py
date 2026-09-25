"""Read news channels through the news session, oldest first.

A public username may be joined with JoinChannelRequest so the account can
read it. A private invite is accepted only when that same news account is
already a member: CheckChatInviteRequest returns the chat, and the channel id
is stored. The invite is never used to join. A full page means older unread
ids may still remain, so the caller must not jump the cursor to the newest id.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time

logger = logging.getLogger(__name__)
_PUBLIC = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")
_joins: list[float] = []
_NO_SESSION = "نشست خبر یا پرمیوم وصل نیست. از تنظیمات، تب نشست، یک اکانت با نقش خبر یا هر دو وصل کن"
_READ_FAILED = "خواندن پیام‌های کانال انجام نشد"


def _public_name(username: str) -> bool:
    return bool(_PUBLIC.fullmatch(username or ""))


def _allow_join() -> bool:
    now = time.monotonic()
    _joins[:] = [item for item in _joins if now - item < 60]
    if len(_joins) >= 8:
        return False
    _joins.append(now)
    return True


def _news_who() -> str:
    try:
        from backend.app.telegram.accounts import pick_news

        username = ((pick_news() or {}).get("username") or "").lstrip("@")
    except Exception:
        return ""
    return f"@{username}" if username else ""


def _not_member() -> str:
    who = _news_who()
    label = f" ({who})" if who else ""
    return (
        f"این اکانت خبری{label} هنوز عضو این کانال خصوصی نیست. "
        "اول با همان اکانت در تلگرام عضو شو، بعد لینک را دوباره بگذار. جوین خودکار انجام نمی‌شود."
    )


def _marked_id(chat) -> int | None:
    raw = getattr(chat, "id", None)
    if raw is None:
        return None
    try:
        from telethon import utils

        return int(utils.get_peer_id(chat))
    except Exception:
        raw = int(raw)
        kind = type(chat).__name__
        channel = (
            kind == "Channel"
            or bool(getattr(chat, "broadcast", False))
            or bool(getattr(chat, "megagroup", False))
            or getattr(chat, "access_hash", None) is not None
        )
        if channel:
            return raw if raw < 0 else -(1_000_000_000_000 + raw)
        return raw if raw < 0 else -raw


def _stored_peer(username: str, access_hash: int | None):
    try:
        marked = int(str(username))
    except (TypeError, ValueError):
        return None
    from telethon import utils
    from telethon.tl.types import InputPeerChannel, InputPeerChat, PeerChannel, PeerChat

    bare, kind = utils.resolve_id(marked)
    if kind is PeerChannel:
        if access_hash is None:
            return None
        return InputPeerChannel(int(bare), int(access_hash))
    if kind is PeerChat:
        return InputPeerChat(int(bare))
    return None


def _apply_updates(updates: dict | None, resolved: dict) -> None:
    if updates is None:
        return
    if resolved.get("access_hash") is not None:
        updates["access_hash"] = int(resolved["access_hash"])
    if resolved.get("title"):
        updates["title"] = resolved["title"]


def _cache_invite(client, result) -> None:
    session = getattr(client, "session", None)
    process = getattr(session, "process_entities", None)
    if not process:
        return
    try:
        process(result)
    except Exception as exc:
        logger.info("invite cache skipped: %s", type(exc).__name__)


async def _news_client():
    from backend.app.telegram.user_editor import get_news_client

    return await get_news_client()


async def resolve_joined_invite(client, invite_hash: str) -> tuple[dict | None, str | None]:
    """Resolve a private invite only if the news account is already inside.

    Never joins. A link the account has not accepted is refused.
    """
    from telethon.tl.functions.messages import CheckChatInviteRequest

    try:
        result = await client(CheckChatInviteRequest(invite_hash))
    except Exception as exc:
        name = type(exc).__name__
        logger.info("invite check failed: %s", name)
        if name in {"InviteHashExpiredError", "InviteHashInvalidError", "InviteHashEmptyError"}:
            return None, "این لینک دعوت معتبر نیست یا منقضی شده. اگر اکانت خبر هنوز عضو است، یک لینک تازه بگذار."
        if name == "FloodWaitError":
            seconds = getattr(exc, "seconds", None)
            if isinstance(seconds, int) and 0 < seconds < 3600:
                return None, f"تلگرام گفته {seconds} ثانیه صبر کن، بعد لینک را دوباره بگذار."
            return None, "تلگرام بررسی لینک را موقتاً محدود کرده."
        return None, "بررسی لینک دعوت انجام نشد."
    chat = getattr(result, "chat", None)
    kind = type(chat).__name__ if chat is not None else ""
    if type(result).__name__ != "ChatInviteAlready" or chat is None or kind in {"ChannelForbidden", "ChatForbidden"}:
        return None, _not_member()
    marked = _marked_id(chat)
    if marked is None:
        return None, "این لینک به کانال قابل خواندن وصل نشد."
    _cache_invite(client, result)
    public = getattr(chat, "username", None)
    if not isinstance(public, str) or not _public_name(public):
        public = None
    access = getattr(chat, "access_hash", None)
    return {
        "username": public or str(marked),
        "title": getattr(chat, "title", None),
        "access_hash": None if access is None else int(access),
        "public": public is not None,
        "chat": chat,
    }, None


async def join_public_channel(client, username: str) -> str | None:
    """Join a public channel. Returns a Persian error, or None on success."""
    if not _public_name(username):
        return "فقط یوزرنیم کانال عمومی قابل عضویت است. لینک خصوصی جوین نمی‌شود"
    if not _allow_join():
        return "برای جلوگیری از محدودیت تلگرام، بقیهٔ عضویت‌ها را کمی بعد تکرار کن."
    try:
        entity = await client.get_entity(username)
    except Exception as exc:
        logger.info("public resolve failed: %s", type(exc).__name__)
        return "این یوزرنیم عمومی پیدا نشد"
    if not getattr(entity, "username", None):
        return "این کانال عمومی نیست. لینک خصوصی جوین نمی‌شود؛ اگر از قبل عضوی، لینک را در منابع بگذار"
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
            return "این کانال عمومی نیست. لینک خصوصی جوین نمی‌شود؛ اگر از قبل عضوی، لینک را در منابع بگذار"
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
            return None, "این کانال با اکانت خبر باز نشد. اگر خصوصی است و از قبل عضوی، لینک دعوت را در منابع بگذار"
        joined = await join_public_channel(client, username)
        if joined:
            return None, joined
        try:
            return await client.get_entity(username), None
        except Exception as nested:
            logger.info("source resolve after join failed: %s", type(nested).__name__)
            return None, "بعد از عضویت هم این کانال عمومی باز نشد"


async def _open_source(client, username: str, *, access_hash: int | None = None, invite_hash: str | None = None, updates: dict | None = None):
    peer = _stored_peer(username, access_hash)
    if peer is not None:
        return peer, None
    if invite_hash and not _public_name(username):
        resolved, error = await resolve_joined_invite(client, invite_hash)
        if error or not resolved:
            return None, error or "این کانال خصوصی باز نشد"
        _apply_updates(updates, resolved)
        return resolved["chat"], None
    return await _entity(client, username)


def _is_image_message(message) -> bool:
    if getattr(message, "photo", None):
        return True
    document = getattr(message, "document", None)
    if document is None:
        return False
    mime = (getattr(document, "mime_type", None) or "").lower()
    if mime.startswith("image/") and "svg" not in mime:
        return True
    for attr in getattr(document, "attributes", None) or []:
        name = (getattr(attr, "file_name", None) or "").lower()
        if name.endswith((".jpg", ".jpeg", ".png", ".webp")):
            return True
    return False


def _is_video_message(message) -> bool:
    if getattr(message, "video", None):
        return True
    document = getattr(message, "document", None)
    if document is None:
        return False
    mime = (getattr(document, "mime_type", None) or "").lower()
    return mime.startswith("video/")


def _poll_text(message) -> str:
    poll = getattr(message, "poll", None)
    if poll is None:
        media = getattr(message, "media", None)
        poll = getattr(media, "poll", None) if media is not None else None
    if poll is None:
        return ""
    question = getattr(poll, "question", None)
    if hasattr(question, "text"):
        question = question.text
    lines = [str(question or "").strip()]
    for answer in getattr(poll, "answers", None) or []:
        label = getattr(answer, "text", None)
        if hasattr(label, "text"):
            label = label.text
        label = str(label or "").strip()
        if label:
            lines.append(f"- {label}")
    return "\n".join(line for line in lines if line)


async def _save_video(client, message, username: str) -> str | None:
    if not _is_video_message(message):
        return None
    try:
        raw = await asyncio.wait_for(client.download_media(message, bytes), timeout=20)
    except Exception as exc:
        logger.info("video download skipped: %s", type(exc).__name__)
        return None
    if not isinstance(raw, (bytes, bytearray)):
        return None
    from backend.app.content.intake import save_source_video

    return save_source_video(f"{username}:{int(message.id)}:video", bytes(raw))


async def _save_photo(client, message, username: str) -> str | None:
    if not _is_image_message(message):
        return None
    try:
        raw = await asyncio.wait_for(client.download_media(message, bytes), timeout=8)
    except Exception as exc:
        logger.info("photo download skipped: %s", type(exc).__name__)
        return None
    if not isinstance(raw, (bytes, bytearray)):
        return None
    from backend.app.content.intake import save_source_photo

    return save_source_photo(f"{username}:{int(message.id)}", bytes(raw))


async def _download_message_photo(client, entity, message_id: int, key: str) -> str | None:
    try:
        message = await asyncio.wait_for(client.get_messages(entity, ids=int(message_id)), timeout=12)
    except Exception as exc:
        logger.info("photo refetch skipped: %s", type(exc).__name__)
        return None
    if message is None:
        return None
    saved = await _save_photo(client, message, key)
    if saved:
        return saved
    grouped = getattr(message, "grouped_id", None)
    if not grouped:
        return None
    try:
        nearby = await asyncio.wait_for(
            client.get_messages(entity, limit=8, max_id=int(message_id) + 4, min_id=max(0, int(message_id) - 5)),
            timeout=12,
        )
    except Exception as exc:
        logger.info("album refetch skipped: %s", type(exc).__name__)
        return None
    for item in nearby or []:
        if getattr(item, "grouped_id", None) != grouped:
            continue
        saved = await _save_photo(client, item, key)
        if saved:
            return saved
    return None


async def _open_known(client, username: str, access_hash: int | None, invite_hash: str | None):
    """Open a source the account can already read. Never joins a channel."""
    peer = _stored_peer(username, access_hash)
    if peer is not None:
        return peer
    if invite_hash and not _public_name(username):
        resolved, error = await resolve_joined_invite(client, invite_hash)
        if error or not resolved:
            return None
        return resolved["chat"]
    try:
        return await client.get_entity(username)
    except Exception as exc:
        logger.info("known source open skipped: %s", type(exc).__name__)
        return None


async def refetch_source_photo(
    username: str,
    message_id: int,
    *,
    access_hash: int | None = None,
    invite_hash: str | None = None,
) -> str | None:
    client = await _news_client()
    if client is None:
        return None
    entity = await _open_known(client, username, access_hash, invite_hash)
    if entity is None:
        return None
    return await _download_message_photo(client, entity, message_id, username)


async def refetch_published_photo(chat_id: int, message_id: int, key: str) -> str | None:
    photos = await refetch_published_photos(chat_id, message_id, key)
    return photos[0] if photos else None


async def _download_album(client, entity, message_id: int, key: str) -> list[str]:
    try:
        message = await asyncio.wait_for(client.get_messages(entity, ids=int(message_id)), timeout=10)
    except Exception as exc:
        logger.info("album refetch skipped: %s", type(exc).__name__)
        return []
    if message is None:
        return []
    messages = [message]
    grouped = getattr(message, "grouped_id", None)
    if grouped:
        try:
            nearby = await asyncio.wait_for(
                client.get_messages(entity, limit=10, max_id=int(message_id) + 6, min_id=max(0, int(message_id) - 6)),
                timeout=10,
            )
        except Exception as exc:
            logger.info("album nearby skipped: %s", type(exc).__name__)
            nearby = []
        grouped_messages = [item for item in nearby or [] if getattr(item, "grouped_id", None) == grouped]
        if grouped_messages:
            messages = sorted(grouped_messages, key=lambda item: int(item.id))
    paths: list[str] = []
    for item in messages:
        saved = await _save_photo(client, item, key)
        if saved and saved not in paths:
            paths.append(saved)
    return paths


async def refetch_source_photos(
    username: str,
    message_id: int,
    *,
    access_hash: int | None = None,
    invite_hash: str | None = None,
) -> list[str]:
    client = await _news_client()
    if client is None:
        return []
    entity = await _open_known(client, username, access_hash, invite_hash)
    if entity is None:
        return []
    return await _download_album(client, entity, message_id, username)


async def refetch_published_photos(chat_id: int, message_id: int, key: str) -> list[str]:
    from backend.app.telegram.user_editor import get_news_client, get_user_client

    for opener in (get_user_client, get_news_client):
        try:
            client = await opener()
        except Exception:
            client = None
        if client is None:
            continue
        saved = await _download_album(client, int(chat_id), message_id, key or "published")
        if saved:
            return saved
    return []


async def _messages(client, entity, username: str, *, min_id: int, limit: int, title: str | None = None, recent: bool = False):
    from backend.app.telegram.accounts import news_may_join

    label = title or getattr(entity, "title", None) or username

    async def collect():
        found: list[dict] = []
        albums: dict[int, list[str]] = {}
        scanned = 0
        kwargs = {"limit": limit}
        if not recent:
            kwargs["min_id"] = min_id or 0
            kwargs["reverse"] = True
        async for message in client.iter_messages(entity, **kwargs):
            scanned += 1
            text = (getattr(message, "message", None) or getattr(message, "text", None) or "").strip()
            poll_text = _poll_text(message)
            if poll_text and poll_text not in text:
                text = f"{text}\n{poll_text}".strip() if text else poll_text
            image = _is_image_message(message)
            video = _is_video_message(message)
            has_media = bool(
                image
                or video
                or poll_text
                or getattr(message, "document", None)
                or getattr(message, "grouped_id", None)
            )
            photo_path = await _save_photo(client, message, username) if image else None
            video_path = await _save_video(client, message, username) if video and not photo_path else None
            grouped = getattr(message, "grouped_id", None)
            if photo_path and grouped:
                albums.setdefault(int(grouped), [])
                if photo_path not in albums[int(grouped)]:
                    albums[int(grouped)].append(photo_path)
            kind = "poll" if poll_text else "video" if video_path else "photo" if photo_path else ""
            found.append({
                "id": int(message.id),
                "text": text[:1800],
                "title": label,
                "date": getattr(message, "date", None),
                "has_media": has_media,
                "photo_path": photo_path,
                "photo_paths": [photo_path] if photo_path else [],
                "video_path": video_path,
                "media_kind": kind,
                "grouped_id": grouped,
                "usable": len(text) >= 40 or (has_media and len(text) >= 12),
            })
        captioned = {int(item["grouped_id"]) for item in found if item.get("grouped_id") and item.get("text")}
        for item in found:
            grouped = item.get("grouped_id")
            if not grouped or int(grouped) not in albums:
                continue
            item["photo_paths"] = list(albums[int(grouped)])
            item["photo_path"] = item["photo_paths"][0]
            item["has_media"] = True
            if len(item["photo_paths"]) > 1:
                item["media_kind"] = "album"
            if int(grouped) in captioned and not item.get("text"):
                item["usable"] = False
        found.sort(key=lambda item: item["id"])
        return found, scanned

    try:
        found, scanned = await collect()
        return found, None, (not recent and scanned >= limit)
    except Exception as exc:
        logger.info("source read failed: %s", type(exc).__name__)
        if _public_name(username) and news_may_join():
            joined = await join_public_channel(client, username)
            if joined is None:
                try:
                    found, scanned = await collect()
                    return found, None, (not recent and scanned >= limit)
                except Exception as nested:
                    logger.info("source reread failed: %s", type(nested).__name__)
        if not _public_name(username):
            return [], "خواندن پیام‌های این کانال خصوصی انجام نشد. اگر اکانت خبر هنوز عضو است، لینک دعوت را دوباره در منابع بگذار.", True
        return [], _READ_FAILED, True


async def _reread_joined(client, username: str, invite_hash: str | None, access_hash: int | None, updates: dict | None):
    if not invite_hash or _public_name(username) or _stored_peer(username, access_hash) is None:
        return None, None
    resolved, error = await resolve_joined_invite(client, invite_hash)
    if error or not resolved:
        return None, error or "این کانال خصوصی باز نشد"
    _apply_updates(updates, resolved)
    return resolved, None


async def read_channel_posts(
    username: str,
    *,
    min_id: int = 0,
    limit: int = 40,
    access_hash: int | None = None,
    invite_hash: str | None = None,
    updates: dict | None = None,
    title: str | None = None,
    recent: bool = False,
) -> tuple[list[dict], str | None, bool]:
    try:
        return await asyncio.wait_for(
            _read_channel_posts(
                username,
                min_id=min_id,
                limit=limit,
                access_hash=access_hash,
                invite_hash=invite_hash,
                updates=updates,
                title=title,
                recent=recent,
            ),
            timeout=25,
        )
    except asyncio.TimeoutError:
        logger.warning("news read timed out for %s", username)
        return [], "خواندن این منبع بیش از حد طول کشید", False


async def _read_channel_posts(
    username: str,
    *,
    min_id: int = 0,
    limit: int = 40,
    access_hash: int | None = None,
    invite_hash: str | None = None,
    updates: dict | None = None,
    title: str | None = None,
    recent: bool = False,
) -> tuple[list[dict], str | None, bool]:
    client = await _news_client()
    if client is None:
        return [], _NO_SESSION, False
    entity, error = await _open_source(
        client,
        username,
        access_hash=access_hash,
        invite_hash=invite_hash,
        updates=updates,
    )
    if error or entity is None:
        return [], error or "این کانال باز نشد", False
    page_limit = 12 if recent else limit
    found, read_error, truncated = await _messages(
        client, entity, username, min_id=0 if recent else min_id, limit=page_limit, title=title, recent=recent,
    )
    if not read_error:
        return found, None, truncated
    resolved, resolve_error = await _reread_joined(client, username, invite_hash, access_hash, updates)
    if resolved:
        return await _messages(
            client,
            resolved["chat"],
            resolved["username"],
            min_id=0 if recent else min_id,
            limit=12 if recent else limit,
            title=resolved.get("title") or title,
            recent=recent,
        )
    return [], resolve_error or read_error, truncated


async def _latest_id(client, entity) -> tuple[int | None, str | None]:
    try:
        async for message in client.iter_messages(entity, limit=1):
            return int(message.id), None
    except Exception as exc:
        logger.info("source probe read failed: %s", type(exc).__name__)
        return None, "خواندن پیام آزمایشی انجام نشد"
    return None, None


async def probe_channel(
    username: str,
    *,
    access_hash: int | None = None,
    invite_hash: str | None = None,
    updates: dict | None = None,
) -> tuple[dict, str | None]:
    """Open a source. Joins a public username when the news account is allowed to."""
    client = await _news_client()
    if client is None:
        return {}, _NO_SESSION
    entity, error = await _open_source(
        client,
        username,
        access_hash=access_hash,
        invite_hash=invite_hash,
        updates=updates,
    )
    if error or entity is None:
        return {}, error or "این کانال باز نشد"
    latest, read_error = await _latest_id(client, entity)
    if read_error:
        resolved, resolve_error = await _reread_joined(client, username, invite_hash, access_hash, updates)
        if resolved:
            entity = resolved["chat"]
            username = resolved["username"]
            latest, read_error = await _latest_id(client, entity)
        elif resolve_error:
            read_error = resolve_error
    if read_error and _public_name(username):
        joined = await join_public_channel(client, username)
        if joined:
            return {"title": getattr(entity, "title", None), "username": getattr(entity, "username", None)}, joined
        latest, read_error = await _latest_id(client, entity)
    info = {
        "title": getattr(entity, "title", None) or (updates or {}).get("title"),
        "username": getattr(entity, "username", None) or username,
    }
    if read_error:
        return info, read_error
    if latest:
        info["latest_id"] = latest
    return info, None


async def register_joined_invite(
    db,
    raw: str,
    *,
    category_hint: str | None = None,
    priority: str | None = None,
    interval_minutes: int | None = None,
):
    """Store a private channel the news account can already read. Never joins."""
    from sqlalchemy import select

    from backend.app.models.automation import NewsSource
    from backend.app.services.autopost import parse_invite_hash
    from backend.app.telegram.session_login import refresh_user_credentials

    invite_hash = parse_invite_hash(raw or "")
    if not invite_hash:
        return "لینک دعوت خصوصی شناخته نشد."
    await refresh_user_credentials(db)
    client = await _news_client()
    if client is None:
        return _NO_SESSION
    resolved, error = await resolve_joined_invite(client, invite_hash)
    if error or not resolved:
        return error or "این کانال خصوصی باز نشد"
    username = resolved["username"]
    row = (await db.execute(select(NewsSource).where(NewsSource.username == username))).scalar_one_or_none()
    if row is None:
        row = NewsSource(username=username, enabled=True)
        db.add(row)
    else:
        row.enabled = True
    row.title = resolved.get("title") or row.title
    row.access_hash = resolved.get("access_hash")
    row.invite_hash = invite_hash
    if not resolved.get("public"):
        row.source_type = "private"
    if category_hint:
        row.category_hint = category_hint
    if priority:
        row.priority = priority
    if interval_minutes:
        row.interval_minutes = interval_minutes
    latest, read_error = await _latest_id(client, resolved["chat"])
    row.last_error = read_error
    if latest and not read_error:
        row.last_message_id = latest
    await db.flush()
    return row


async def subscribe_public(db, raw: str) -> str:
    from sqlalchemy import select

    from backend.app.models.automation import NewsSource
    from backend.app.services.autopost import normalize_source, parse_invite_hash
    from backend.app.telegram.session_login import refresh_user_credentials

    if parse_invite_hash(raw or ""):
        result = await register_joined_invite(db, raw)
        if isinstance(result, str):
            return result
        if result.last_error:
            return f"منبع ثبت شد ولی خوانده نشد: {result.last_error}"
        title = result.title or result.username
        return f"منبع خصوصی ثبت شد، چون اکانت خبر از قبل عضو بود: {title}"
    username = normalize_source(raw or "")
    if not username:
        return "فقط یوزرنیم کانال عمومی، یا لینک دعوتی که اکانت خبر از قبل عضو آن است."
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
