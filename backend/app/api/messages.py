import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.base import get_db
from backend.app.formatting.diff import line_diff
from backend.app.models.message_log import MessageLog
from backend.app.security.deps import assert_editor, get_current_admin
from backend.app.telegram.pipeline import reprocess_log

router = APIRouter(prefix="/api/messages", tags=["messages"])


def _meta(row: MessageLog) -> dict:
    try:
        parsed = json.loads(row.meta or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def dump_message(row: MessageLog, full: bool = False) -> dict:
    original = row.original_text
    formatted = row.formatted_text
    if not full:
        original = original[:240] if original else None
        formatted = formatted[:240] if formatted else None
    return {
        "id": row.id,
        "chat_id": row.chat_id,
        "message_id": row.message_id,
        "original_text": original,
        "formatted_text": formatted,
        "html_text": row.html_text if full else None,
        "category": row.category,
        "status": row.status,
        "error": row.error,
        "applied_rules": row.applied_rules,
        "processing_time_ms": row.processing_time_ms,
        "has_media": row.has_media,
        "message_type": row.message_type,
        "ai_used": row.ai_used,
        "attempt_count": row.attempt_count,
        "edit_method": row.edit_method,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "decision": _meta(row).get("decision") if full else None,
        "selection": _meta(row).get("selection") if full else None,
        "diff": line_diff(row.original_text, row.formatted_text) if full else None,
    }


@router.get("")
async def list_messages(
    limit: int = Query(40, le=200),
    offset: int = 0,
    status: str | None = None,
    category: str | None = None,
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    filters = []
    if status:
        filters.append(MessageLog.status == status)
    if category:
        filters.append(MessageLog.category == category)
    if q:
        like = f"%{q.strip()}%"
        filters.append(or_(
            MessageLog.original_text.ilike(like),
            MessageLog.formatted_text.ilike(like),
            MessageLog.error.ilike(like),
            MessageLog.category.ilike(like),
        ))
    total = (await db.execute(select(func.count()).select_from(MessageLog).where(*filters))).scalar() or 0
    rows = (
        await db.execute(
            select(MessageLog).where(*filters).order_by(desc(MessageLog.created_at)).limit(limit).offset(offset)
        )
    ).scalars().all()
    return {"items": [dump_message(row) for row in rows], "total": total}


@router.get("/{msg_id}")
async def get_message(msg_id: str, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    row = (await db.execute(select(MessageLog).where(MessageLog.id == msg_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="پیام پیدا نشد")
    return dump_message(row, full=True)


@router.post("/{msg_id}/retry")
async def retry_message(msg_id: str, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    row = (await db.execute(select(MessageLog).where(MessageLog.id == msg_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="پیام پیدا نشد")
    result = await reprocess_log(db, row)
    await db.flush()
    refreshed = (await db.execute(select(MessageLog).where(MessageLog.id == row.id))).scalar_one_or_none()
    return {"result": result, "message": dump_message(refreshed or row, full=True)}


@router.post("/{msg_id}/skip")
async def skip_message(msg_id: str, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    row = (await db.execute(select(MessageLog).where(MessageLog.id == msg_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="پیام پیدا نشد")
    row.status = "skipped"
    row.error = "skipped_by_admin"
    await db.flush()
    return dump_message(row, full=True)


@router.delete("/{msg_id}")
async def delete_message(msg_id: str, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    row = (await db.execute(select(MessageLog).where(MessageLog.id == msg_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="پیام پیدا نشد")
    if row.status == "edited":
        raise HTTPException(status_code=400, detail="ادیت موفق حذف نمی‌شود")
    await db.delete(row)
    await db.flush()
    return {"ok": True}
