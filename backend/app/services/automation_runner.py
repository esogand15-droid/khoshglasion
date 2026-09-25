"""One tick of the news automation. Safe to call from the panel or the loop."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import asyncio
import json
import logging
import os
import re

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.content.pipeline import (
    attribution_line,
    choose_hashtags,
    content_hash,
    extract_facts,
    judge_value,
    merge_analysis,
    opening_signature,
    parse_analysis,
    should_auto_schedule,
    source_url,
    too_similar,
)
from backend.app.content.media_store import remember_paths
from backend.app.content.publish import configured_footer, prepare_publish_payload
from backend.app.content.schedule import cursor_after, next_retry_at, pick_balanced
from backend.app.core.runtime import load_runtime
from backend.app.formatting.editor import analyze_post
from backend.app.formatting.rotation import choose_template
from backend.app.models.automation import (
    AutomationJob,
    AutomationLog,
    DraftPost,
    HashtagRule,
    JobLock,
    NewsSource,
    PublishSlot,
)
from backend.app.content.intake import layout_for, photo_of, rewrite_plan, safe_photo_path
from backend.app.services.ai import complete_text, describe_image
from backend.app.services.finetune import (
    angle_label,
    classify_style,
    folder_category,
    folder_label,
    keep_fun,
    load_card,
    remember_sample,
)
from backend.app.services.autopost import (
    active_prompt,
    as_utc,
    compose_prompt,
    append_hashtags,
    draft_from_source,
    ensure_content_defaults,
    get_config,
    human_reason,
    push_lesson,
    next_slot_time,
    slot_is_due,
    slot_key,
)
from backend.app.services.prompts import wrap_post
from backend.app.services.notify import notify
from backend.app.telegram.collector import read_channel_posts
from backend.app.telegram.pipeline import load_emoji_maps
from backend.app.telegram.publisher import publish_rendered

_alerted: set[str] = set()

logger = logging.getLogger(__name__)
WORKER_ID = (os.environ.get("HOSTNAME") or "worker")[:32]
PRIORITY = {"high": 0, "normal": 1, "low": 2}
_SECRETISH = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")


def safe_detail(text: str | None) -> str:
    return _SECRETISH.sub("[redacted]", text or "")[:400]


async def write_log(db: AsyncSession, event: str, detail: str = "", level: str = "info") -> None:
    db.add(AutomationLog(level=level, event=event[:64], detail=safe_detail(detail)))


async def alert_admin(db: AsyncSession, key: str, text: str, runtime=None) -> None:
    if key in _alerted:
        return
    _alerted.add(key)
    if len(_alerted) > 300:
        _alerted.clear()
    if runtime is None:
        runtime = await load_runtime(db)
    try:
        await notify(runtime, safe_detail(text)[:500])
    except Exception:
        logger.info("admin alert failed")


SKIP_FA = {
    "DUPLICATE": "تکراری است",
    "ADVERTISEMENT": "تبلیغ کانال دیگر است و برای پست استفاده نمی‌شود",
    "LOW_VALUE": "برای پست کانال مناسب نیست",
    "OUTDATED": "کهنه است",
}


def source_stamp(value) -> str | None:
    """Telegram receive time, stored as UTC. Never invent a clock."""
    if isinstance(value, datetime):
        stamped = as_utc(value)
        return stamped.isoformat() if stamped else None
    if isinstance(value, (int, float)) and value > 1_000_000_000:
        return datetime.fromtimestamp(float(value), timezone.utc).isoformat()
    return None


def repeat_source(text: str, known: list[str], digest: str, hashes: set[str]) -> bool:
    """A second scan must not open a draft for the same or a near-copy of a seen post."""
    if digest and digest in hashes:
        return True
    folded = re.sub(r"\s+", "", text or "")
    if len(folded) < 24:
        return False
    return too_similar(text, known)


def _remember_seen(db: AsyncSession, source: NewsSource, item: dict, digest: str, config) -> None:
    """Remember a repeat so the next scan is cheap. This row is not a draft."""
    db.add(DraftPost(
        status="seen",
        category=source.category_hint or "news",
        body="",
        source_content=(item.get("text") or "")[:4000],
        source_label=source.title or source.username,
        source_key=f"{source.username}:{int(item['id'])}",
        content_hash=digest or None,
        error="تکراری است",
        confidence="low",
        analysis_json=json.dumps({"value": "DUPLICATE"}, ensure_ascii=False),
        target_chat_id=config.target_chat_id,
    ))


def _remember_skip(db: AsyncSession, source: NewsSource, item: dict, reason: str, config, detail: str = "") -> None:
    label = detail.strip() or SKIP_FA.get(reason) or reason
    if reason == "ADVERTISEMENT" and not label.startswith("تبلیغ"):
        label = f"تبلیغ: {label}"
    db.add(DraftPost(
        status="skipped",
        category=source.category_hint or "news",
        body="",
        source_content=item.get("text") or "",
        source_label=source.title or source.username,
        source_key=f"{source.username}:{int(item['id'])}",
        content_hash=content_hash(item.get("text") or "") or None,
        error=label[:180],
        confidence="low",
        analysis_json=json.dumps({"value": reason, "reading": detail[:180], "has_media": bool(item.get("has_media"))}, ensure_ascii=False),
        target_chat_id=config.target_chat_id,
    ))


PUBLISHABLE = ("preview", "scheduled", "failed", "recalled", "rejected")


async def claim_for_publish(db: AsyncSession, draft_id: str, allowed: tuple[str, ...] | None = None) -> bool:
    """One sender wins. The clock only claims the status it selected, so a reject cannot be published underneath the panel."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        update(DraftPost)
        .where(DraftPost.id == draft_id, DraftPost.status.in_(allowed or PUBLISHABLE))
        .values(status="sending", updated_at=now, error=None)
    )
    return (result.rowcount or 0) == 1


async def recover_stuck_sends(db: AsyncSession, now: datetime | None = None) -> None:
    moment = now or datetime.now(timezone.utc)
    await db.execute(
        update(DraftPost)
        .where(
            DraftPost.status == "sending",
            DraftPost.updated_at.is_not(None),
            DraftPost.updated_at < moment - timedelta(minutes=3),
        )
        .values(status="failed", error="ارسال ناتمام ماند. اگر پیام در کانال رفته، دوباره منتشر نکن.")
    )


async def claim_job(db: AsyncSession, name: str = "automation", seconds: int = 50) -> bool:
    now = datetime.now(timezone.utc)
    until = now + timedelta(seconds=seconds)
    result = await db.execute(
        update(JobLock)
        .where(JobLock.name == name, JobLock.locked_until <= now)
        .values(locked_until=until, owner=WORKER_ID)
    )
    if (result.rowcount or 0) > 0:
        return True
    if await db.get(JobLock, name) is not None:
        return False
    try:
        async with db.begin_nested():
            db.add(JobLock(name=name, owner=WORKER_ID, locked_until=until))
            await db.flush()
    except IntegrityError:
        return False
    return True


def _priority(source: NewsSource) -> int:
    return PRIORITY.get(getattr(source, "priority", None) or "normal", 1)


async def _hashtags(db: AsyncSession, category: str, text: str) -> list[str]:
    rules = (await db.execute(select(HashtagRule).order_by(HashtagRule.priority.desc(), HashtagRule.tag))).scalars().all()
    if not rules:
        return choose_hashtags(category, text)
    enabled = {rule.tag for rule in rules if rule.enabled and not rule.forbidden}
    forbidden = {rule.tag for rule in rules if rule.forbidden}
    catalog = [(rule.tag, rule.category or "general") for rule in rules]
    return choose_hashtags(category, text, enabled=enabled, forbidden=forbidden, catalog=catalog)


async def _analyze(db: AsyncSession, text: str, created_at, runtime, image_note: str = "") -> dict:
    decision = analyze_post(text)
    judgment = judge_value(text, created_at=created_at)
    base = {
        "category": decision.category,
        "strategy": decision.strategy,
        "template_family": decision.template_family,
        "value": judgment["value"],
        "importance": judgment["importance"],
        "confidence": judgment["confidence"],
        "reasons": list(decision.reasons) + list(judgment.get("reasons") or []),
        "facts": extract_facts(text),
        "summary": "",
    }
    if runtime is None or not runtime.ai_ready:
        return base
    raw = await complete_text(runtime, [
        {"role": "system", "content": await active_prompt(db, "analyzer")},
        {"role": "user", "content": wrap_post(text[:1600]) + (f"\n\nتوضیح عکس:\n{image_note[:500]}" if image_note else "")},
    ])
    return merge_analysis(base, parse_analysis(raw), text)


async def _validate(db: AsyncSession, source: str, body: str, runtime) -> bool:
    if runtime is None or not runtime.ai_ready:
        return True
    raw = await complete_text(runtime, [
        {"role": "system", "content": await active_prompt(db, "validator")},
        {"role": "user", "content": f"منبع:\n{wrap_post(source[:1200])}\n\nتولیدشده:\n{wrap_post(body[:1200])}"},
    ])
    verdict = (raw or "").strip().upper()
    return not verdict.startswith("REVIEW")


async def collect_sources(db: AsyncSession, *, force: bool = False) -> dict:
    await ensure_content_defaults(db)
    config = await get_config(db)
    if getattr(config, "paused", False) and not force:
        return {"created": 0, "skipped": "paused"}
    if not config.enabled and not force:
        return {"created": 0, "skipped": "disabled"}
    now = datetime.now(timezone.utc)
    gap = timedelta(minutes=max(5, int(getattr(config, "collect_interval_minutes", None) or 20)))
    last_collect = as_utc(config.last_collect_at)
    if not force and last_collect and last_collect > now - gap:
        return {"created": 0, "skipped": "recent"}
    from backend.app.telegram.session_login import refresh_user_credentials

    await refresh_user_credentials(db)
    runtime = await load_runtime(db)
    sources = (await db.execute(select(NewsSource).where(NewsSource.enabled == True))).scalars().all()  # noqa: E712
    sources = sorted(sources, key=_priority)
    slots = (await db.execute(select(PublishSlot).where(PublishSlot.enabled == True))).scalars().all()  # noqa: E712
    recent_rows = (
        await db.execute(
            select(DraftPost)
            .where(DraftPost.status.in_(("preview", "scheduled", "published")))
            .order_by(DraftPost.created_at.desc())
            .limit(30)
        )
    ).scalars().all()
    recent = [row.body for row in recent_rows if row.body]
    recent_emoji = [row.emoji_signature for row in recent_rows if row.emoji_signature]
    seen_rows = (
        await db.execute(
            select(DraftPost.source_content, DraftPost.content_hash)
            .where(DraftPost.source_content.is_not(None))
        )
    ).all()
    known_texts = [row[0] for row in seen_rows if row[0] and len(row[0]) >= 24]
    known_hashes = {row[1] for row in seen_rows if row[1]}
    created = 0
    filed = 0
    photos = 0
    ads = 0
    used_recent = False
    style_card = await load_card(db)
    errors: list[str] = []
    truncated_any = False
    blocked = False
    for source in sources:
        interval = max(5, int(source.interval_minutes or 20))
        source_seen = as_utc(source.last_collect_at)
        if not force and source_seen and source_seen > now - timedelta(minutes=interval):
            continue
        updates: dict = {}
        # Commit before Telegram. An open transaction here blocks the panel's
        # automation read for as long as the channel call takes.
        await db.commit()
        try:
            posts, error, truncated = await asyncio.wait_for(
                read_channel_posts(
                    source.username,
                    min_id=int(source.last_message_id or 0),
                    access_hash=getattr(source, "access_hash", None),
                    invite_hash=getattr(source, "invite_hash", None),
                    updates=updates,
                    title=source.title,
                ),
                timeout=30,
            )
        except asyncio.TimeoutError:
            posts, error, truncated = [], "خواندن این منبع بیش از حد طول کشید", False
        if updates.get("access_hash") is not None:
            source.access_hash = int(updates["access_hash"])
        if updates.get("title"):
            source.title = updates["title"]
        if not error and not posts and (force or source.last_collect_at is None) and int(source.last_message_id or 0) > 0:
            try:
                posts, error, truncated = await asyncio.wait_for(
                    read_channel_posts(
                        source.username,
                        min_id=0,
                        access_hash=getattr(source, "access_hash", None),
                        invite_hash=getattr(source, "invite_hash", None),
                        updates=updates,
                        title=source.title,
                        recent=True,
                    ),
                    timeout=30,
                )
            except asyncio.TimeoutError:
                posts, error, truncated = [], "خواندن پست‌های اخیر این منبع بیش از حد طول کشید", False
            used_recent = True
            truncated = False
        if error:
            source.last_error = error[:300]
            errors.append(error)
            await write_log(db, "collect_error", f"{source.username}: {error}", "warning")
            if "نشست" in error:
                await alert_admin(db, f"session:{source.username}", f"نشست خبر نتوانست {source.username} را بخواند. از تنظیمات نقش خبر را روشن کن.", runtime)
                break
            continue
        source.last_error = None
        handled: set[int] = set()
        stop_before = None
        for item in posts:
            message_id = int(item["id"])
            if not item.get("usable", True):
                handled.add(message_id)
                continue
            key = f"{source.username}:{message_id}"
            exists = (await db.execute(select(DraftPost.id).where(DraftPost.source_key == key))).first()
            digest = content_hash(item["text"])
            if digest and digest not in known_hashes:
                duplicate = (await db.execute(select(DraftPost.id).where(DraftPost.content_hash == digest))).first()
                if duplicate:
                    known_hashes.add(digest)
            if exists:
                handled.add(message_id)
                continue
            if repeat_source(item["text"], known_texts, digest, known_hashes):
                _remember_seen(db, source, item, digest, config)
                known_hashes.add(digest)
                if item.get("text"):
                    known_texts.append(item["text"])
                handled.add(message_id)
                await write_log(db, "collect_skip", f"{source.username}:{message_id} REPEAT")
                continue
            from backend.app.content.intake import promotion_reason
            from backend.app.content.reading import blend_style, image_ad_reason, review_ad

            photo_path = item.get("photo_path") if safe_photo_path(item.get("photo_path")) else None
            image_note = ""
            seen: dict = {}
            text_ad = promotion_reason(item["text"])
            if photo_path and not text_ad and runtime is not None and runtime.ai_ready:
                photos += 1
                try:
                    raw_photo = safe_photo_path(photo_path).read_bytes()
                    seen = await describe_image(runtime, raw_photo, item["text"])
                except Exception:
                    logger.info("image describe skipped")
                    seen = {"text": None, "model": "", "provider": ""}
                image_note = (seen.get("text") or "").strip()
            style = classify_style(item["text"], image_note)
            ad_reason = text_ad or image_ad_reason(image_note, item["text"])
            judgment = judge_value(item["text"], created_at=item.get("date"), style=style, image_note=image_note)
            if ad_reason or judgment["value"] == "ADVERTISEMENT":
                ads += 1
                _remember_skip(db, source, item, "ADVERTISEMENT", config, ad_reason or "تبلیغ")
                handled.add(message_id)
                await write_log(db, "collect_skip", f"{source.username}:{message_id} AD {ad_reason or judgment['value']}")
                continue
            if judgment["value"] != "ADVERTISEMENT":
                filed += await remember_sample(
                    db,
                    source_key=key,
                    source_label=source.title or item.get("title") or source.username,
                    text=item["text"],
                )
            if judgment["value"] in {"LOW_VALUE", "OUTDATED"} and not keep_fun(item["text"], judgment, style):
                _remember_skip(db, source, item, judgment["value"], config)
                handled.add(message_id)
                await write_log(db, "collect_skip", f"{source.username}:{message_id} {judgment['value']}")
                continue
            if runtime is None or not runtime.ai_ready:
                stop_before = message_id
                config.last_error = "هوش مصنوعی آماده نیست؛ پیش‌نویس ساخته نشد"
                await write_log(db, "collect_not_ready", source.username, "warning")
                await alert_admin(db, "ai-not-ready", "هوش مصنوعی آماده نیست. جمع‌آوری روی همین پیام مانده.", runtime)
                break
            analysis = await _analyze(db, item["text"], item.get("date"), runtime, image_note)
            if photo_path:
                analysis["photo_path"] = str(safe_photo_path(photo_path))
                analysis["vision_model"] = seen.get("model") or ""
                analysis["vision_provider"] = seen.get("provider") or ""
            style, model_ad, tone = blend_style(item["text"], image_note, analysis if analysis.get("ai") else None)
            if model_ad:
                ads += 1
                _remember_skip(db, source, item, "ADVERTISEMENT", config, model_ad)
                handled.add(message_id)
                await write_log(db, "collect_skip", f"{source.username}:{message_id} AD {model_ad}")
                continue
            analysis["has_media"] = bool(item.get("has_media") or photo_path or item.get("video_path"))
            analysis["image_note"] = image_note
            paths = [path for path in (item.get("photo_paths") or []) if path]
            if photo_path and photo_path not in paths:
                paths.insert(0, photo_path)
            if paths:
                analysis["photo_paths"] = paths
            if item.get("video_path"):
                analysis["video_path"] = item["video_path"]
            if item.get("media_kind"):
                analysis["media_kind"] = item["media_kind"]
            plan = rewrite_plan(item["text"])
            if style == "fun" and len((item["text"] or "").strip()) <= 220:
                plan = "preserve"
            analysis["rewrite"] = plan
            analysis["style"] = style
            analysis["style_label"] = folder_label(style)
            analysis["tone"] = tone
            analysis["content_kind"] = style
            analysis["reading"] = (
                "شوخی یا میم است؛ خبر نیست و باید کوتاه و صمیمی بماند"
                if style == "fun"
                else "خبر یا اطلاعیه است و لحن باید جدی بماند"
                if style in {"flash", "announce", "alert"}
                else "از روی متن و عکس با هم خوانده شد"
            )
            if review_ad(analysis if analysis.get("ai") else None, None):
                analysis["needs_review"] = True
                analysis["reading"] = str(analysis.get("ad_reason") or "احتمال تبلیغ کم است؛ در صف می‌ماند تا خودت ببینی")
            category = folder_category(style)
            decision = analyze_post(item["text"])
            choice = choose_template(decision, channel_style=None, recent_emoji_styles=recent_emoji)
            layout = "quiet" if choice.emoji_style_id == "quiet" else layout_for(category, style, plan)
            openings = [opening_signature(body) for body in recent[-6:]]
            style_card = await load_card(db)
            prompt = await compose_prompt(db, "generator")
            trace: dict = {}
            body, _category, reason = await draft_from_source(
                item["text"],
                item.get("title") or source.username,
                runtime,
                mode="generate",
                avoid=openings,
                template_hint=angle_label(style),
                system_prompt=prompt,
                style=style,
                style_card=style_card,
                plan=plan,
                image_note=image_note or None,
                lessons=getattr(config, "lessons_json", None),
                trace=trace,
            )
            analysis["writer_model"] = trace.get("writer_model") or ""
            analysis["writer_provider"] = trace.get("writer_provider") or ""
            analysis["layout"] = layout
            seen_at = source_stamp(item.get("date"))
            if seen_at:
                analysis["source_at"] = seen_at
            if trace.get("repaired"):
                config.lessons_json = push_lesson(
                    getattr(config, "lessons_json", None),
                    kind="repair",
                    category=category,
                    note=f"خبر دسته {category} را SKIP نکن؛ قابل بازنویسی است",
                )
            if body and too_similar(body, recent):
                fresh_prompt = await compose_prompt(db, "regenerator_fresh")
                alt, _alt_category, alt_reason = await draft_from_source(
                    item["text"],
                    item.get("title") or source.username,
                    runtime,
                    mode="fresh",
                    avoid=openings,
                    template_hint=angle_label(style),
                    system_prompt=fresh_prompt,
                    style=style,
                    style_card=style_card,
                    plan=plan,
                    image_note=image_note or None,
                    lessons=getattr(config, "lessons_json", None),
                )
                if alt and not too_similar(alt, recent):
                    body = alt
                    reason = alt_reason
                else:
                    _remember_seen(db, source, item, digest, config)
                    known_hashes.add(digest)
                    known_texts.append(item["text"])
                    handled.add(message_id)
                    await write_log(db, "collect_skip", f"{source.username}:{message_id} SIMILAR")
                    continue
            if not body:
                db.add(DraftPost(
                    status="skipped",
                    category=category,
                    body="",
                    source_content=item["text"],
                    source_label=source.title or source.username,
                    source_key=key,
                    source_url=source_url(source.username, message_id),
                    content_hash=digest,
                    analysis_json=json.dumps(analysis, ensure_ascii=False),
                    confidence="low",
                    error=human_reason(reason),
                    target_chat_id=config.target_chat_id,
                ))
                handled.add(message_id)
                await write_log(db, "collect_rejected", f"{source.username}:{message_id} {reason}")
                continue
            if style == "fun" and body and len((item["text"] or "").strip()) < 180 and len(body) > max(220, len(item["text"]) * 3):
                kept = re.sub(r"#\S+", "", item["text"] or "")
                kept = re.sub(r"https?://\S+", "", kept).strip()
                if 12 <= len(kept) <= 320:
                    body = kept
            tags = await _hashtags(db, category, item["text"])
            if style == "fun":
                tags = [tag for tag in tags if tag not in {"خبر", "اطلاعیه", "مشاوره"}]
                if "طنز" not in tags:
                    tags.insert(0, "طنز")
                tags = tags[:3]
            credit = attribution_line(source.username, getattr(config, "attribution_mode", None) or "news", category)
            if credit and credit not in body:
                body = f"{body.strip()}\n\n{credit}"
            body = append_hashtags(body, tags)
            validated = await _validate(db, item["text"] + (f"\n{image_note}" if image_note else ""), body, runtime)
            auto = (
                bool(config.auto_publish)
                and not getattr(config, "paused", False)
                and should_auto_schedule(analysis, validated, False)
            )
            when = next_slot_time(list(slots), category=category) if auto else None
            draft = DraftPost(
                status="scheduled" if auto and when else "preview",
                category=category,
                body=body,
                source_content=item["text"],
                source_label=source.title or source.username,
                source_key=key,
                source_url=source_url(source.username, message_id),
                content_hash=digest,
                analysis_json=json.dumps(analysis, ensure_ascii=False),
                hashtags=" ".join(f"#{tag}" for tag in tags),
                template_id=f"{choice.template_id}.{style}",
                style_id=choice.style_id,
                emoji_signature=layout,
                confidence=analysis.get("confidence"),
                importance=analysis.get("importance"),
                scheduled_at=when.astimezone(timezone.utc) if when else None,
                target_chat_id=config.target_chat_id,
                error=None if validated and not analysis.get("needs_review") else "needs_review",
            )
            db.add(draft)
            await db.flush()
            await remember_paths(db, draft.id, paths)
            if draft.status == "scheduled":
                db.add(AutomationJob(
                    kind="publish",
                    ref_id=draft.id,
                    status="pending",
                    next_run_at=draft.scheduled_at,
                ))
            recent.append(body)
            known_texts.append(item["text"])
            known_hashes.add(digest)
            recent_emoji.append(choice.emoji_style_id)
            handled.add(message_id)
            created += 1
        source.last_message_id = cursor_after(int(source.last_message_id or 0), posts, handled, stop_before)
        if truncated and stop_before is None:
            truncated_any = True
        else:
            source.last_collect_at = now
        if stop_before is not None:
            blocked = True
            break
    if not truncated_any:
        config.last_collect_at = now
    if errors:
        config.last_error = errors[0]
    elif not blocked:
        config.last_error = None
    if filed:
        style_card = await load_card(db)
    await write_log(db, "collect_done", f"created={created} filed={filed}")
    await db.flush()
    return {
        "created": created,
        "errors": errors,
        "truncated": truncated_any,
        "filed": filed,
        "photos": photos,
        "ads": ads,
        "recent": used_recent,
    }


async def published_today(db: AsyncSession, now: datetime | None = None) -> dict[str, int]:
    from backend.app.services.autopost import tehran_now

    start = tehran_now(now).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    rows = (
        await db.execute(
            select(DraftPost.category, func.count())
            .where(DraftPost.status == "published", DraftPost.published_at.is_not(None), DraftPost.published_at >= start)
            .group_by(DraftPost.category)
        )
    ).all()
    return {category or "news": int(count) for category, count in rows}


def _analysis_dict(raw: str | None) -> dict:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


async def recent_emoji_ids(db: AsyncSession, exclude_id: str | None = None) -> set[str]:
    rows = (
        await db.execute(
            select(DraftPost.id, DraftPost.analysis_json)
            .where(DraftPost.status.in_(("published", "sending", "scheduled")))
            .order_by(DraftPost.updated_at.desc())
            .limit(16)
        )
    ).all()
    found: set[str] = set()
    for draft_id, raw in rows:
        if exclude_id and draft_id == exclude_id:
            continue
        for item in _analysis_dict(raw).get("emoji_ids") or []:
            if str(item).isdigit():
                found.add(str(item))
    return found


async def deliver_draft(db: AsyncSession, draft: DraftPost, chat_id: int) -> tuple[int | None, str | None]:
    if not (draft.body or "").strip():
        return None, "متن پیش‌نویس خالی است"
    from backend.app.content.intake import photo_paths_of, video_of
    from backend.app.formatting.spectrum import spectrum_of
    from backend.app.telegram.sent_mark import drain_sent_ids, fingerprint

    analysis = _analysis_dict(draft.analysis_json)
    style = str(analysis.get("style") or "")
    maps = await load_emoji_maps(db)
    photos = photo_paths_of(draft.analysis_json)
    video = video_of(draft.analysis_json)
    has_media = bool(photos or video)
    avoid = await recent_emoji_ids(db, draft.id)
    config = await get_config(db)
    payload = prepare_publish_payload(
        draft.body,
        spectrum_of(style or draft.category),
        "quiet" if draft.emoji_signature == "quiet" else draft.emoji_signature,
        maps,
        is_caption=has_media,
        avoid_emoji_ids=avoid,
        footer=configured_footer(getattr(config, "footer_text", None)),
    )
    analysis["emoji_ids"] = payload["emoji_ids"]
    analysis["sent_fp"] = fingerprint(payload["text"])
    draft.analysis_json = json.dumps(analysis, ensure_ascii=False)
    await db.commit()
    try:
        message_id, error = await asyncio.wait_for(
            publish_rendered(
                chat_id,
                payload["text"],
                payload["html_text"],
                payload["entities"],
                photos[0] if photos else None,
                photos,
                video,
            ),
            timeout=45 if has_media else 25,
        )
    except asyncio.TimeoutError:
        return None, "ارسال به تلگرام بیش از حد طول کشید"
    sent_ids = drain_sent_ids(chat_id)
    if message_id and message_id not in sent_ids:
        sent_ids.insert(0, message_id)
    if not message_id:
        analysis.pop("sent_fp", None)
        analysis.pop("sent_ids", None)
        draft.analysis_json = json.dumps(analysis, ensure_ascii=False)
        await db.commit()
        return None, error or "ارسال نشد"
    if sent_ids:
        analysis["sent_ids"] = sent_ids
        draft.analysis_json = json.dumps(analysis, ensure_ascii=False)
    return message_id, error


def mark_publish_failure(draft: DraftPost, error: str, now: datetime) -> None:
    draft.retry_count = (draft.retry_count or 0) + 1
    draft.error = safe_detail(error)
    if draft.retry_count < 3:
        draft.status = "scheduled"
        draft.next_retry_at = next_retry_at(draft.retry_count, now)
        # A slot failure used to leave scheduled_at empty, so the retry query
        # never saw the draft again and the day's slot was already consumed.
        planned = as_utc(draft.scheduled_at)
        retry = as_utc(draft.next_retry_at)
        if planned is None or (retry is not None and planned < retry):
            draft.scheduled_at = draft.next_retry_at
    else:
        draft.status = "failed"
        draft.next_retry_at = None


async def publish_due(db: AsyncSession) -> dict:
    config = await get_config(db)
    if getattr(config, "paused", False):
        return {"published": 0, "skipped": "paused"}
    if not config.target_chat_id:
        return {"published": 0, "error": "کانال مقصد انتخاب نشده"}
    now = datetime.now(timezone.utc)
    published = 0
    await recover_stuck_sends(db, now)
    counts = await published_today(db, now)
    cap = int(getattr(config, "daily_cap", None) or 6)
    balance = bool(getattr(config, "balance_categories", True))
    due = (
        await db.execute(
            select(DraftPost).where(
                DraftPost.status == "scheduled",
                DraftPost.scheduled_at.is_not(None),
                DraftPost.scheduled_at <= now,
            ).limit(20)
        )
    ).scalars().all()
    due = [row for row in due if (retry := as_utc(row.next_retry_at)) is None or retry <= now]
    queued = {row.category for row in due}
    for draft in due:
        if not pick_balanced([draft], None, counts, cap, balance):
            await write_log(db, "publish_held", f"{draft.id} cap_or_balance")
            continue
        if not await claim_for_publish(db, draft.id, ("scheduled",)):
            continue
        await db.commit()
        draft.status = "sending"
        message_id, error = await deliver_draft(db, draft, int(config.target_chat_id))
        draft.target_chat_id = config.target_chat_id
        job = (
            await db.execute(
                select(AutomationJob).where(AutomationJob.ref_id == draft.id, AutomationJob.kind == "publish")
            )
        ).scalars().first()
        if error:
            mark_publish_failure(draft, error, now)
            if job:
                job.status = "retry" if draft.status == "scheduled" else "failed"
                job.attempts = draft.retry_count
                job.next_run_at = draft.next_retry_at
                job.last_error = draft.error
            await write_log(db, "publish_failed", f"{draft.id} {draft.error}", "warning")
            await alert_admin(db, f"publish:{draft.id}:{draft.retry_count}", f"انتشار پیش‌نویس ناموفق ماند: {draft.error}")
            continue
        draft.status = "published"
        draft.published_at = now
        draft.message_id = message_id
        draft.error = None
        draft.next_retry_at = None
        counts[draft.category] = counts.get(draft.category, 0) + 1
        if job:
            job.status = "done"
            job.attempts = (job.attempts or 0) + 1
            job.last_error = None
        await write_log(db, "published", str(draft.id))
        config.lessons_json = push_lesson(
            getattr(config, "lessons_json", None),
            kind="published",
            category=draft.category or "",
            note=f"دسته {draft.category or 'news'} منتشر شد؛ برای خبر فقط یک ایموجی عنوان بگذار",
        )
        published += 1
    if config.enabled and config.auto_publish and not getattr(config, "paused", False):
        slots = (await db.execute(select(PublishSlot))).scalars().all()
        used = {
            key
            for key in (await db.execute(select(DraftPost.slot_key).where(DraftPost.slot_key.is_not(None)))).scalars().all()
            if key
        }
        waiting = (
            await db.execute(
                select(DraftPost).where(DraftPost.status == "preview").order_by(DraftPost.created_at).limit(80)
            )
        ).scalars().all()
        for slot in slots:
            if not slot_is_due(slot, used_keys=used):
                continue
            draft = pick_balanced(list(waiting), slot.category, counts, cap, balance)
            if draft is None:
                await write_log(db, "slot_empty", slot.category or "any")
                continue
            if not await claim_for_publish(db, draft.id, ("preview",)):
                waiting = [item for item in waiting if item.id != draft.id]
                continue
            await db.commit()
            draft.status = "sending"
            waiting = [item for item in waiting if item.id != draft.id]
            message_id, error = await deliver_draft(db, draft, int(config.target_chat_id))
            draft.target_chat_id = config.target_chat_id
            waiting = [item for item in waiting if item.id != draft.id]
            if error:
                mark_publish_failure(draft, error, now)
                await write_log(db, "publish_failed", f"{draft.id} {draft.error}", "warning")
                await alert_admin(db, f"publish:{draft.id}:{draft.retry_count}", f"انتشار پیش‌نویس ناموفق ماند: {draft.error}")
                continue
            key = slot_key(slot)
            draft.slot_key = key
            used.add(key)
            draft.status = "published"
            draft.published_at = now
            draft.message_id = message_id
            draft.error = None
            counts[draft.category] = counts.get(draft.category, 0) + 1
            published += 1
            await write_log(db, "published", str(draft.id))
            config.lessons_json = push_lesson(
                getattr(config, "lessons_json", None),
                kind="published",
                category=draft.category or "",
                note=f"دسته {draft.category or 'news'} منتشر شد؛ برای خبر فقط یک ایموجی عنوان بگذار",
            )
    await db.flush()
    return {"published": published}


async def automation_loop(stop) -> None:
    import asyncio
    from backend.app.db.base import get_session_factory

    while not stop.is_set():
        try:
            factory = get_session_factory()
            async with factory() as db:
                if not await claim_job(db):
                    await db.rollback()
                else:
                    await publish_due(db)
                    await collect_sources(db)
                    await db.commit()
        except Exception:
            logger.exception("automation tick failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=60)
        except asyncio.TimeoutError:
            continue
