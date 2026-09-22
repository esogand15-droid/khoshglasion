from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.db.base import get_db
from backend.app.models.style import StylePreset
from backend.app.security.deps import get_current_admin
from backend.app.formatting.styles import BUILTIN_STYLES
import json

router = APIRouter(prefix="/api/styles", tags=["styles"])

@router.get("")
async def list_styles(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    # merge builtin + db
    res = await db.execute(select(StylePreset))
    custom = res.scalars().all()
    builtin = [{"id": f"builtin_{k}", "name": v.name, "slug": v.slug, "description": None, "config": json.dumps({"footer": v.footer_template, "divider": v.divider}), "is_builtin": True} for k,v in BUILTIN_STYLES.items()]
    custom_out = [{"id": c.id, "name": c.name, "slug": c.slug, "description": c.description, "config": c.config, "is_builtin": False} for c in custom]
    return builtin + custom_out

@router.post("")
async def create_style(payload: dict, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    s = StylePreset(name=payload["name"], slug=payload["slug"], description=payload.get("description"), config=json.dumps(payload.get("config", {}), ensure_ascii=False))
    db.add(s)
    await db.flush()
    return {"id": s.id}

@router.patch("/{style_id}")
async def update_style(style_id: str, payload: dict, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    if style_id.startswith("builtin_"):
        raise HTTPException(status_code=400, detail="Cannot edit builtin style")
    res = await db.execute(select(StylePreset).where(StylePreset.id==style_id))
    s = res.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Not found")
    for k in ["name","slug","description"]:
        if k in payload:
            setattr(s,k,payload[k])
    if "config" in payload:
        s.config = json.dumps(payload["config"], ensure_ascii=False)
    await db.flush()
    return {"ok": True}
