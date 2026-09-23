import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.base import get_db
from backend.app.formatting.styles import BUILTIN_STYLES
from backend.app.models.style import StylePreset
from backend.app.security.deps import get_current_admin

router = APIRouter(prefix="/api/styles", tags=["styles"])


def _builtin():
    return [{
        "id": f"builtin_{key}",
        "name": style.name,
        "slug": style.slug,
        "description": None,
        "config": json.dumps({
            "footer": style.footer_template,
            "divider": style.divider,
            "header": style.header_template,
            "add_footer": style.add_footer,
        }, ensure_ascii=False),
        "is_builtin": True,
    } for key, style in BUILTIN_STYLES.items()]


@router.get("")
async def list_styles(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    custom = (await db.execute(select(StylePreset).order_by(StylePreset.created_at.desc()))).scalars().all()
    custom_out = [{
        "id": row.id,
        "name": row.name,
        "slug": row.slug,
        "description": row.description,
        "config": row.config,
        "is_builtin": False,
    } for row in custom]
    return _builtin() + custom_out


@router.post("")
async def create_style(payload: dict, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    slug = (payload.get("slug") or "").strip()
    name = (payload.get("name") or "").strip()
    if not slug or not name:
        raise HTTPException(status_code=400, detail="نام و شناسه لازم است")
    if slug in BUILTIN_STYLES:
        raise HTTPException(status_code=400, detail="این شناسه برای استایل داخلی رزرو شده")
    exists = (await db.execute(select(StylePreset).where(StylePreset.slug == slug))).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="این شناسه قبلاً استفاده شده")
    config = payload.get("config") or {}
    row = StylePreset(
        name=name,
        slug=slug,
        description=payload.get("description"),
        config=json.dumps(config, ensure_ascii=False),
    )
    db.add(row)
    await db.flush()
    return {"id": row.id, "slug": row.slug}


@router.patch("/{style_id}")
async def update_style(style_id: str, payload: dict, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    if style_id.startswith("builtin_"):
        raise HTTPException(status_code=400, detail="استایل داخلی را کپی کن و نسخه سفارشی را ویرایش کن")
    row = (await db.execute(select(StylePreset).where(StylePreset.id == style_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="استایل پیدا نشد")
    for key in ("name", "slug", "description"):
        if key in payload and payload[key]:
            setattr(row, key, payload[key])
    if "config" in payload:
        row.config = json.dumps(payload["config"], ensure_ascii=False)
    return {"ok": True}


@router.delete("/{style_id}")
async def delete_style(style_id: str, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    if style_id.startswith("builtin_"):
        raise HTTPException(status_code=400, detail="استایل داخلی حذف نمی‌شود")
    row = (await db.execute(select(StylePreset).where(StylePreset.id == style_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="استایل پیدا نشد")
    await db.delete(row)
    return {"ok": True}
