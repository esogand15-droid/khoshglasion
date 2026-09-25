"""One tick of the news automation. Safe to call from the panel or the loop."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
    pick_angle,
    should_auto_schedule,
    source_url,
    too_similar,
)
from backend.app.content.publish import prepare_publish_payload
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
from backend.app.services.ai import complete_text
from backend.app.services.autopost import (
    active_prompt,
    compose_prompt,
    append_hashtags,
    draft_from_source,
    ensure_content_defaults,
    get_config,
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


def _remember_skip(db: AsyncSession, source: NewsSource, item: dict, reason: str, config) -> None:
    db.add(DraftPost(
        status="skipped",
        category=source.category_hint or "news",
        body="",
        source_content=item.get("text") or "",
        source_label=source.username,
        source_key=f"{source.username}:{int(item['id'])}",
        content_hash=content_hash(item.get("text") or "") or None,
        error=reason[:120],
        confidence="low",
        analysis_json=json.dumps({"value": reason, "has_media": bool(item.get("has_media"))}, ensure_ascii=False),
        target_chat_id=config.target_chat_id,
    ))


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


async def _analyze(db: AsyncSession, text: str, created_at, runtime) -> dict:
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
        {"role": "user", "content": wrap_post(text[:1800])},
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
    if not force and config.last_collect_at and config.last_collect_at > now - gap:
        return {"created": 0, "skipped": "recent"}
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
    recent_angles = [row.template_id.rsplit(".", 1)[-1] for row in recent_rows if row.template_id]
    created = 0
    errors: list[str] = []
    truncated_any = False
    for source in sources:
        interval = max(5, int(source.interval_minutes or 20))
        if (
            not force
            and source.last_collect_at
            and source.last_collect_at > now - timedelta(minutes=interval)
        ):
            continue
        posts, error, truncated = await read_channel_posts(source.username, min_id=int(source.last_message_id or 0))
        if error:
            source.last_error = error[:300]
            errors.append(error)
            await write_log(db, "collect_error", f"{source.username}: {error}", "warning")
            if "نشست" in error:
                await alert_admin(db, f"session:{source.username}", f"نشست پرمیوم نتوانست {source.username} را بخواند.", runtime)
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
            duplicate = (await db.execute(select(DraftPost.id).where(DraftPost.content_hash == digest))).first()
            if exists:
                handled.add(message_id)
                continue
            if duplicate:
                _remember_skip(db, source, item, "DUPLICATE", config)
                handled.add(message_id)
                await write_log(db, "collect_skip", f"{source.username}:{message_id} DUPLICATE")
                continue
            judgment = judge_value(item["text"], created_at=item.get("date"))
            if judgment["value"] in {"LOW_VALUE", "ADVERTISEMENT", "OUTDATED"}:
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
            analysis = await _analyze(db, item["text"], item.get("date"), runtime)
            analysis["has_media"] = bool(item.get("has_media"))
            category = source.category_hint or analysis.get("category") or "news"
            decision = analyze_post(item["text"])
            choice = choose_template(decision, channel_style=None, recent_emoji_styles=recent_emoji)
            angle_key, angle_label = pick_angle(recent_angles)
            openings = [opening_signature(body) for body in recent[-6:]]
            prompt = await compose_prompt(db, "generator")
            body, _category, reason = await draft_from_source(
                item["text"],
                item.get("title") or source.username,
                runtime,
                mode="generate",
                avoid=openings,
                template_hint=angle_label,
                system_prompt=prompt,
            )
            similar = False
            if body and too_similar(body, recent):
                fresh_prompt = await compose_prompt(db, "regenerator_fresh")
                alt, _alt_category, alt_reason = await draft_from_source(
                    item["text"],
                    item.get("title") or source.username,
                    runtime,
                    mode="fresh",
                    avoid=openings,
                    template_hint=angle_label,
                    system_prompt=fresh_prompt,
                )
                if alt and not too_similar(alt, recent):
                    body = alt
                    reason = alt_reason
                else:
                    similar = True
            if not body:
                db.add(DraftPost(
                    status="skipped",
                    category=category,
                    body="",
                    source_content=item["text"],
                    source_label=source.username,
                    source_key=key,
                    source_url=source_url(source.username, message_id),
                    content_hash=digest,
                    analysis_json=json.dumps(analysis, ensure_ascii=False),
                    confidence="low",
                    error=reason or "rejected",
                    target_chat_id=config.target_chat_id,
                ))
                handled.add(message_id)
                await write_log(db, "collect_rejected", f"{source.username}:{message_id} {reason}")
                continue
            tags = await _hashtags(db, category, item["text"])
            credit = attribution_line(source.username, getattr(config, "attribution_mode", None) or "news", category)
            if credit and credit not in body:
                body = f"{body.strip()}\n\n{credit}"
            body = append_hashtags(body, tags)
            validated = await _validate(db, item["text"], body, runtime)
            auto = (
                bool(config.auto_publish)
                and not getattr(config, "paused", False)
                and should_auto_schedule(analysis, validated and not similar, similar)
            )
            when = next_slot_time(list(slots), category=category) if auto else None
            draft = DraftPost(
                status="scheduled" if auto and when else "preview",
                category=category,
                body=body,
                source_content=item["text"],
                source_label=source.username,
                source_key=key,
                source_url=source_url(source.username, message_id),
                content_hash=digest,
                analysis_json=json.dumps(analysis, ensure_ascii=False),
                hashtags=" ".join(f"#{tag}" for tag in tags),
                template_id=f"{choice.template_id}.{angle_key}",
                style_id=choice.style_id,
                emoji_signature=choice.emoji_style_id,
                confidence=analysis.get("confidence"),
                importance=analysis.get("importance"),
                scheduled_at=when.astimezone(timezone.utc) if when else None,
                target_chat_id=config.target_chat_id,
                error="similar" if similar else (None if validated else "needs_review"),
            )
            db.add(draft)
            await db.flush()
            if draft.status == "scheduled":
                db.add(AutomationJob(
                    kind="publish",
                    ref_id=draft.id,
                    status="pending",
                    next_run_at=draft.scheduled_at,
                ))
            recent.append(body)
            recent_emoji.append(choice.emoji_style_id)
            recent_angles.append(angle_key)
            handled.add(message_id)
            created += 1
        source.last_message_id = cursor_after(int(source.last_message_id or 0), posts, handled, stop_before)
        if truncated and stop_before is None:
            truncated_any = True
        else:
            source.last_collect_at = now
        if stop_before is not None:
            break
    if not truncated_any:
        config.last_collect_at = now
    config.last_error = errors[0] if errors else config.last_error
    await write_log(db, "collect_done", f"created={created}")
    await db.flush()
    return {"created": created, "errors": errors, "truncated": truncated_any}


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


async def deliver_draft(db: AsyncSession, draft: DraftPost, chat_id: int) -> tuple[int | None, str | None]:
    if not (draft.body or "").strip():
        return None, "متن پیش‌نویس خالی است"
    maps = await load_emoji_maps(db)
    payload = prepare_publish_payload(draft.body, draft.category, draft.emoji_signature, maps)
    return await publish_rendered(chat_id, payload["text"], payload["html_text"], payload["entities"])


def mark_publish_failure(draft: DraftPost, error: str, now: datetime) -> None:
    draft.retry_count = (draft.retry_count or 0) + 1
    draft.error = safe_detail(error)
    if draft.retry_count < 3:
        draft.status = "scheduled"
        draft.next_retry_at = next_retry_at(draft.retry_count, now)
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
    counts = await published_today(db, now)
    cap = int(getattr(config, "daily_cap", None) or 6)
    balance = bool(getattr(config, "balance_categories", True))
    due = (
        await db.execute(
            select(DraftPost).where(
                DraftPost.status == "scheduled",
                DraftPost.scheduled_at.is_not(None),
                DraftPost.scheduled_at <= now,
            )
        )
    ).scalars().all()
    due = [row for row in due if row.next_retry_at is None or row.next_retry_at <= now]
    queued = {row.category for row in due}
    for draft in due:
        if not pick_balanced([draft], None, counts, cap, balance):
            await write_log(db, "publish_held", f"{draft.id} cap_or_balance")
            continue
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
        published += 1
    if config.enabled and config.auto_publish and not getattr(config, "paused", False):
        slots = (await db.execute(select(PublishSlot))).scalars().all()
        used = {
            key
            for key in (await db.execute(select(DraftPost.slot_key).where(DraftPost.slot_key.is_not(None)))).scalars().all()
            if key
        }
        waiting = (
            await db.execute(select(DraftPost).where(DraftPost.status == "preview").order_by(DraftPost.created_at))
        ).scalars().all()
        for slot in slots:
            if not slot_is_due(slot, used_keys=used):
                continue
            draft = pick_balanced(list(waiting), slot.category, counts, cap, balance)
            if draft is None:
                await write_log(db, "slot_empty", slot.category or "any")
                continue
            message_id, error = await deliver_draft(db, draft, int(config.target_chat_id))
            key = slot_key(slot)
            draft.slot_key = key
            used.add(key)
            draft.target_chat_id = config.target_chat_id
            waiting = [item for item in waiting if item.id != draft.id]
            if error:
                mark_publish_failure(draft, error, now)
                await write_log(db, "publish_failed", f"{draft.id} {draft.error}", "warning")
                await alert_admin(db, f"publish:{draft.id}:{draft.retry_count}", f"انتشار پیش‌نویس ناموفق ماند: {draft.error}")
                continue
            draft.status = "published"
            draft.published_at = now
            draft.message_id = message_id
            draft.error = None
            counts[draft.category] = counts.get(draft.category, 0) + 1
            published += 1
            await write_log(db, "published", str(draft.id))
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
