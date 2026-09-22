from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.app.db.base import get_db
from backend.app.models.message_log import MessageLog
from backend.app.models.channel import Channel
from backend.app.models.emoji import EmojiMapping
from backend.app.security.deps import get_current_admin
from datetime import datetime, timedelta, timezone

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

@router.get("")
async def dashboard(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    # counts
    total = (await db.execute(select(func.count()).select_from(MessageLog))).scalar() or 0
    edited = (await db.execute(select(func.count()).select_from(MessageLog).where(MessageLog.status=="edited"))).scalar() or 0
    skipped = (await db.execute(select(func.count()).select_from(MessageLog).where(MessageLog.status=="skipped"))).scalar() or 0
    failed = (await db.execute(select(func.count()).select_from(MessageLog).where(MessageLog.status=="failed"))).scalar() or 0
    dry = (await db.execute(select(func.count()).select_from(MessageLog).where(MessageLog.status=="dry_run"))).scalar() or 0

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=7)
    today_count = (await db.execute(select(func.count()).select_from(MessageLog).where(MessageLog.created_at >= today_start))).scalar() or 0
    week_count = (await db.execute(select(func.count()).select_from(MessageLog).where(MessageLog.created_at >= week_start))).scalar() or 0

    avg_time = (await db.execute(select(func.avg(MessageLog.processing_time_ms)))).scalar()
    channels_count = (await db.execute(select(func.count()).select_from(Channel))).scalar() or 0
    emojis_count = (await db.execute(select(func.count()).select_from(EmojiMapping).where(EmojiMapping.enabled==True))).scalar() or 0

    # last 7 days histogram
    per_day=[]
    for i in range(6,-1,-1):
        d = today_start - timedelta(days=i)
        nxt = d + timedelta(days=1)
        c = (await db.execute(select(func.count()).select_from(MessageLog).where(MessageLog.created_at >= d, MessageLog.created_at < nxt))).scalar() or 0
        per_day.append({"date": d.strftime("%Y-%m-%d"), "count": c})

    # recent messages
    res = await db.execute(select(MessageLog).order_by(MessageLog.created_at.desc()).limit(8))
    recent = res.scalars().all()
    recent_out = [{"id":m.id,"chat_id":m.chat_id,"message_id":m.message_id,"category":m.category,"status":m.status,"created_at": m.created_at.isoformat() if m.created_at else None} for m in recent]

    return {
        "total": total, "edited": edited, "skipped": skipped, "failed": failed, "dry_run": dry,
        "today": today_count, "week": week_count,
        "avg_ms": round(avg_time,1) if avg_time else 0,
        "channels": channels_count, "emojis": emojis_count,
        "per_day": per_day,
        "recent": recent_out,
    }
