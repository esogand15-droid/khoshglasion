from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.base import get_db
from backend.app.models.automation import DraftPost, NewsSource, PublishSlot
from backend.app.security.deps import get_current_admin
from backend.app.services.audit import write_audit
from backend.app.services.automation_runner import collect_sources, publish_due
from backend.app.services.autopost import get_config, next_slot_time, normalize_source
from backend.app.telegram.publisher import publish_text

router = APIRouter(prefix="/api/automation", tags=["automation"])


def dump_source(row: NewsSource) -> dict:
    return {
        "id": row.id,
        "username": row.username,
        "title": row.title,
        "enabled": row.enabled,
        "category_hint": row.category_hint,
        "last_message_id": row.last_message_id,
        "last_error": row.last_error,
    }


def dump_slot(row: PublishSlot) -> dict:
    return {"id": row.id, "hour": row.hour, "minute": row.minute, "category": row.category, "enabled": row.enabled}


def dump_draft(row: DraftPost) -> dict:
    return {
        "id": row.id,
        "status": row.status,
        "category": row.category,
        "body": row.body,
        "source_label": row.source_label,
        "scheduled_at": row.scheduled_at.isoformat() if row.scheduled_at else None,
        "published_at": row.published_at.isoformat() if row.published_at else None,
        "target_chat_id": row.target_chat_id,
        "message_id": row.message_id,
        "error": row.error,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


class SourceIn(BaseModel):
    username: str
    category_hint: str | None = None


class SlotIn(BaseModel):
    hour: int = Field(ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    category: str | None = None


class ConfigIn(BaseModel):
    enabled: bool | None = None
    auto_publish: bool | None = None
    target_chat_id: int | None = None


class DraftIn(BaseModel):
    body: str | None = None
    scheduled_at: str | None = None
    category: str | None = None


@router.get("")
async def automation_state(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    config = await get_config(db)
    sources = (await db.execute(select(NewsSource).order_by(NewsSource.created_at))).scalars().all()
    slots = (await db.execute(select(PublishSlot).order_by(PublishSlot.hour, PublishSlot.minute))).scalars().all()
    drafts = (await db.execute(select(DraftPost).order_by(DraftPost.created_at.desc()).limit(40))).scalars().all()
    return {
        "enabled": config.enabled,
        "auto_publish": config.auto_publish,
        "target_chat_id": config.target_chat_id,
        "last_collect_at": config.last_collect_at.isoformat() if config.last_collect_at else None,
        "last_error": config.last_error,
        "next_slot": next_slot_time(list(slots)).isoformat() if next_slot_time(list(slots)) else None,
        "sources": [dump_source(row) for row in sources],
        "slots": [dump_slot(row) for row in slots],
        "drafts": [dump_draft(row) for row in drafts],
    }


@router.patch("")
async def update_config(payload: ConfigIn, request: Request, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    config = await get_config(db)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(config, key, value)
    await write_audit(db, admin=admin, action="update", resource="automation", new_value=data, ip_address=request.client.host if request.client else None)
    return {"ok": True, "enabled": config.enabled, "auto_publish": config.auto_publish, "target_chat_id": config.target_chat_id}


@router.post("/sources")
async def add_source(payload: SourceIn, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    username = normalize_source(payload.username)
    if not username:
        raise HTTPException(status_code=400, detail="فقط یوزرنیم عمومی یا آیدی عددی کانال. لینک دعوت خصوصی قبول نیست")
    existing = (await db.execute(select(NewsSource).where(NewsSource.username == username))).scalar_one_or_none()
    if existing:
        existing.enabled = True
        existing.category_hint = payload.category_hint or existing.category_hint
        return dump_source(existing)
    row = NewsSource(username=username, category_hint=payload.category_hint)
    db.add(row)
    await db.flush()
    return dump_source(row)


@router.delete("/sources/{source_id}")
async def delete_source(source_id: str, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    row = (await db.execute(select(NewsSource).where(NewsSource.id == source_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="منبع پیدا نشد")
    await db.delete(row)
    return {"ok": True}


@router.post("/slots")
async def add_slot(payload: SlotIn, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    row = PublishSlot(hour=payload.hour, minute=payload.minute, category=payload.category or None)
    db.add(row)
    await db.flush()
    return dump_slot(row)


@router.delete("/slots/{slot_id}")
async def delete_slot(slot_id: str, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    row = (await db.execute(select(PublishSlot).where(PublishSlot.id == slot_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="ساعت پیدا نشد")
    await db.delete(row)
    return {"ok": True}


@router.post("/collect")
async def collect_now(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    return await collect_sources(db, force=True)


@router.patch("/drafts/{draft_id}")
async def update_draft(draft_id: str, payload: DraftIn, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    row = (await db.execute(select(DraftPost).where(DraftPost.id == draft_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="پیش‌نویس پیدا نشد")
    if payload.body is not None:
        if len(payload.body.strip()) < 8:
            raise HTTPException(status_code=400, detail="متن پیش‌نویس خالی است")
        row.body = payload.body.strip()
    if payload.category:
        row.category = payload.category
    if payload.scheduled_at:
        try:
            when = datetime.fromisoformat(payload.scheduled_at)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="زمان معتبر نیست") from exc
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        row.scheduled_at = when.astimezone(timezone.utc)
        if row.status in {"preview", "failed"}:
            row.status = "scheduled"
    return dump_draft(row)


@router.post("/drafts/{draft_id}/publish")
async def publish_draft(draft_id: str, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    row = (await db.execute(select(DraftPost).where(DraftPost.id == draft_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="پیش‌نویس پیدا نشد")
    config = await get_config(db)
    chat_id = row.target_chat_id or config.target_chat_id
    if not chat_id:
        raise HTTPException(status_code=400, detail="اول کانال مقصد را انتخاب کن")
    message_id, error = await publish_text(int(chat_id), row.body)
    if error:
        row.status = "failed"
        row.error = error
        raise HTTPException(status_code=400, detail=error)
    row.status = "published"
    row.published_at = datetime.now(timezone.utc)
    row.message_id = message_id
    row.target_chat_id = int(chat_id)
    row.error = None
    return dump_draft(row)


@router.post("/drafts/{draft_id}/reject")
async def reject_draft(draft_id: str, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    row = (await db.execute(select(DraftPost).where(DraftPost.id == draft_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="پیش‌نویس پیدا نشد")
    row.status = "rejected"
    return dump_draft(row)


@router.post("/publish-due")
async def publish_due_now(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    return await publish_due(db)
