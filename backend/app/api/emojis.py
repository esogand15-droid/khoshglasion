from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.db.base import get_db
from backend.app.models.emoji import EmojiMapping
from backend.app.schemas.emoji import EmojiCreate, EmojiUpdate
from backend.app.security.deps import get_current_admin
import json

router = APIRouter(prefix="/api/emojis", tags=["emojis"])

@router.get("/export")
async def export_emojis(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    res = await db.execute(select(EmojiMapping))
    items = res.scalars().all()
    return [{"unicode_emoji":e.unicode_emoji,"custom_emoji_id":e.custom_emoji_id,"enabled":e.enabled,"category":e.category,"contexts":e.contexts,"priority":e.priority} for e in items]

@router.post("/import")
async def import_emojis(payload: list[dict], db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    for item in payload:
        rec = EmojiMapping(
            unicode_emoji=item["unicode_emoji"],
            custom_emoji_id=item["custom_emoji_id"],
            enabled=item.get("enabled", True),
            category=item.get("category"),
            contexts=json.dumps(item["contexts"], ensure_ascii=False) if isinstance(item.get("contexts"), list) else item.get("contexts"),
            priority=item.get("priority", 50),
        )
        db.add(rec)
    await db.flush()
    return {"imported": len(payload)}

@router.get("")
async def list_emojis(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    res = await db.execute(select(EmojiMapping).order_by(EmojiMapping.priority.desc()))
    items = res.scalars().all()
    out=[]
    for e in items:
        out.append({"id":e.id,"unicode_emoji":e.unicode_emoji,"custom_emoji_id":e.custom_emoji_id,"enabled":e.enabled,"category":e.category,"contexts":e.contexts,"priority":e.priority,"usage_count":e.usage_count,"created_at": e.created_at.isoformat() if e.created_at else None})
    return out

@router.post("")
async def create_emoji(payload: EmojiCreate, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    rec = EmojiMapping(
        unicode_emoji=payload.unicode_emoji,
        custom_emoji_id=payload.custom_emoji_id,
        enabled=payload.enabled,
        category=payload.category,
        contexts=json.dumps(payload.contexts, ensure_ascii=False) if payload.contexts else None,
        priority=payload.priority,
    )
    db.add(rec)
    await db.flush()
    return {"id": rec.id}

@router.patch("/{emoji_id}")
async def update_emoji(emoji_id: str, payload: EmojiUpdate, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    res = await db.execute(select(EmojiMapping).where(EmojiMapping.id==emoji_id))
    e = res.scalar_one_or_none()
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    data = payload.model_dump(exclude_unset=True)
    if "contexts" in data and data["contexts"] is not None:
        data["contexts"] = json.dumps(data["contexts"], ensure_ascii=False)
    for k,v in data.items():
        setattr(e,k,v)
    await db.flush()
    return {"ok": True}

@router.delete("/{emoji_id}")
async def delete_emoji(emoji_id: str, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    res = await db.execute(select(EmojiMapping).where(EmojiMapping.id==emoji_id))
    e = res.scalar_one_or_none()
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(e)
    await db.flush()
    return {"ok": True}
