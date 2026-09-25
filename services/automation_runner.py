"""One tick of the news automation. Safe to call from the panel or the loop."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.runtime import load_runtime
from backend.app.models.automation import DraftPost, NewsSource, PublishSlot
from backend.app.services.autopost import (
    draft_from_source,
    get_config,
    next_slot_time,
    slot_is_due,
    slot_key,
)
from backend.app.telegram.collector import read_channel_posts
from backend.app.telegram.publisher import publish_text

logger = logging.getLogger(__name__)
COLLECT_GAP = timedelta(minutes=20)


async def collect_sources(db: AsyncSession, *, force: bool = False) -> dict:
    config = await get_config(db)
    if not config.enabled and not force:
        return {"created": 0, "skipped": "disabled"}
    if not force and config.last_collect_at and config.last_collect_at > datetime.now(timezone.utc) - COLLECT_GAP:
        return {"created": 0, "skipped": "recent"}
    runtime = await load_runtime(db)
    sources = (await db.execute(select(NewsSource).where(NewsSource.enabled == True))).scalars().all()  # noqa: E712
    slots = (await db.execute(select(PublishSlot).where(PublishSlot.enabled == True))).scalars().all()  # noqa: E712
    created = 0
    errors: list[str] = []
    for source in sources:
        posts, error = await read_channel_posts(source.username, min_id=int(source.last_message_id or 0))
        if error:
            source.last_error = error[:300]
            errors.append(error)
            if "نشست" in error:
                break
            continue
        source.last_error = None
        for item in reversed(posts):
            key = f"{source.username}:{item['id']}"
            exists = (await db.execute(select(DraftPost.id).where(DraftPost.source_key == key))).first()
            source.last_message_id = max(int(source.last_message_id or 0), int(item["id"]))
            if exists:
                continue
            body, category, reason = await draft_from_source(item["text"], item.get("title") or source.username, runtime)
            if not body:
                if reason == "not_ready":
                    config.last_error = "هوش مصنوعی آماده نیست؛ پیش‌نویس ساخته نشد"
                    await db.flush()
                    return {"created": created, "error": config.last_error}
                continue
            draft = DraftPost(
                status="preview",
                category=source.category_hint or category or "news",
                body=body,
                source_label=source.username,
                source_key=key,
                target_chat_id=config.target_chat_id,
            )
            if config.auto_publish:
                when = next_slot_time(list(slots))
                if when is not None:
                    draft.status = "scheduled"
                    draft.scheduled_at = when.astimezone(timezone.utc)
            db.add(draft)
            created += 1
    config.last_collect_at = datetime.now(timezone.utc)
    config.last_error = errors[0] if errors else None
    await db.flush()
    return {"created": created, "errors": errors}


async def publish_due(db: AsyncSession) -> dict:
    config = await get_config(db)
    if not config.target_chat_id:
        return {"published": 0, "error": "کانال مقصد انتخاب نشده"}
    now = datetime.now(timezone.utc)
    published = 0
    due = (
        await db.execute(
            select(DraftPost).where(DraftPost.status == "scheduled", DraftPost.scheduled_at.is_not(None), DraftPost.scheduled_at <= now)
        )
    ).scalars().all()
    for draft in due:
        message_id, error = await publish_text(int(config.target_chat_id), draft.body)
        draft.target_chat_id = config.target_chat_id
        if error:
            draft.status = "failed"
            draft.error = error
            continue
        draft.status = "published"
        draft.published_at = now
        draft.message_id = message_id
        draft.error = None
        published += 1
    if config.enabled and config.auto_publish:
        slots = (await db.execute(select(PublishSlot))).scalars().all()
        used = {
            key for key in (await db.execute(select(DraftPost.slot_key).where(DraftPost.slot_key.is_not(None)))).scalars().all()
            if key
        }
        for slot in slots:
            if not slot_is_due(slot, used_keys=used):
                continue
            query = select(DraftPost).where(DraftPost.status == "preview").order_by(DraftPost.created_at)
            if slot.category:
                query = query.where(DraftPost.category == slot.category)
            draft = (await db.execute(query)).scalars().first()
            if draft is None:
                continue
            message_id, error = await publish_text(int(config.target_chat_id), draft.body)
            key = slot_key(slot)
            draft.slot_key = key
            used.add(key)
            draft.target_chat_id = config.target_chat_id
            if error:
                draft.status = "failed"
                draft.error = error
                continue
            draft.status = "published"
            draft.published_at = now
            draft.message_id = message_id
            draft.error = None
            published += 1
    await db.flush()
    return {"published": published}


async def automation_loop(stop) -> None:
    import asyncio
    from backend.app.db.base import get_session_factory

    while not stop.is_set():
        try:
            factory = get_session_factory()
            async with factory() as db:
                await publish_due(db)
                await collect_sources(db)
                await db.commit()
        except Exception:
            logger.exception("automation tick failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=60)
        except asyncio.TimeoutError:
            continue
