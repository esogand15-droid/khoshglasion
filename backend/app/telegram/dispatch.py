from __future__ import annotations

import asyncio
import json
import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.runtime import load_runtime
from backend.app.models.channel import Channel
from backend.app.models.system import WebhookEvent
from backend.app.services.notify import notify
from backend.app.telegram.commands import handle_callback, handle_private_message
from backend.app.telegram.pipeline import NON_EDITABLE, process_channel_post

logger = logging.getLogger(__name__)

_inflight: set[tuple[int, int]] = set()
_tasks: set[asyncio.Task] = set()


def spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def _summary(data: dict) -> str:
    post = data.get("channel_post") or data.get("edited_channel_post") or data.get("message") or {}
    chat = post.get("chat") or {}
    payload = {
        "update_id": data.get("update_id"),
        "keys": [key for key in data.keys() if key != "update_id"],
        "chat_id": chat.get("id"),
        "message_id": post.get("message_id"),
    }
    return json.dumps(payload, ensure_ascii=False)[:1500]


async def _claim_update(db: AsyncSession, data: dict) -> bool:
    update_id = data.get("update_id")
    if update_id is None:
        return True
    existing = (await db.execute(select(WebhookEvent.id).where(WebhookEvent.update_id == update_id))).first()
    if existing:
        return False
    db.add(WebhookEvent(update_id=update_id, payload=_summary(data), status="received"))
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return False
    return True


def _media(post: dict) -> tuple[bool, str | None]:
    for key in (
        "photo", "video", "animation", "document", "audio", "voice", "video_note",
        "sticker", "poll", "location", "contact", "venue", "dice",
    ):
        if key in post:
            return True, key
    return False, None


async def _remember_channel(db: AsyncSession, chat: dict, *, can_edit: bool, enabled: bool, note: str) -> Channel:
    chat_id = int(chat["id"])
    channel = (await db.execute(select(Channel).where(Channel.chat_id == chat_id))).scalar_one_or_none()
    if channel is None:
        channel = Channel(chat_id=chat_id)
        db.add(channel)
    channel.title = chat.get("title") or channel.title
    channel.username = chat.get("username") or channel.username
    channel.can_edit = can_edit
    channel.enabled = enabled and can_edit
    channel.notes = note
    await db.flush()
    return channel


async def handle_update(db: AsyncSession, data: dict) -> dict:
    if not await _claim_update(db, data):
        return {"ok": True, "skipped": "duplicate_update"}

    runtime = await load_runtime(db)
    if "callback_query" in data:
        return await handle_callback(db, data["callback_query"], runtime)

    if "my_chat_member" in data:
        member = data["my_chat_member"]
        chat = member.get("chat") or {}
        if chat.get("type") != "channel" or "id" not in chat:
            return {"ok": True, "skipped": "not_channel_membership"}
        new_member = member.get("new_chat_member") or {}
        status = new_member.get("status")
        if status in {"administrator", "creator"}:
            can_edit = status == "creator" or bool(new_member.get("can_edit_messages"))
            channel = await _remember_channel(
                db, chat, can_edit=can_edit, enabled=True,
                note="ثبت از روی افزودن ربات به کانال",
            )
            if can_edit:
                await notify(runtime, f"ربات ادمین کانال شد: {channel.title or channel.chat_id}\nحالا پست‌ها خودکار خوشگل می‌شوند.")
            else:
                await notify(runtime, f"ربات به {channel.title or channel.chat_id} اضافه شد ولی دسترسی Edit messages ندارد.")
            return {"ok": True, "registered": channel.chat_id, "can_edit": can_edit}
        if status in {"left", "kicked", "restricted"}:
            channel = (await db.execute(select(Channel).where(Channel.chat_id == int(chat["id"])))).scalar_one_or_none()
            if channel:
                channel.enabled = False
                channel.can_edit = False
                channel.notes = f"ربات از کانال خارج شد ({status})"
            await notify(runtime, f"ربات از کانال {chat.get('title') or chat.get('id')} خارج شد.")
            return {"ok": True, "removed": chat.get("id")}
        return {"ok": True, "skipped": f"membership_{status}"}

    private = data.get("message") or data.get("edited_message")
    if private and (private.get("chat") or {}).get("type") == "private":
        return await handle_private_message(db, private, runtime)

    edited = "edited_channel_post" in data and "channel_post" not in data
    post = data.get("channel_post") or data.get("edited_channel_post")
    if not post:
        return {"ok": True, "skipped": "no_channel_post"}

    chat = post.get("chat") or {}
    chat_id = chat.get("id")
    message_id = post.get("message_id")
    if chat_id is None or message_id is None:
        return {"ok": True, "skipped": "missing_ids"}

    has_media, media_type = _media(post)
    if media_type in NON_EDITABLE:
        return {"ok": True, "skipped": f"non_editable_{media_type}"}

    key = (int(chat_id), int(message_id))
    if key in _inflight:
        return {"ok": True, "skipped": "inflight"}
    _inflight.add(key)
    try:
        if chat.get("title") or chat.get("username"):
            known = (await db.execute(select(Channel).where(Channel.chat_id == int(chat_id)))).scalar_one_or_none()
            if known:
                known.title = chat.get("title") or known.title
                known.username = chat.get("username") or known.username
        result = await process_channel_post(
            db,
            chat_id=int(chat_id),
            message_id=int(message_id),
            text=post.get("text"),
            caption=post.get("caption"),
            has_media=has_media and bool(post.get("caption")),
            media_type=media_type,
            reply_markup=post.get("reply_markup"),
            is_edit_event=edited,
            update_id=data.get("update_id"),
            runtime=runtime,
            entities=post.get("caption_entities") if has_media and post.get("caption") else post.get("entities"),
        )
        known = (await db.execute(select(Channel).where(Channel.chat_id == int(chat_id)))).scalar_one_or_none()
        if known:
            known.title = chat.get("title") or known.title
            known.username = chat.get("username") or known.username
        event = (await db.execute(select(WebhookEvent).where(WebhookEvent.update_id == data.get("update_id")))).scalar_one_or_none()
        if event:
            event.status = result.get("status") or "processed"
            event.error = result.get("reason") or (result.get("edit") or {}).get("error")
        return {"ok": True, "result": result}
    finally:
        _inflight.discard(key)


async def process_update_safely(data: dict) -> None:
    from backend.app.db.base import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        try:
            await handle_update(db, data)
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("Update processing failed update_id=%s", data.get("update_id"))
