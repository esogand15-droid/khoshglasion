from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from backend.app.db.base import get_db
from backend.app.models.message_log import MessageLog
from backend.app.security.deps import get_current_admin

router = APIRouter(prefix="/api/messages", tags=["messages"])

@router.get("")
async def list_messages(limit: int = Query(50, le=200), offset: int = 0, status: str | None = None, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    q = select(MessageLog).order_by(desc(MessageLog.created_at)).limit(limit).offset(offset)
    if status:
        q = select(MessageLog).where(MessageLog.status==status).order_by(desc(MessageLog.created_at)).limit(limit).offset(offset)
    res = await db.execute(q)
    items = res.scalars().all()
    return [{"id":m.id,"chat_id":m.chat_id,"message_id":m.message_id,"original_text":(m.original_text[:200] if m.original_text else None),"formatted_text":(m.formatted_text[:200] if m.formatted_text else None),"category":m.category,"status":m.status,"error":m.error,"processing_time_ms":m.processing_time_ms,"has_media":m.has_media,"message_type":m.message_type,"created_at": m.created_at.isoformat() if m.created_at else None} for m in items]

@router.get("/{msg_id}")
async def get_message(msg_id: str, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    res = await db.execute(select(MessageLog).where(MessageLog.id==msg_id))
    m = res.scalar_one_or_none()
    if not m:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Not found")
    return {"id":m.id,"chat_id":m.chat_id,"message_id":m.message_id,"original_text":m.original_text,"formatted_text":m.formatted_text,"category":m.category,"status":m.status,"error":m.error,"applied_rules":m.applied_rules,"processing_time_ms":m.processing_time_ms,"has_media":m.has_media,"message_type":m.message_type,"created_at": m.created_at.isoformat() if m.created_at else None}
