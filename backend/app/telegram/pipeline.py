from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import logging
import time

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.runtime import RuntimeState, load_runtime
from backend.app.formatting.emoji import EmojiMapping as EmojiMap
from backend.app.formatting.engine import format_message
from backend.app.formatting.styles import get_style, style_from_payload
from backend.app.formatting.textutil import strip_footer_block
from backend.app.models.channel import Channel
from backend.app.models.emoji import EmojiMapping
from backend.app.models.message_log import MessageLog
from backend.app.models.style import StylePreset
from backend.app.services.ai import enhance_with_ai
from backend.app.services.notify import notify
from backend.app.telegram.edit import edit_telegram_message, merge_signature
from backend.app.telegram.user_editor import edit_via_user, session_configured

logger = logging.getLogger(__name__)

NON_EDITABLE = {
    "poll", "sticker", "location", "contact", "venue", "dice", "game",
    "invoice", "successful_payment", "video_note", "story",
}
FINAL_STATUSES = {"edited", "dry_run"}


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def parse_contexts(raw: str | None):
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return [raw]
    if isinstance(parsed, str):
        return [parsed]
    if isinstance(parsed, list) and parsed:
        return parsed
    return None


async def load_emoji_maps(db: AsyncSession) -> list[EmojiMap]:
    rows = (await db.execute(select(EmojiMapping).where(EmojiMapping.enabled == True))).scalars().all()  # noqa: E712
    return [
        EmojiMap(
            unicode_emoji=row.unicode_emoji,
            custom_emoji_id=row.custom_emoji_id,
            enabled=row.enabled,
            contexts=parse_contexts(row.contexts),
            priority=row.priority or 50,
        )
        for row in rows
    ]


async def resolve_style(db: AsyncSession, slug: str | None):
    if not slug:
        return None
    builtin = get_style(slug)
    if builtin.slug == slug:
        return builtin
    row = (await db.execute(select(StylePreset).where(StylePreset.slug == slug))).scalar_one_or_none()
    if row is None:
        row = (await db.execute(select(StylePreset).where(StylePreset.id == slug))).scalar_one_or_none()
    if row is None:
        return None
    return style_from_payload(row.slug, row.name, row.config)


def _keywords(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except json.JSONDecodeError:
        pass
    return [part.strip() for part in raw.replace("،", ",").split(",") if part.strip()]


def _upsert_log(db: AsyncSession, existing: MessageLog | None, **values) -> MessageLog:
    if existing is None:
        log = MessageLog(**values)
        db.add(log)
        return log
    for key, value in values.items():
        setattr(existing, key, value)
    existing.attempt_count = (existing.attempt_count or 0) + 1
    return existing


async def _touch_emoji_usage(db: AsyncSession, spans: list[tuple[int, int, str]]) -> None:
    ids = {cid for _s, _e, cid in spans}
    if not ids:
        return
    rows = (await db.execute(select(EmojiMapping).where(EmojiMapping.custom_emoji_id.in_(ids)))).scalars().all()
    now_ids = set()
    for row in rows:
        if row.custom_emoji_id in now_ids:
            continue
        now_ids.add(row.custom_emoji_id)
        row.usage_count = (row.usage_count or 0) + 1


async def process_channel_post(
    db: AsyncSession,
    chat_id: int,
    message_id: int,
    text: str | None,
    caption: str | None,
    has_media: bool,
    media_type: str | None,
    reply_markup: dict | None = None,
    is_edit_event: bool = False,
    force: bool = False,
    update_id: int | None = None,
    runtime: RuntimeState | None = None,
) -> dict:
    runtime = runtime or await load_runtime(db)
    effective = (caption if has_media else text) or ""
    effective = effective.strip()
    # Hash is computed before every branch. The old code referenced it while
    # logging an unknown channel and crashed before the channel could be saved.
    orig_hash = content_hash(effective) if effective else content_hash("")

    if media_type in NON_EDITABLE:
        return {"status": "skipped", "reason": f"non_editable_{media_type}"}
    if not effective:
        return {"status": "skipped", "reason": "no_editable_content"}

    channel = (await db.execute(select(Channel).where(Channel.chat_id == chat_id))).scalar_one_or_none()
    if channel is None and runtime.auto_register_channels and not is_edit_event:
        channel = Channel(
            chat_id=chat_id,
            title=f"کانال {chat_id}",
            enabled=True,
            auto_beautify=True,
            emoji_replacement=True,
            notes="ثبت خودکار از روی اولین پست",
        )
        db.add(channel)
        await db.flush()
        logger.info("Auto-registered channel %s", chat_id)

    existing = (
        await db.execute(select(MessageLog).where(MessageLog.chat_id == chat_id, MessageLog.message_id == message_id))
    ).scalar_one_or_none()

    if is_edit_event and existing and existing.formatted_hash == orig_hash and existing.status == "edited":
        return {"status": "skipped", "reason": "own_edit"}
    if is_edit_event and not runtime.reprocess_edits and not force:
        return {"status": "skipped", "reason": "edit_event_ignored"}

    if channel is None:
        log = _upsert_log(
            db, existing,
            chat_id=chat_id, message_id=message_id,
            original_text=effective, formatted_text=effective,
            original_hash=orig_hash, formatted_hash=orig_hash,
            category="general", status="skipped",
            error=f"unknown_channel: chat_id {chat_id} ثبت نشده است.",
            applied_rules="[]", has_media=has_media, message_type=media_type or "text",
            update_id=update_id,
        )
        await db.flush()
        return {"status": "skipped", "reason": "unknown_channel", "log_id": log.id}

    if not channel.enabled or not channel.auto_beautify:
        log = _upsert_log(
            db, existing,
            chat_id=chat_id, message_id=message_id,
            original_text=effective, formatted_text=effective,
            original_hash=orig_hash, formatted_hash=orig_hash,
            category="general", status="skipped",
            error="channel_disabled",
            applied_rules="[]", has_media=has_media, message_type=media_type or "text",
            update_id=update_id,
        )
        await db.flush()
        return {"status": "skipped", "reason": "channel_disabled", "log_id": log.id}

    if runtime.kill_switch and not force:
        return {"status": "skipped", "reason": "kill_switch"}

    blocked = next((word for word in _keywords(channel.skip_keywords) if word and word in effective), None)
    if blocked:
        log = _upsert_log(
            db, existing,
            chat_id=chat_id, message_id=message_id,
            original_text=effective, formatted_text=effective,
            original_hash=orig_hash, formatted_hash=orig_hash,
            category="general", status="skipped",
            error=f"skip_keyword:{blocked}",
            applied_rules="[]", has_media=has_media, message_type=media_type or "text",
            update_id=update_id,
        )
        await db.flush()
        return {"status": "skipped", "reason": "skip_keyword", "log_id": log.id}

    if len(effective) < (channel.min_chars or 1):
        return {"status": "skipped", "reason": "too_short"}

    if not force and existing and existing.original_hash == orig_hash and existing.status in FINAL_STATUSES:
        return {"status": "skipped", "reason": "idempotent_duplicate"}

    style = await resolve_style(db, channel.style_id)
    footer = channel.footer_text if channel.footer_text is not None else (runtime.default_footer or None)
    if footer == "":
        footer = None
    emoji_maps = await load_emoji_maps(db) if channel.emoji_replacement else []
    source_text = strip_footer_block(effective, footer, style.divider if style else None)

    use_ai = runtime.ai_ready and (channel.ai_rewrite if channel.ai_rewrite is not None else True)
    ai_text = None
    if use_ai:
        previous = ""
        prev = (
            await db.execute(
                select(MessageLog.formatted_text)
                .where(MessageLog.chat_id == chat_id, MessageLog.status.in_(["edited", "dry_run"]))
                .order_by(desc(MessageLog.created_at))
                .limit(1)
            )
        ).scalar_one_or_none()
        if prev:
            previous = prev[:300]
        from backend.app.formatting.category import detect_category
        ai_text = await enhance_with_ai(
            source_text,
            detect_category(source_text),
            previous,
            runtime=runtime,
            limit=900 if has_media else 3600,
        )

    started = time.perf_counter()
    result = format_message(
        raw_text=ai_text or source_text,
        is_caption=has_media,
        channel_style_slug=channel.style_id,
        footer_text=footer,
        emoji_mappings=emoji_maps,
        header_enabled=channel.header_enabled,
        enable_emoji=channel.emoji_replacement and runtime.premium_mode != "off",
        persian_normalize=runtime.persian_normalize,
        max_emoji=runtime.max_emoji_per_post,
        style_config=style,
    )
    if ai_text:
        result.applied_rules.append("ai_enhanced")
    elapsed = (time.perf_counter() - started) * 1000

    if not result.changed and not force:
        log = _upsert_log(
            db, existing,
            chat_id=chat_id, message_id=message_id,
            original_text=effective, formatted_text=result.text,
            html_text=result.html_text,
            original_hash=orig_hash, formatted_hash=content_hash(result.text),
            category=result.category, status="skipped",
            error="no_change",
            applied_rules=json.dumps(result.applied_rules, ensure_ascii=False),
            processing_time_ms=elapsed, has_media=has_media, message_type=media_type or "text",
            ai_used=bool(ai_text), update_id=update_id,
            meta=json.dumps({"reply_markup": reply_markup}, ensure_ascii=False),
        )
        await db.flush()
        return {"status": "skipped", "reason": "no_change", "category": result.category, "log_id": log.id}

    formatted_hash = content_hash(result.text)
    markup = reply_markup if channel.preserve_buttons else None
    markup = merge_signature(markup, channel.signature_text, channel.signature_url)
    meta = {"reply_markup": reply_markup, "warnings": result.warnings}
    log = _upsert_log(
        db, existing,
        chat_id=chat_id, message_id=message_id,
        original_text=effective, formatted_text=result.text, html_text=result.html_text,
        original_hash=orig_hash, formatted_hash=formatted_hash,
        category=result.category, status="dry_run" if runtime.dry_run else "pending_edit",
        error=None,
        applied_rules=json.dumps(result.applied_rules, ensure_ascii=False),
        processing_time_ms=elapsed, has_media=has_media, message_type=media_type or "text",
        ai_used=bool(ai_text), edit_method=None, update_id=update_id,
        meta=json.dumps(meta, ensure_ascii=False),
    )
    await db.flush()

    if runtime.dry_run:
        return {
            "status": "dry_run",
            "category": result.category,
            "formatted": result.text,
            "applied": result.applied_rules,
            "log_id": log.id,
            "ai_used": bool(ai_text),
        }

    delay = channel.edit_delay_seconds if channel.edit_delay_seconds is not None else runtime.edit_delay_seconds
    wait_for = 0.3 if force else max(0.4, min(float(delay or 0), 20))
    await asyncio.sleep(wait_for)

    edit_result = await _edit(runtime, channel, chat_id, message_id, result, has_media, markup)
    log.edit_method = edit_result.get("method")
    log.processing_time_ms = (time.perf_counter() - started) * 1000
    if edit_result.get("ok"):
        log.status = "edited"
        log.error = edit_result.get("warning")
        already = existing is not None and existing.status == "edited"
        channel.posts_edited = (channel.posts_edited or 0) + (0 if already else 1)
        channel.last_error = None
        channel.last_post_at = datetime.now(timezone.utc)
        await _touch_emoji_usage(db, result.emoji_spans)
        if edit_result.get("emoji_rejected"):
            await _remember_emoji_error(db, edit_result.get("error") or "custom emoji rejected")
    else:
        log.status = "failed"
        log.error = str(edit_result.get("error") or "edit_failed")[:2000]
        channel.last_error = log.error
        await notify(
            runtime,
            f"ادیت ناموفق شد.\nکانال: {channel.title or chat_id}\nپیام: {message_id}\nخطا: {log.error[:500]}",
            chat_id=chat_id,
            message_id=message_id,
        )
    await db.flush()
    return {
        "status": log.status,
        "category": result.category,
        "edit": {k: v for k, v in edit_result.items() if k != "formatted"},
        "formatted": result.text,
        "log_id": log.id,
        "ai_used": bool(ai_text),
    }


async def _edit(runtime: RuntimeState, channel: Channel, chat_id: int, message_id: int, result, has_media: bool, markup):
    mode = (runtime.premium_mode or "auto").lower()
    want_premium = channel.emoji_replacement and mode != "off" and bool(result.emoji_spans)
    if want_premium and mode in {"auto", "user"} and session_configured():
        user_result = await edit_via_user(chat_id, message_id, result.text, result.emoji_spans)
        if user_result.get("ok"):
            return user_result
        logger.info("User-session edit failed, trying Bot API: %s", user_result.get("error"))
    return await edit_telegram_message(
        chat_id=chat_id,
        message_id=message_id,
        text=result.text,
        html_text=result.html_text if want_premium and mode != "user" else None,
        is_caption=has_media,
        reply_markup=markup,
        prefer_html=want_premium and mode != "user",
    )


async def _remember_emoji_error(db: AsyncSession, message: str) -> None:
    from backend.app.models.system import SystemSetting
    row = (await db.execute(select(SystemSetting).where(SystemSetting.key == "last_emoji_error"))).scalar_one_or_none()
    if row:
        row.value = message[:500]
    else:
        db.add(SystemSetting(key="last_emoji_error", value=message[:500], description="last custom emoji rejection"))


async def reprocess_log(db: AsyncSession, log: MessageLog, runtime: RuntimeState | None = None) -> dict:
    meta = {}
    try:
        meta = json.loads(log.meta or "{}")
    except json.JSONDecodeError:
        meta = {}
    return await process_channel_post(
        db,
        log.chat_id,
        log.message_id,
        text=None if log.has_media else log.original_text,
        caption=log.original_text if log.has_media else None,
        has_media=bool(log.has_media),
        media_type=log.message_type,
        reply_markup=meta.get("reply_markup"),
        force=True,
        runtime=runtime,
    )
