from datetime import datetime, timezone
import json
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.content.links import channel_message_url
from backend.app.content.publish import prepare_publish_payload
from backend.app.db.base import get_db
from backend.app.core.runtime import load_runtime
from backend.app.formatting.diff import line_diff
from backend.app.models.automation import AutomationLog, DraftPost, HashtagRule, NewsSource, PromptVersion, PublishSlot
from backend.app.models.channel import Channel
from backend.app.security.deps import assert_editor, assert_publisher, get_current_admin
from backend.app.services.audit import write_audit
from backend.app.services.automation_runner import claim_for_publish, collect_sources, deliver_draft, publish_due, published_today
from backend.app.telegram.collector import probe_channel, register_joined_invite
from backend.app.telegram.pipeline import load_emoji_maps
from backend.app.telegram.publisher import delete_published, publish_rendered
from backend.app.content.pipeline import normalize_hashtag
from backend.app.content.prompts import PROMPTS
from backend.app.services.autopost import (
    compose_prompt,
    draft_from_source,
    ensure_content_defaults,
    get_config,
    next_slot_time,
    normalize_source,
    parse_invite_hash,
    human_reason,
    remember_lesson,
    remember_version,
)

router = APIRouter(prefix="/api/automation", tags=["automation"])
logger = logging.getLogger(__name__)


def dump_source(row: NewsSource) -> dict:
    return {
        "id": row.id,
        "username": row.username,
        "title": row.title,
        "enabled": row.enabled,
        "category_hint": row.category_hint,
        "priority": row.priority,
        "interval_minutes": row.interval_minutes,
        "last_message_id": row.last_message_id,
        "last_error": row.last_error,
    }


def dump_slot(row: PublishSlot) -> dict:
    return {"id": row.id, "hour": row.hour, "minute": row.minute, "category": row.category, "enabled": row.enabled}


def _versions(raw: str | None) -> list[dict]:
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [
        {"version": item.get("version"), "reason": item.get("reason"), "body": item.get("body")}
        for item in data
        if isinstance(item, dict)
    ]


def _draft_photo(row: DraftPost):
    from backend.app.content.intake import photo_of

    return photo_of(row.analysis_json)


def _analysis_flag(raw: str | None, key: str):
    try:
        data = json.loads(raw or "")
    except json.JSONDecodeError:
        return None
    return data.get(key) if isinstance(data, dict) else None


def dump_draft(row: DraftPost, username: str | None = None) -> dict:
    return {
        "id": row.id,
        "status": row.status,
        "category": row.category,
        "body": row.body,
        "source_label": row.source_label,
        "scheduled_at": _iso(row.scheduled_at),
        "published_at": _iso(row.published_at),
        "target_chat_id": row.target_chat_id,
        "message_id": row.message_id,
        "error": row.error,
        "source_content": row.source_content,
        "hashtags": row.hashtags,
        "confidence": row.confidence,
        "importance": row.importance,
        "version": row.version,
        "retry_count": row.retry_count,
        "next_retry_at": _iso(row.next_retry_at),
        "template_id": row.template_id,
        "emoji_signature": row.emoji_signature,
        "analysis_summary": _summary(row.analysis_json),
        "style_label": _analysis_flag(row.analysis_json, "style_label"),
        "source_url": row.source_url,
        "published_url": channel_message_url(row.target_chat_id, row.message_id, username),
        "has_media": bool(_analysis_flag(row.analysis_json, "has_media")),
        "has_photo": _draft_photo(row) is not None,
        "image_note": _analysis_flag(row.analysis_json, "image_note") or "",
        "rewrite": _analysis_flag(row.analysis_json, "rewrite") or "",
        "writer_model": _analysis_flag(row.analysis_json, "writer_model") or "",
        "vision_model": _analysis_flag(row.analysis_json, "vision_model") or "",
        "versions": _versions(row.versions_json),
        "created_at": _iso(row.created_at),
    }


def _summary(raw: str | None) -> str:
    try:
        data = json.loads(raw or "")
    except json.JSONDecodeError:
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("summary") or "")[:180]


class SourceIn(BaseModel):
    username: str
    category_hint: str | None = None
    priority: str | None = None
    interval_minutes: int | None = Field(default=None, ge=5, le=240)


class SourcePatch(BaseModel):
    enabled: bool | None = None
    category_hint: str | None = None
    priority: str | None = None
    interval_minutes: int | None = Field(default=None, ge=5, le=240)


class SlotIn(BaseModel):
    hour: int = Field(ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    category: str | None = None


class ConfigIn(BaseModel):
    enabled: bool | None = None
    auto_publish: bool | None = None
    paused: bool | None = None
    attribution_mode: str | None = None
    target_chat_id: int | None = None
    daily_cap: int | None = Field(default=None, ge=1, le=48)
    balance_categories: bool | None = None
    collect_interval_minutes: int | None = Field(default=None, ge=5, le=240)


class HashtagIn(BaseModel):
    enabled: bool | None = None
    forbidden: bool | None = None
    category: str | None = None
    priority: int | None = Field(default=None, ge=1, le=200)


class HashtagCreate(BaseModel):
    tag: str
    category: str = "general"
    priority: int = Field(default=60, ge=1, le=200)
    enabled: bool = True


class PromptIn(BaseModel):
    name: str
    body: str = Field(min_length=24, max_length=4000)
    kind: str = "stage"


class DraftIn(BaseModel):
    body: str | None = None
    scheduled_at: str | None = None
    category: str | None = None
    hashtags: str | None = None


class SlotPatch(BaseModel):
    enabled: bool | None = None
    category: str | None = None


def _iso(value) -> str | None:
    if value is None:
        return None
    iso = getattr(value, "isoformat", None)
    return iso() if callable(iso) else str(value)


async def _finetune_snapshot(db: AsyncSession) -> dict:
    empty = {"total": 0, "card": "", "folders": []}
    try:
        async with db.begin_nested():
            from backend.app.services.finetune import snapshot

            return await snapshot(db)
    except Exception:
        # A failed Postgres statement aborts the transaction. Roll it back or
        # the page read, which already succeeded, dies on commit.
        logger.exception("finetune snapshot skipped")
        try:
            await db.rollback()
        except Exception:
            logger.exception("finetune rollback failed")
        return empty


@router.get("")
async def automation_state(
    draft_status: str | None = None,
    draft_category: str | None = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    try:
        return await _read_automation_state(draft_status, draft_category, db, admin)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("automation state failed")
        raise HTTPException(status_code=503, detail="صف اتوماسیون الان خوانده نشد. چند ثانیه بعد دوباره بزن.") from exc


async def _read_automation_state(
    draft_status: str | None = None,
    draft_category: str | None = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    # Read only. Do not SET LOCAL here: on asyncpg a failed SET aborts the
    # transaction and every later query becomes the 503 the panel shows.
    config = await get_config(db)
    sources = (await db.execute(select(NewsSource).order_by(NewsSource.created_at))).scalars().all()
    slots = (await db.execute(select(PublishSlot).order_by(PublishSlot.hour, PublishSlot.minute))).scalars().all()
    draft_query = select(DraftPost).where(DraftPost.status != "rejected").order_by(DraftPost.created_at.desc()).limit(80)
    archive_query = select(DraftPost).where(DraftPost.status == "rejected").order_by(DraftPost.created_at.desc()).limit(80)
    if draft_status and draft_status != "rejected":
        draft_query = draft_query.where(DraftPost.status == draft_status)
    if draft_category:
        draft_query = draft_query.where(DraftPost.category == draft_category)
        archive_query = archive_query.where(DraftPost.category == draft_category)
    drafts = (await db.execute(draft_query)).scalars().all()
    archived = (await db.execute(archive_query)).scalars().all()
    channels = (await db.execute(select(Channel))).scalars().all()
    names = {int(row.chat_id): row.username for row in channels if row.chat_id and row.username}
    hashtags = (await db.execute(select(HashtagRule).order_by(HashtagRule.priority.desc()))).scalars().all()
    logs = (await db.execute(select(AutomationLog).order_by(AutomationLog.created_at.desc()).limit(12))).scalars().all()
    prompts = (await db.execute(select(PromptVersion).where(PromptVersion.active == True))).scalars().all()  # noqa: E712
    counts = dict(
        (await db.execute(select(DraftPost.status, func.count()).group_by(DraftPost.status))).all()
    )
    today = await published_today(db)
    finetune = await _finetune_snapshot(db)
    return {
        "enabled": config.enabled,
        "auto_publish": config.auto_publish,
        "paused": config.paused,
        "attribution_mode": config.attribution_mode,
        "daily_cap": config.daily_cap,
        "balance_categories": config.balance_categories,
        "collect_interval_minutes": config.collect_interval_minutes,
        "target_chat_id": config.target_chat_id,
        "metrics": {
            "preview": int(counts.get("preview") or 0),
            "scheduled": int(counts.get("scheduled") or 0),
            "failed": int(counts.get("failed") or 0),
            "archive": int(counts.get("rejected") or 0),
            "published_today": sum(today.values()),
            "daily_cap": config.daily_cap,
        },
        "hashtags": [_dump_hashtag(row) for row in hashtags],
        "logs": [
            {"event": row.event, "level": row.level, "detail": row.detail, "created_at": _iso(row.created_at)}
            for row in logs
        ],
        "prompts": [_dump_prompt(row) for row in prompts],
        "alerts": [config.last_error] if config.last_error else [],
        "role": admin.role,
        "last_collect_at": _iso(config.last_collect_at),
        "last_error": config.last_error,
        "next_slot": _iso(next_slot_time(list(slots))),
        "sources": [dump_source(row) for row in sources],
        "slots": [dump_slot(row) for row in slots],
        "drafts": [dump_draft(row, names.get(int(row.target_chat_id)) if row.target_chat_id else None) for row in drafts],
        "archive": [dump_draft(row, names.get(int(row.target_chat_id)) if row.target_chat_id else None) for row in archived],
        "finetune": finetune,
    }


@router.patch("")
async def update_config(payload: ConfigIn, request: Request, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    if payload.auto_publish is True:
        assert_publisher(admin)
    if payload.attribution_mode and payload.attribution_mode not in {"news", "always", "never"}:
        raise HTTPException(status_code=400, detail="حالت منبع باید news، always یا never باشد")
    config = await get_config(db)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(config, key, value)
    await write_audit(db, admin=admin, action="update", resource="automation", new_value=data, ip_address=request.client.host if request.client else None)
    return {"ok": True, "enabled": config.enabled, "auto_publish": config.auto_publish, "target_chat_id": config.target_chat_id}


@router.post("/sources")
async def add_source(payload: SourceIn, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    from backend.app.telegram.session_login import refresh_user_credentials

    await refresh_user_credentials(db)
    if parse_invite_hash(payload.username):
        result = await register_joined_invite(
            db,
            payload.username,
            category_hint=payload.category_hint,
            priority=payload.priority,
            interval_minutes=payload.interval_minutes,
        )
        if isinstance(result, str):
            raise HTTPException(status_code=400, detail=result)
        return dump_source(result)
    username = normalize_source(payload.username)
    if not username:
        raise HTTPException(status_code=400, detail="یوزرنیم عمومی، آیدی عددی، یا لینک دعوت کانالی که اکانت خبری از قبل عضو آن است")
    existing = (await db.execute(select(NewsSource).where(NewsSource.username == username))).scalar_one_or_none()
    if existing:
        existing.enabled = True
        existing.category_hint = payload.category_hint or existing.category_hint
        if payload.priority:
            existing.priority = payload.priority
        if payload.interval_minutes:
            existing.interval_minutes = payload.interval_minutes
        return dump_source(existing)
    row = NewsSource(
        username=username,
        category_hint=payload.category_hint,
        priority=payload.priority or "normal",
        interval_minutes=payload.interval_minutes or 20,
    )
    info, error = await probe_channel(username)
    row.title = info.get("title")
    row.last_error = error
    if not error and info.get("latest_id"):
        row.last_message_id = int(info["latest_id"])
    db.add(row)
    await db.flush()
    return dump_source(row)


@router.patch("/sources/{source_id}")
async def update_source(source_id: str, payload: SourcePatch, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    row = (await db.execute(select(NewsSource).where(NewsSource.id == source_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="منبع پیدا نشد")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(row, key, value)
    return dump_source(row)


@router.post("/sources/{source_id}/probe")
async def probe_source(source_id: str, catch_up: bool = False, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    row = (await db.execute(select(NewsSource).where(NewsSource.id == source_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="منبع پیدا نشد")
    from backend.app.telegram.session_login import refresh_user_credentials

    await refresh_user_credentials(db)
    updates: dict = {}
    info, error = await probe_channel(
        row.username,
        access_hash=row.access_hash,
        invite_hash=row.invite_hash,
        updates=updates,
    )
    if updates.get("access_hash") is not None:
        row.access_hash = int(updates["access_hash"])
    row.title = updates.get("title") or info.get("title") or row.title
    row.last_error = error
    if catch_up and info.get("latest_id"):
        row.last_message_id = int(info["latest_id"])
    await write_audit(db, admin=admin, action="probe", resource="news_source", resource_id=row.id, new_value={"ok": error is None, "catch_up": catch_up})
    return {**dump_source(row), "latest_id": info.get("latest_id"), "readable": error is None}


@router.delete("/sources/{source_id}")
async def delete_source(source_id: str, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    row = (await db.execute(select(NewsSource).where(NewsSource.id == source_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="منبع پیدا نشد")
    await db.delete(row)
    return {"ok": True}


@router.post("/slots")
async def add_slot(payload: SlotIn, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    row = PublishSlot(hour=payload.hour, minute=payload.minute, category=payload.category or None)
    db.add(row)
    await db.flush()
    return dump_slot(row)


@router.patch("/slots/{slot_id}")
async def update_slot(slot_id: str, payload: SlotPatch, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    row = (await db.execute(select(PublishSlot).where(PublishSlot.id == slot_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="ساعت پیدا نشد")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(row, key, value)
    return dump_slot(row)


@router.delete("/slots/{slot_id}")
async def delete_slot(slot_id: str, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    row = (await db.execute(select(PublishSlot).where(PublishSlot.id == slot_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="ساعت پیدا نشد")
    await db.delete(row)
    return {"ok": True}


@router.post("/collect")
async def collect_now(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    return await collect_sources(db, force=True)


async def _draft(db: AsyncSession, draft_id: str) -> DraftPost:
    row = (await db.execute(select(DraftPost).where(DraftPost.id == draft_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="پیش‌نویس پیدا نشد")
    return row


@router.patch("/drafts/{draft_id}")
async def update_draft(draft_id: str, payload: DraftIn, request: Request, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    row = await _draft(db, draft_id)
    if payload.body is not None:
        if len(payload.body.strip()) < 8:
            raise HTTPException(status_code=400, detail="متن پیش‌نویس خالی است")
        remember_version(row, payload.body.strip(), "edit")
        await remember_lesson(
            db,
            kind="edit",
            category=row.category or "",
            note="اپراتور متن را اصلاح کرد؛ خبر واقعی را رد نکن و فرمول تکراری ننویس",
        )
    if payload.category:
        row.category = payload.category
    if payload.hashtags is not None:
        row.hashtags = payload.hashtags.strip()
    if payload.scheduled_at:
        try:
            when = datetime.fromisoformat(payload.scheduled_at)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="زمان معتبر نیست") from exc
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        row.scheduled_at = when.astimezone(timezone.utc)
        if row.status in {"preview", "failed", "skipped"}:
            row.status = "scheduled"
    await write_audit(db, admin=admin, action="edit", resource="draft", resource_id=row.id, ip_address=request.client.host if request.client else None)
    return dump_draft(row)


@router.get("/drafts/{draft_id}/photo")
async def draft_photo(draft_id: str, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    row = await _draft(db, draft_id)
    path = _draft_photo(row)
    if path is None:
        raise HTTPException(status_code=404, detail="این پیش‌نویس عکس ندارد")
    data = path.read_bytes()
    from backend.app.content.intake import image_mime

    return Response(content=data, media_type=image_mime(data), headers={"Cache-Control": "private, max-age=600"})


@router.get("/drafts/{draft_id}/preview")
async def preview_draft(draft_id: str, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    row = await _draft(db, draft_id)
    if len((row.body or "").strip()) < 8:
        raise HTTPException(status_code=400, detail="متن پیش‌نویس برای پیش‌نمایش کافی نیست")
    from backend.app.content.intake import photo_of

    maps = await load_emoji_maps(db)
    photo = photo_of(row.analysis_json)
    payload = prepare_publish_payload(row.body, row.category, row.emoji_signature, maps, is_caption=photo is not None)
    return {"text": payload["text"], "html_text": payload["html_text"], "emoji_ids": payload["emoji_ids"], "has_photo": photo is not None}


@router.post("/drafts/{draft_id}/test-send")
async def test_send_draft(draft_id: str, request: Request, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_publisher(admin)
    row = await _draft(db, draft_id)
    runtime = await load_runtime(db)
    chat_id = runtime.notify_id or admin.telegram_id
    if not chat_id:
        raise HTTPException(status_code=400, detail="اول چت اعلان یا آیدی تلگرام ادمین را در تنظیمات بگذار")
    from backend.app.content.intake import photo_of

    maps = await load_emoji_maps(db)
    photo = photo_of(row.analysis_json)
    payload = prepare_publish_payload(row.body, row.category, row.emoji_signature, maps, is_caption=photo is not None)
    note_id, note_error = await publish_rendered(int(chat_id), "پیش‌نمایش آزمایشی. این پیام در کانال عمومی نرفت.")
    if note_error:
        raise HTTPException(status_code=400, detail=note_error)
    message_id, error = await publish_rendered(int(chat_id), payload["text"], payload["html_text"], payload["entities"], photo)
    if error:
        raise HTTPException(status_code=400, detail=error)
    await write_audit(db, admin=admin, action="test_send", resource="draft", resource_id=row.id, ip_address=request.client.host if request.client else None)
    return {"ok": True, "message_id": message_id}


@router.post("/drafts/{draft_id}/publish")
async def publish_draft(draft_id: str, request: Request, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_publisher(admin)
    row = await _draft(db, draft_id)
    config = await get_config(db)
    chat_id = row.target_chat_id or config.target_chat_id
    if not chat_id:
        raise HTTPException(status_code=400, detail="اول کانال مقصد را انتخاب کن")
    if not await claim_for_publish(db, row.id):
        raise HTTPException(status_code=409, detail="این پیش‌نویس در حال ارسال است یا وضعیتش اجازه انتشار نمی‌دهد")
    await db.commit()
    row.status = "sending"
    message_id, error = await deliver_draft(db, row, int(chat_id))
    if error:
        row.status = "failed"
        row.error = error
        await write_audit(db, admin=admin, action="publish_failed", resource="draft", resource_id=row.id, new_value=error, ip_address=request.client.host if request.client else None)
        await db.commit()
        raise HTTPException(status_code=400, detail=error)
    row.status = "published"
    row.published_at = datetime.now(timezone.utc)
    row.message_id = message_id
    row.target_chat_id = int(chat_id)
    row.error = None
    await write_audit(db, admin=admin, action="publish", resource="draft", resource_id=row.id, new_value={"message_id": message_id}, ip_address=request.client.host if request.client else None)
    return dump_draft(row)


@router.post("/drafts/{draft_id}/unsend")
async def unsend_draft(draft_id: str, request: Request, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_publisher(admin)
    row = await _draft(db, draft_id)
    if not row.message_id or not row.target_chat_id:
        raise HTTPException(status_code=400, detail="این پیش‌نویس هنوز در کانال پیام ندارد")
    error = await delete_published(int(row.target_chat_id), int(row.message_id))
    if error:
        raise HTTPException(status_code=400, detail=error)
    removed = int(row.message_id)
    row.status = "recalled"
    row.message_id = None
    row.error = None
    row.published_at = None
    await write_audit(db, admin=admin, action="unsend", resource="draft", resource_id=row.id, new_value={"message_id": removed}, ip_address=request.client.host if request.client else None)
    return dump_draft(row)


@router.post("/drafts/{draft_id}/approve")
async def approve_draft(draft_id: str, request: Request, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_publisher(admin)
    row = await _draft(db, draft_id)
    if row.status not in {"preview", "failed", "scheduled", "recalled", "rejected"}:
        raise HTTPException(status_code=400, detail="فقط پیش‌نویس باز، پس‌گرفته یا بایگانی‌شده تأیید می‌شود")
    if len((row.body or "").strip()) < 8:
        raise HTTPException(status_code=400, detail="اول متن پیش‌نویس را کامل کن")
    slots = (await db.execute(select(PublishSlot).where(PublishSlot.enabled == True))).scalars().all()  # noqa: E712
    when = next_slot_time(list(slots), category=row.category)
    if when is None:
        raise HTTPException(status_code=400, detail="اول یک ساعت انتشار ثبت کن")
    row.status = "scheduled"
    row.scheduled_at = when.astimezone(timezone.utc)
    row.error = None
    await remember_lesson(
        db,
        kind="approve",
        category=row.category or "",
        note=f"دسته {row.category or 'news'} تأیید شد؛ خبر واقعی را رد نکن",
    )
    await write_audit(db, admin=admin, action="approve", resource="draft", resource_id=row.id, ip_address=request.client.host if request.client else None)
    return dump_draft(row)


@router.post("/drafts/{draft_id}/regenerate")
async def regenerate_draft(draft_id: str, request: Request, mode: str = "fresh", apply: bool = False, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    row = await _draft(db, draft_id)
    source = row.source_content or ""
    if len(source) < 40:
        raise HTTPException(status_code=400, detail="متن منبع برای بازنویسی ذخیره نشده")
    if mode not in {"fresh", "shorter", "rewrite"}:
        raise HTTPException(status_code=400, detail="حالت بازنویسی معتبر نیست")
    from backend.app.services.finetune import angle_label, classify_style, load_card

    runtime = await load_runtime(db)
    style = classify_style(source)
    prompt = await compose_prompt(db, f"regenerator_{mode}")
    config = await get_config(db)
    trace: dict = {}
    body, category, reason = await draft_from_source(
        source,
        row.source_label or "",
        runtime,
        mode=mode,
        template_hint=angle_label(style),
        system_prompt=prompt,
        style=style,
        style_card=await load_card(db),
        lessons=getattr(config, "lessons_json", None),
        trace=trace,
    )
    if not body:
        raise HTTPException(status_code=400, detail=human_reason(reason))
    if trace.get("repaired"):
        await remember_lesson(db, kind="repair", category=category, note=f"خبر دسته {category} را SKIP نکن؛ قابل بازنویسی است")
    diff = line_diff(row.body, body)
    if not apply:
        return {"applied": False, "proposed": body, "diff": diff}
    remember_version(row, body, mode)
    row.category = row.category or category
    row.status = "preview"
    await write_audit(db, admin=admin, action="regenerate", resource="draft", resource_id=row.id, new_value={"mode": mode}, ip_address=request.client.host if request.client else None)
    return dump_draft(row)


@router.post("/drafts/{draft_id}/restore")
async def restore_draft(draft_id: str, request: Request, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    row = await _draft(db, draft_id)
    row.status = "preview"
    row.error = None
    await write_audit(db, admin=admin, action="restore", resource="draft", resource_id=row.id, ip_address=request.client.host if request.client else None)
    return dump_draft(row)


@router.post("/drafts/{draft_id}/restore-version")
async def restore_version(draft_id: str, version: int, request: Request, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    row = await _draft(db, draft_id)
    match = next((item for item in _versions(row.versions_json) if int(item.get("version") or 0) == version), None)
    if not match or not match.get("body"):
        raise HTTPException(status_code=404, detail="این نسخه ذخیره نشده")
    remember_version(row, str(match["body"]), f"restore:{version}")
    row.status = "preview"
    await write_audit(db, admin=admin, action="restore_version", resource="draft", resource_id=row.id, new_value={"version": version}, ip_address=request.client.host if request.client else None)
    return dump_draft(row)


def _dump_hashtag(row: HashtagRule) -> dict:
    return {
        "id": row.id,
        "tag": row.tag,
        "category": row.category,
        "enabled": row.enabled,
        "forbidden": row.forbidden,
        "priority": row.priority,
    }


def _dump_prompt(row: PromptVersion) -> dict:
    name = row.name or ""
    return {
        "id": row.id,
        "name": name,
        "version": row.version,
        "body": row.body,
        "kind": "extra" if name.startswith("extra:") else "stage",
        "label": name.removeprefix("extra:"),
    }


def _clean_category(value: str | None) -> str:
    text = (value or "general").strip()[:64]
    if not re.fullmatch(r"[a-z_]{2,32}", text):
        raise HTTPException(status_code=400, detail="دسته هشتگ معتبر نیست")
    return text


@router.get("/hashtags")
async def list_hashtags(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    await ensure_content_defaults(db)
    rows = (await db.execute(select(HashtagRule).order_by(HashtagRule.priority.desc(), HashtagRule.tag))).scalars().all()
    return [_dump_hashtag(row) for row in rows]


@router.post("/hashtags")
async def create_hashtag(payload: HashtagCreate, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    tag = normalize_hashtag(payload.tag)
    if not tag:
        raise HTTPException(status_code=400, detail="هشتگ باید ۲ تا ۳۲ حرف باشد، بدون فاصله و بدون عددِ تنها")
    row = HashtagRule(
        tag=tag,
        category=_clean_category(payload.category),
        priority=payload.priority,
        enabled=payload.enabled,
        forbidden=False,
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(status_code=400, detail="این هشتگ قبلاً هست")
    return _dump_hashtag(row)


@router.patch("/hashtags/{tag_id}")
async def update_hashtag(tag_id: str, payload: HashtagIn, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    row = (await db.execute(select(HashtagRule).where(HashtagRule.id == tag_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="هشتگ پیدا نشد")
    data = payload.model_dump(exclude_unset=True)
    if "category" in data:
        data["category"] = _clean_category(data["category"])
    for key, value in data.items():
        setattr(row, key, value)
    return _dump_hashtag(row)


@router.delete("/hashtags/{tag_id}")
async def delete_hashtag(tag_id: str, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    row = (await db.execute(select(HashtagRule).where(HashtagRule.id == tag_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="هشتگ پیدا نشد")
    await db.delete(row)
    return {"ok": True}


@router.post("/prompts")
async def save_prompt(payload: PromptIn, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    await ensure_content_defaults(db)
    kind = (payload.kind or "stage").strip()
    body = payload.body.strip()
    if kind == "extra":
        label = normalize_hashtag(payload.name.replace("extra:", "", 1))
        if not label:
            raise HTTPException(status_code=400, detail="نام دستور اضافه معتبر نیست")
        name = f"extra:{label}"
    elif kind == "stage" and payload.name in PROMPTS:
        name = payload.name
    else:
        raise HTTPException(status_code=400, detail="مرحله ناشناخته است. دستور تازه را به‌صورت افزوده بساز")
    current = (
        await db.execute(select(PromptVersion).where(PromptVersion.name == name, PromptVersion.active == True))  # noqa: E712
    ).scalars().all()
    version = 1
    for row in current:
        version = max(version, int(row.version or 1) + 1)
        row.active = False
    if not current:
        previous = (await db.execute(select(func.max(PromptVersion.version)).where(PromptVersion.name == name))).scalar()
        version = int(previous or 0) + 1
    created = PromptVersion(name=name, version=version, body=body, active=True)
    db.add(created)
    await db.flush()
    return _dump_prompt(created)


@router.post("/prompts/{name}/restore")
async def restore_prompt(name: str, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    if name not in PROMPTS:
        raise HTTPException(status_code=400, detail="فقط مرحله‌های اصلی متن پایه دارند")
    current = (
        await db.execute(select(PromptVersion).where(PromptVersion.name == name))
    ).scalars().all()
    version = max((int(row.version or 1) for row in current), default=0) + 1
    for row in current:
        if row.active:
            row.active = False
    created = PromptVersion(name=name, version=version, body=PROMPTS[name], active=True)
    db.add(created)
    await db.flush()
    return _dump_prompt(created)


@router.delete("/prompts/{prompt_id}")
async def delete_prompt(prompt_id: str, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    row = (await db.execute(select(PromptVersion).where(PromptVersion.id == prompt_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="پرامپت پیدا نشد")
    if not (row.name or "").startswith("extra:"):
        raise HTTPException(status_code=400, detail="مرحله اصلی حذف نمی‌شود؛ متن پایه را برگردان")
    siblings = (await db.execute(select(PromptVersion).where(PromptVersion.name == row.name))).scalars().all()
    for item in siblings:
        await db.delete(item)
    return {"ok": True}


@router.post("/drafts/{draft_id}/reject")
async def reject_draft(draft_id: str, request: Request, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    row = await _draft(db, draft_id)
    if row.status in {"published", "sending"}:
        raise HTTPException(status_code=400, detail="پست منتشرشده یا در حال ارسال را رد نکن. اول از کانال پس بگیر")
    row.status = "rejected"
    await remember_lesson(
        db,
        kind="reject",
        category=row.category or "",
        note=f"پیش‌نویس دسته {row.category or 'عمومی'} رد شد؛ لحن را عوض کن و تبلیغ را منتشر نکن",
    )
    await write_audit(db, admin=admin, action="reject", resource="draft", resource_id=row.id, ip_address=request.client.host if request.client else None)
    return dump_draft(row)


@router.post("/publish-due")
async def publish_due_now(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_publisher(admin)
    return await publish_due(db)
