from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.db.base import get_db
from backend.app.schemas.preview import PreviewRequest, PreviewResponse
from backend.app.formatting.engine import format_message
from backend.app.formatting.emoji import EmojiMapping as EmojiMap
from backend.app.models.emoji import EmojiMapping
from backend.app.models.channel import Channel
import json

router = APIRouter(prefix="/api/preview", tags=["preview"])

@router.post("", response_model=PreviewResponse)
async def preview(payload: PreviewRequest, db: AsyncSession = Depends(get_db)):
    # load emoji maps
    res = await db.execute(select(EmojiMapping).where(EmojiMapping.enabled==True))
    rows = res.scalars().all()
    maps=[]
    for r in rows:
        try:
            raw_ctx=json.loads(r.contexts) if r.contexts else None
            if raw_ctx is None or raw_ctx == "":
                ctx=None
            elif isinstance(raw_ctx, str):
                ctx=[raw_ctx]
            elif isinstance(raw_ctx, list):
                ctx=raw_ctx if len(raw_ctx)>0 else None
            else:
                ctx=None
        except:
            ctx=[r.contexts] if r.contexts else None
        maps.append(EmojiMap(unicode_emoji=r.unicode_emoji, custom_emoji_id=r.custom_emoji_id, enabled=r.enabled, contexts=ctx, priority=r.priority))

    # resolve channel style
    style_slug = payload.style_slug
    footer = None
    if payload.channel_id:
        cres = await db.execute(select(Channel).where(Channel.id==payload.channel_id))
        ch = cres.scalar_one_or_none()
        if ch:
            style_slug = style_slug or ch.style_id
            footer = ch.footer_text

    result = format_message(
        raw_text=payload.text,
        is_caption=payload.is_caption,
        channel_style_slug=style_slug,
        footer_text=footer,
        emoji_mappings=maps,
        enable_emoji=payload.enable_emoji,
    )
    return PreviewResponse(
        original=payload.text,
        formatted=result.text,
        html_formatted=result.html_text,
        changed=result.changed,
        category=result.category,
        style=result.style_slug,
        applied_rules=result.applied_rules,
        warnings=result.warnings,
    )
