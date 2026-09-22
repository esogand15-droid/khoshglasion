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
@router.post("/validate")
async def validate_emojis(payload: dict, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    """Validate custom_emoji_ids via Telegram Bot API getCustomEmojiStickers. Returns which are real."""
    ids: list[str] = payload.get("custom_emoji_ids", []) or payload.get("ids", [])
    if not ids:
        return {"found": [], "valid": [], "invalid": []}
    # limit
    ids = [str(x).strip() for x in ids[:20] if str(x).strip().isdigit()]
    if not ids:
        return {"found": [], "valid": [], "invalid": ids}
    try:
        from backend.app.telegram.bot import get_bot
        bot = get_bot()
        if not bot:
            return {"found": [], "valid": [], "invalid": ids, "note": "bot not configured"}
        stickers = await bot.get_custom_emoji_stickers(custom_emoji_ids=ids)
        found_ids = {str(s.custom_emoji_id) for s in stickers} if stickers else set()
        # Some versions return .custom_emoji_id as int
        found_ids = {str(x) for x in found_ids}
        invalid = [x for x in ids if x not in found_ids]
        return {"found": list(found_ids), "valid": list(found_ids), "invalid": invalid}
    except Exception as e:
        return {"found": [], "valid": [], "invalid": ids, "error": str(e)}

@router.post("/cleanup-fake")
async def cleanup_fake(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    """Remove sequential fake IDs (53683241...) that never work."""
    from sqlalchemy import delete as sa_delete
    res = await db.execute(select(EmojiMapping).where(EmojiMapping.custom_emoji_id.like("53683241%")))
    fakes = res.scalars().all()
    count = len(fakes)
    for f in fakes:
        await db.delete(f)
    await db.flush()
    return {"removed": count, "message": f"{count} fake mappings removed"}



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
