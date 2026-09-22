import hashlib
import time
import logging
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.app.formatting.engine import format_message
from backend.app.formatting.emoji import EmojiMapping as EmojiMap
from backend.app.models.message_log import MessageLog
from backend.app.models.channel import Channel
from backend.app.models.emoji import EmojiMapping

logger = logging.getLogger(__name__)

def sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]

async def load_emoji_maps(db: AsyncSession) -> list[EmojiMap]:
    res = await db.execute(select(EmojiMapping).where(EmojiMapping.enabled==True))
    rows = res.scalars().all()
    out=[]
    for r in rows:
        try:
            ctx = json.loads(r.contexts) if r.contexts else None
        except:
            ctx=None
        out.append(EmojiMap(
            unicode_emoji=r.unicode_emoji,
            custom_emoji_id=r.custom_emoji_id,
            enabled=r.enabled,
            contexts=ctx,
            priority=r.priority,
        ))
    return out

async def process_channel_post(
    db: AsyncSession,
    chat_id: int,
    message_id: int,
    text: str | None,
    caption: str | None,
    has_media: bool,
    media_type: str | None,
) -> dict:
    effective = caption if has_media else text
    if not effective or not effective.strip():
        return {"status":"skipped","reason":"no_editable_content"}

    # Check channel allowlist
    res = await db.execute(select(Channel).where(Channel.chat_id==chat_id))
    channel = res.scalar_one_or_none()
    if not channel:
        # also log for visibility in panel
        log = MessageLog(
            chat_id=chat_id, message_id=message_id,
            original_text=effective, formatted_text=effective,
            original_hash=orig_hash, formatted_hash=orig_hash,
            category="general", status="skipped",
            error=f"unknown_channel: chat_id {chat_id} not registered. Add it in Channels panel.",
            applied_rules="[]",
            has_media=has_media, message_type=media_type or "text",
        )
        db.add(log)
        await db.flush()
        return {"status":"skipped","reason":"unknown_channel"}
    if not channel.enabled or not channel.auto_beautify:
        log = MessageLog(
            chat_id=chat_id, message_id=message_id,
            original_text=effective, formatted_text=effective,
            original_hash=orig_hash, formatted_hash=orig_hash,
            category="general", status="skipped",
            error="channel_disabled: channel is disabled or auto_beautify off",
            applied_rules="[]",
            has_media=has_media, message_type=media_type or "text",
        )
        db.add(log)
        await db.flush()
        return {"status":"skipped","reason":"channel_disabled"}

    # Global kill switch / dry run from settings
    from backend.app.core.config import get_settings
    settings = get_settings()
    if settings.kill_switch:
        return {"status":"skipped","reason":"kill_switch"}

    # Idempotency: check duplicate
    orig_hash = sha16(effective)
    dup = await db.execute(select(MessageLog).where(MessageLog.chat_id==chat_id, MessageLog.message_id==message_id))
    existing = dup.scalar_one_or_none()
    if existing and existing.original_hash == orig_hash and existing.status in ("edited","dry_run"):
        # Already successfully processed — avoid re-edit loops
        return {"status":"skipped","reason":"idempotent_duplicate"}

    # Load emoji mappings
    emoji_maps = await load_emoji_maps(db)

    t0 = time.perf_counter()
    result = format_message(
        raw_text=effective,
        is_caption=has_media,
        channel_style_slug=channel.style_id,
        footer_text=channel.footer_text,
        emoji_mappings=emoji_maps,
        enable_emoji=channel.emoji_replacement,
    )
    elapsed = (time.perf_counter()-t0)*1000

    if not result.changed:
        # log skipped with explicit reason
        log = MessageLog(
            chat_id=chat_id, message_id=message_id,
            original_text=effective, formatted_text=effective,
            original_hash=orig_hash, formatted_hash=orig_hash,
            category=result.category, status="skipped",
            error="no_change: content already matches style (footer/dividers present or no beautification needed)",
            applied_rules=json.dumps(result.applied_rules, ensure_ascii=False),
            processing_time_ms=elapsed,
            has_media=has_media, message_type=media_type or "text",
        )
        db.add(log)
        await db.flush()
        return {"status":"skipped","reason":"no_change","category":result.category}

    formatted_hash = sha16(result.text)
    # Dry run check
    is_dry = settings.dry_run
    status = "dry_run" if is_dry else "pending_edit"

    log = MessageLog(
        chat_id=chat_id, message_id=message_id,
        original_text=effective, formatted_text=result.text,
        original_hash=orig_hash, formatted_hash=formatted_hash,
        category=result.category, status=status,
        applied_rules=json.dumps(result.applied_rules, ensure_ascii=False),
        processing_time_ms=elapsed,
        has_media=has_media, message_type=media_type or "text",
    )
    db.add(log)
    await db.flush()

    # If not dry_run, attempt edit via Telegram API
    if not is_dry:
        from backend.app.telegram.edit import edit_telegram_message
        edit_result = await edit_telegram_message(
            chat_id=chat_id,
            message_id=message_id,
            text=result.text,
            html_text=result.html_text,
            is_caption=has_media,
        )
        if edit_result["ok"]:
            log.status = "edited"
        else:
            log.status = "failed"
            log.error = edit_result.get("error")
        await db.flush()
        return {"status": log.status, "category": result.category, "edit": edit_result, "formatted": result.text}
    else:
        return {"status":"dry_run","category":result.category,"formatted":result.text,"applied":result.applied_rules}
