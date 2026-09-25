import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.base import get_db
from backend.app.models.emoji import EmojiMapping
from backend.app.schemas.emoji import EmojiCreate, EmojiUpdate
from backend.app.security.deps import assert_editor, get_current_admin
from backend.app.services.audit import write_audit
from backend.app.telegram.bot import get_bot
from backend.app.telegram.emoji_pack import fetch_sticker_set, import_pack_names, parse_pack_names

router = APIRouter(prefix="/api/emojis", tags=["emojis"])


def dump_emoji(row: EmojiMapping) -> dict:
    return {
        "id": row.id,
        "unicode_emoji": row.unicode_emoji,
        "custom_emoji_id": row.custom_emoji_id,
        "enabled": row.enabled,
        "category": row.category,
        "contexts": row.contexts,
        "priority": row.priority,
        "usage_count": row.usage_count,
        "label": row.label,
        "source": row.source,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/export")
async def export_emojis(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    rows = (await db.execute(select(EmojiMapping))).scalars().all()
    return [dump_emoji(row) for row in rows]


@router.post("/import")
async def import_emojis(payload: list[dict], db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    imported = 0
    for item in payload:
        emoji = item.get("unicode_emoji")
        custom_id = str(item.get("custom_emoji_id") or "")
        if not emoji or not custom_id.isdigit():
            continue
        existing = (
            await db.execute(
                select(EmojiMapping).where(EmojiMapping.unicode_emoji == emoji, EmojiMapping.custom_emoji_id == custom_id)
            )
        ).scalar_one_or_none()
        contexts = item.get("contexts")
        if isinstance(contexts, list):
            contexts = json.dumps(contexts, ensure_ascii=False)
        if existing:
            existing.enabled = item.get("enabled", existing.enabled)
            existing.category = item.get("category", existing.category)
            existing.priority = item.get("priority", existing.priority)
            existing.label = item.get("label", existing.label)
            if contexts is not None:
                existing.contexts = contexts
            continue
        db.add(EmojiMapping(
            unicode_emoji=emoji,
            custom_emoji_id=custom_id,
            enabled=item.get("enabled", True),
            category=item.get("category"),
            contexts=contexts,
            priority=item.get("priority", 50),
            label=item.get("label"),
            source="import",
        ))
        imported += 1
    await db.flush()
    return {"imported": imported}


@router.post("/import-pack")
async def import_pack(payload: dict, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    raw = str(payload.get("url") or payload.get("link") or payload.get("name") or "").strip()
    names = parse_pack_names(raw, allow_bare=True)
    if not names:
        raise HTTPException(status_code=400, detail="لینک پک معتبر نیست. نمونه: https://t.me/addemoji/Name")
    if get_bot() is None:
        raise HTTPException(status_code=400, detail="توکن ربات تنظیم نشده")
    result = await import_pack_names(db, names, fetch_sticker_set)
    await write_audit(db, admin=admin, action="import_pack", resource="emoji", resource_id=names[0], ip_address=None)
    return result


@router.post("/validate")
async def validate_emojis(payload: dict, admin=Depends(get_current_admin)):
    ids = [str(item).strip() for item in (payload.get("custom_emoji_ids") or payload.get("ids") or [])]
    ids = [item for item in ids if item.isdigit()][:50]
    if not ids:
        return {"found": [], "valid": [], "invalid": []}
    bot = get_bot()
    if not bot:
        return {"found": [], "valid": [], "invalid": ids, "note": "توکن ربات تنظیم نشده"}
    try:
        stickers = await bot.get_custom_emoji_stickers(custom_emoji_ids=ids)
        found = {str(getattr(sticker, "custom_emoji_id", "")) for sticker in (stickers or [])}
        found.discard("")
        return {"found": sorted(found), "valid": sorted(found), "invalid": [item for item in ids if item not in found]}
    except Exception as exc:
        return {"found": [], "valid": [], "invalid": ids, "error": str(exc)}


@router.post("/cleanup-fake")
async def cleanup_fake(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    rows = (await db.execute(select(EmojiMapping).where(EmojiMapping.custom_emoji_id.like("53683241%")))).scalars().all()
    for row in rows:
        await db.delete(row)
    await db.flush()
    return {"removed": len(rows)}


@router.get("")
async def list_emojis(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    rows = (await db.execute(select(EmojiMapping).order_by(EmojiMapping.priority.desc(), EmojiMapping.usage_count.desc()))).scalars().all()
    return [dump_emoji(row) for row in rows]


@router.post("")
async def create_emoji(payload: EmojiCreate, request: Request, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    if not str(payload.custom_emoji_id).isdigit():
        raise HTTPException(status_code=400, detail="custom_emoji_id باید عدد باشد")
    row = EmojiMapping(
        unicode_emoji=payload.unicode_emoji,
        custom_emoji_id=payload.custom_emoji_id.strip(),
        enabled=payload.enabled,
        category=payload.category,
        contexts=json.dumps(payload.contexts, ensure_ascii=False) if payload.contexts else None,
        priority=payload.priority,
        source="panel",
    )
    db.add(row)
    await db.flush()
    await write_audit(db, admin=admin, action="create", resource="emoji", resource_id=row.id, ip_address=request.client.host if request.client else None)
    return dump_emoji(row)


@router.patch("/{emoji_id}")
async def update_emoji(emoji_id: str, payload: EmojiUpdate, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    row = (await db.execute(select(EmojiMapping).where(EmojiMapping.id == emoji_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="ایموجی پیدا نشد")
    data = payload.model_dump(exclude_unset=True)
    if "contexts" in data and data["contexts"] is not None:
        data["contexts"] = json.dumps(data["contexts"], ensure_ascii=False)
    for key, value in data.items():
        setattr(row, key, value)
    return dump_emoji(row)


@router.delete("/{emoji_id}")
async def delete_emoji(emoji_id: str, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    row = (await db.execute(select(EmojiMapping).where(EmojiMapping.id == emoji_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="ایموجی پیدا نشد")
    await db.delete(row)
    return {"ok": True}
