from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.db.base import get_db
from backend.app.models.channel import Channel
from backend.app.schemas.channel import ChannelCreate, ChannelUpdate
from backend.app.security.deps import get_current_admin
import json

router = APIRouter(prefix="/api/channels", tags=["channels"])

@router.get("")
async def list_channels(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    res = await db.execute(select(Channel).order_by(Channel.created_at.desc()))
    items = res.scalars().all()
    return [{"id":c.id,"chat_id":c.chat_id,"username":c.username,"title":c.title,"enabled":c.enabled,"auto_beautify":c.auto_beautify,"emoji_replacement":c.emoji_replacement,"style_id":c.style_id,"footer_text":c.footer_text,"header_enabled":c.header_enabled,"processing_mode":c.processing_mode,"created_at":c.created_at.isoformat() if c.created_at else None} for c in items]

@router.post("")
async def create_channel(payload: ChannelCreate, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    # check duplicate chat_id
    res = await db.execute(select(Channel).where(Channel.chat_id==payload.chat_id))
    if res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Channel already exists")
    ch = Channel(**payload.model_dump())
    db.add(ch)
    await db.flush()
    return {"id": ch.id, "chat_id": ch.chat_id}

@router.patch("/{channel_id}")
async def update_channel(channel_id: str, payload: ChannelUpdate, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    res = await db.execute(select(Channel).where(Channel.id==channel_id))
    ch = res.scalar_one_or_none()
    if not ch:
        raise HTTPException(status_code=404, detail="Not found")
    for k,v in payload.model_dump(exclude_unset=True).items():
        setattr(ch,k,v)
    await db.flush()
    return {"ok": True}

@router.delete("/{channel_id}")
async def delete_channel(channel_id: str, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    res = await db.execute(select(Channel).where(Channel.id==channel_id))
    ch = res.scalar_one_or_none()
    if not ch:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(ch)
    await db.flush()
    return {"ok": True}
