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
from backend.app.formatting.editor import analyze_post
from backend.app.formatting.engine import format_message
from backend.app.formatting.rotation import choose_template
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


def build_log_meta(
    reply_markup: dict | None = None,
    entities: list | None = None,
    decision=None,
    selection: dict | None = None,
    warnings: list | None = None,
) -> str:
    """Keep retry data on every logged post, including no_change skips."""
    payload: dict = {
        "reply_markup": reply_markup,
        "entities": entities or [],
    }
    if decision is not None:
        payload["decision"] = decision.as_dict() if hasattr(decision, "as_dict") else decision
    if selection:
        payload["selection"] = selection
    if warnings:
        payload["warnings"] = warnings
    return json.dumps(payload, ensure_ascii=False)


def selection_from_meta(raw: str | None) -> dict:
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    selection = parsed.get("selection") if isinstance(parsed, dict) else None
    return selection if isinstance(selection, dict) else {}


async def recent_template_state(db: AsyncSession, chat_id: int, message_id: int) -> tuple[list[str], list[str], list[str]]:
    """Newest-last structure ids, emoji styles, and recently used custom emoji ids."""
    rows = (
        await db.execute(
            select(MessageLog.meta)
            .where(MessageLog.chat_id == chat_id, MessageLog.message_id != message_id)
            .order_by(desc(MessageLog.created_at))
            .limit(5)
        )
    ).scalars().all()
    structures: list[str] = []
    emoji_styles: list[str] = []
    used_ids: list[str] = []
    for raw in reversed(list(rows)):
        selection = selection_from_meta(raw)
        if selection.get("structure_id"):
            structures.append(str(selection["structure_id"]))
        if selection.get("emoji_style_id"):
            emoji_styles.append(str(selection["emoji_style_id"]))
        for item in selection.get("used_emoji_ids") or []:
            used_ids.append(str(item))
    return structures, emoji_styles, used_ids[-12:]


def _ai_entities(text: str | None, marks) -> list | None:
    if not text or not marks:
        return None
    from backend.app.formatting.textutil import utf16_len
    return [
        {
            "type": mark.type,
            "offset": utf16_len(text[:mark.start]),
            "length": utf16_len(text[mark.start:mark.end]),
        }
        for mark in marks
    ]


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
            category=row.category,
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
    entities: list | None = None,
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
            meta=build_log_meta(reply_markup, entities),
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
            meta=build_log_meta(reply_markup, entities),
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
            meta=build_log_meta(reply_markup, entities),
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
    from backend.app.formatting.richtext import quote_texts, shield_quotes, unwrap_quotes

    source_text = strip_footer_block(effective, footer, style.divider if style else None)
    quotes = quote_texts(effective, entities)
    ai_source = shield_quotes(source_text, quotes)
    decision = analyze_post(effective, entities)
    recent_structures, recent_emoji_styles, recent_emoji_ids = await recent_template_state(db, chat_id, message_id)
    choice = choose_template(
        decision,
        channel_style=channel.style_id,
        recent_structures=recent_structures,
        recent_emoji_styles=recent_emoji_styles,
        emoji_enabled=bool(channel.emoji_replacement and runtime.premium_mode != "off"),
        has_entities=bool(entities),
    )

    use_ai = (
        runtime.ai_ready
        and (channel.ai_rewrite if channel.ai_rewrite is not None else True)
        and decision.strategy == "light_edit"
    )
    ai_text = None
    ai_marks = None
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
        ai_text = await enhance_with_ai(
            ai_source,
            decision.category,
            previous,
            runtime=runtime,
            limit=900 if has_media else 3600,
            required=quotes,
        )
        if ai_text and quotes:
            ai_text, ai_marks = unwrap_quotes(ai_text, quotes)
            if any(quote not in (ai_text or "") for quote in quotes):
                logger.info("AI dropped a quote; keeping the admin wording")
                ai_text = None
                ai_marks = None

    started = time.perf_counter()
    result = format_message(
        raw_text=ai_text or effective,
        is_caption=has_media,
        channel_style_slug=channel.style_id,
        footer_text=footer,
        emoji_mappings=emoji_maps,
        header_enabled=channel.header_enabled and not entities and not ai_text,
        enable_emoji=channel.emoji_replacement and runtime.premium_mode != "off",
        persian_normalize=runtime.persian_normalize and not entities,
        max_emoji=runtime.max_emoji_per_post,
        style_config=style,
        entities=_ai_entities(ai_text, ai_marks) if ai_text else entities,
        footer_url=getattr(runtime, "footer_url", None),
        support_username=getattr(runtime, "support_username", None),
        category=decision.category,
        structure_id=choice.structure_id,
        body_emoji=choice.emoji_style_id == "accent",
        avoid_emoji_ids=set(recent_emoji_ids),
    )
    result.applied_rules.append(f"strategy:{decision.strategy}")
    result.applied_rules.append(f"template:{decision.template_family}")
    result.applied_rules.append(f"template_id:{choice.template_id}")
    result.applied_rules.append(f"style_id:{choice.style_id}")
    result.applied_rules.append(f"emoji_style:{choice.emoji_style_id}")
    result.applied_rules.append(f"structure:{choice.structure_id}")
    selection = choice.as_dict()
    selection["used_emoji_ids"] = [cid for _start, _end, cid in result.emoji_spans]
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
            meta=build_log_meta(reply_markup, entities, decision, selection, result.warnings),
        )
        await db.flush()
        return {"status": "skipped", "reason": "no_change", "category": result.category, "log_id": log.id}

    formatted_hash = content_hash(result.text)
    markup = reply_markup if channel.preserve_buttons else None
    markup = merge_signature(markup, channel.signature_text, channel.signature_url)
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
        meta=build_log_meta(reply_markup, entities, decision, selection, result.warnings),
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
    has_formatting = bool(result.html_text)
    want_user = channel.emoji_replacement and mode in {"auto", "user"} and session_configured() and bool(result.entities or result.emoji_spans)
    if want_user:
        user_result = await edit_via_user(
            chat_id, message_id, result.text, result.emoji_spans, entities=result.entities,
        )
        if user_result.get("ok"):
            return user_result
        logger.info("User-session edit failed, trying Bot API: %s", user_result.get("error"))
    return await edit_telegram_message(
        chat_id=chat_id,
        message_id=message_id,
        text=result.text,
        html_text=result.html_text if has_formatting and mode != "user" else None,
        is_caption=has_media,
        reply_markup=markup,
        prefer_html=has_formatting and mode != "user",
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
        entities=meta.get("entities"),
    )
