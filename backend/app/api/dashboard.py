from datetime import datetime, timedelta, timezone
import json

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.runtime import load_runtime
from backend.app.db.base import get_db
from backend.app.models.channel import Channel
from backend.app.models.emoji import EmojiMapping
from backend.app.models.message_log import MessageLog
from backend.app.security.deps import get_current_admin

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def template_usage(rules_list: list[str | None]) -> list[dict]:
    counts: dict[str, int] = {}
    for raw in rules_list:
        try:
            parsed = json.loads(raw or "[]")
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, list):
            continue
        for item in parsed:
            text = str(item)
            if text.startswith("template_id:"):
                name = text.split(":", 1)[1]
                counts[name] = counts.get(name, 0) + 1
                break
    return [{"name": name, "count": count} for name, count in sorted(counts.items(), key=lambda item: -item[1])]


@router.get("")
async def dashboard(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    runtime = await load_runtime(db)

    async def count(*where):
        stmt = select(func.count()).select_from(MessageLog)
        if where:
            stmt = stmt.where(*where)
        return (await db.execute(stmt)).scalar() or 0

    total = await count()
    edited = await count(MessageLog.status == "edited")
    skipped = await count(MessageLog.status == "skipped")
    failed = await count(MessageLog.status == "failed")
    dry = await count(MessageLog.status == "dry_run")
    ai_used = await count(MessageLog.ai_used == True)  # noqa: E712

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=7)
    today_count = await count(MessageLog.created_at >= today_start)
    week_count = await count(MessageLog.created_at >= week_start)
    avg_time = (await db.execute(select(func.avg(MessageLog.processing_time_ms)))).scalar()
    channels_count = (await db.execute(select(func.count()).select_from(Channel))).scalar() or 0
    emojis_count = (await db.execute(select(func.count()).select_from(EmojiMapping).where(EmojiMapping.enabled == True))).scalar() or 0  # noqa: E712

    per_day = []
    for i in range(6, -1, -1):
        day = today_start - timedelta(days=i)
        nxt = day + timedelta(days=1)
        per_day.append({
            "date": day.strftime("%m/%d"),
            "count": await count(MessageLog.created_at >= day, MessageLog.created_at < nxt),
            "edited": await count(MessageLog.status == "edited", MessageLog.created_at >= day, MessageLog.created_at < nxt),
        })

    categories = (
        await db.execute(
            select(MessageLog.category, func.count())
            .group_by(MessageLog.category)
            .order_by(func.count().desc())
            .limit(6)
        )
    ).all()
    recent = (await db.execute(select(MessageLog).order_by(MessageLog.created_at.desc()).limit(8))).scalars().all()
    rule_rows = (
        await db.execute(select(MessageLog.applied_rules).order_by(MessageLog.created_at.desc()).limit(40))
    ).scalars().all()
    success = round((edited / total) * 100, 1) if total else None
    failures = (
        await db.execute(
            select(MessageLog).where(MessageLog.status == "failed").order_by(MessageLog.created_at.desc()).limit(5)
        )
    ).scalars().all()
    return {
        "total": total,
        "edited": edited,
        "skipped": skipped,
        "failed": failed,
        "dry_run": dry,
        "ai_used": ai_used,
        "today": today_count,
        "week": week_count,
        "success_rate": success,
        "has_data": total > 0,
        "avg_ms": round(avg_time, 1) if avg_time else 0,
        "channels": channels_count,
        "emojis": emojis_count,
        "per_day": per_day,
        "categories": [{"name": name or "general", "count": count} for name, count in categories],
        "runtime": {
            "dry_run": runtime.dry_run,
            "kill_switch": runtime.kill_switch,
            "ai_ready": runtime.ai_ready,
            "premium_mode": runtime.premium_mode,
        },
        "recent": [{
            "id": row.id,
            "chat_id": row.chat_id,
            "message_id": row.message_id,
            "category": row.category,
            "status": row.status,
            "ai_used": row.ai_used,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        } for row in recent],
        "templates": template_usage(list(rule_rows)),
        "failures": [{
            "id": row.id,
            "chat_id": row.chat_id,
            "message_id": row.message_id,
            "error": row.error,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        } for row in failures],
    }
