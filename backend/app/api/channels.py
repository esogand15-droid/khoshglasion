from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.base import get_db
from backend.app.models.channel import Channel
from backend.app.schemas.channel import ChannelCreate, ChannelUpdate
from backend.app.security.deps import assert_editor, get_current_admin
from backend.app.services.audit import write_audit
from backend.app.telegram.bot import get_bot

router = APIRouter(prefix="/api/channels", tags=["channels"])


def dump_channel(channel: Channel) -> dict:
    return {
        "id": channel.id,
        "chat_id": channel.chat_id,
        "username": channel.username,
        "title": channel.title,
        "enabled": channel.enabled,
        "auto_beautify": channel.auto_beautify,
        "emoji_replacement": channel.emoji_replacement,
        "style_id": channel.style_id,
        "footer_text": channel.footer_text,
        "header_enabled": channel.header_enabled,
        "processing_mode": channel.processing_mode,
        "ai_rewrite": channel.ai_rewrite,
        "edit_delay_seconds": channel.edit_delay_seconds,
        "signature_text": channel.signature_text,
        "signature_url": channel.signature_url,
        "skip_keywords": channel.skip_keywords,
        "min_chars": channel.min_chars,
        "preserve_buttons": channel.preserve_buttons,
        "notes": channel.notes,
        "posts_edited": channel.posts_edited,
        "last_error": channel.last_error,
        "last_post_at": channel.last_post_at.isoformat() if channel.last_post_at else None,
        "can_edit": channel.can_edit,
        "created_at": channel.created_at.isoformat() if channel.created_at else None,
    }


@router.get("")
async def list_channels(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    rows = (await db.execute(select(Channel).order_by(Channel.created_at.desc()))).scalars().all()
    return [dump_channel(row) for row in rows]


@router.post("")
async def create_channel(payload: ChannelCreate, request: Request, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    existing = (await db.execute(select(Channel).where(Channel.chat_id == payload.chat_id))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="این کانال قبلاً ثبت شده")
    channel = Channel(**payload.model_dump())
    db.add(channel)
    await db.flush()
    await write_audit(db, admin=admin, action="create", resource="channel", resource_id=channel.id, new_value=payload.model_dump(), ip_address=request.client.host if request.client else None)
    return dump_channel(channel)


@router.patch("/{channel_id}")
async def update_channel(channel_id: str, payload: ChannelUpdate, request: Request, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    channel = (await db.execute(select(Channel).where(Channel.id == channel_id))).scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="کانال پیدا نشد")
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(channel, key, value)
    await write_audit(db, admin=admin, action="update", resource="channel", resource_id=channel.id, new_value=changes, ip_address=request.client.host if request.client else None)
    return dump_channel(channel)


@router.delete("/{channel_id}")
async def delete_channel(channel_id: str, request: Request, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    channel = (await db.execute(select(Channel).where(Channel.id == channel_id))).scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="کانال پیدا نشد")
    await db.delete(channel)
    await write_audit(db, admin=admin, action="delete", resource="channel", resource_id=channel_id, ip_address=request.client.host if request.client else None)
    return {"ok": True}


@router.post("/sync")
async def sync_channel(payload: dict, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    chat_id = payload.get("chat_id")
    if chat_id is None:
        raise HTTPException(status_code=400, detail="chat_id لازم است")
    bot = get_bot()
    if not bot:
        raise HTTPException(status_code=400, detail="توکن ربات تنظیم نشده")
    try:
        chat = await bot.get_chat(int(chat_id))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"تلگرام این کانال را برنگرداند: {exc}") from exc
    channel = (await db.execute(select(Channel).where(Channel.chat_id == int(chat_id)))).scalar_one_or_none()
    if channel is None:
        channel = Channel(chat_id=int(chat_id), enabled=True)
        db.add(channel)
    channel.title = chat.title or channel.title
    channel.username = chat.username or channel.username
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(int(chat_id), me.id)
        status = getattr(member, "status", "")
        can_edit = status == "creator" or bool(getattr(member, "can_edit_messages", False))
        channel.can_edit = can_edit
        if not can_edit:
            channel.last_error = "ربات دسترسی ویرایش پیام ندارد"
    except Exception as exc:
        channel.last_error = f"نتوانستم سطح دسترسی را بخوانم: {exc}"
    await db.flush()
    return dump_channel(channel)
