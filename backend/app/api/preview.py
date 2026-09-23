import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.runtime import load_runtime
from backend.app.db.base import get_db
from backend.app.formatting.emoji import EmojiMapping as EmojiMap
from backend.app.formatting.engine import format_message
from backend.app.models.channel import Channel
from backend.app.models.emoji import EmojiMapping
from backend.app.schemas.preview import PreviewRequest, PreviewResponse
from backend.app.security.deps import get_current_admin
from backend.app.services.ai import enhance_with_ai
from backend.app.telegram.pipeline import parse_contexts, resolve_style

router = APIRouter(prefix="/api/preview", tags=["preview"])


class AIPreviewRequest(BaseModel):
    text: str
    category: str = "general"


@router.post("/ai-enhance")
async def preview_ai_enhance(payload: AIPreviewRequest, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    runtime = await load_runtime(db)
    enhanced = await enhance_with_ai(payload.text, payload.category, runtime=runtime)
    return {
        "original": payload.text,
        "enhanced": enhanced,
        "category": payload.category,
        "ai_used": enhanced is not None,
        "ai_ready": runtime.ai_ready,
    }


@router.post("", response_model=PreviewResponse)
async def preview(payload: PreviewRequest, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    runtime = await load_runtime(db)
    rows = (await db.execute(select(EmojiMapping).where(EmojiMapping.enabled == True))).scalars().all()  # noqa: E712
    maps = [
        EmojiMap(
            unicode_emoji=row.unicode_emoji,
            custom_emoji_id=row.custom_emoji_id,
            enabled=row.enabled,
            contexts=parse_contexts(row.contexts),
            priority=row.priority,
        )
        for row in rows
    ]
    style_slug = payload.style_slug
    footer = None
    header_enabled = False
    if payload.channel_id:
        channel = (await db.execute(select(Channel).where(Channel.id == payload.channel_id))).scalar_one_or_none()
        if channel:
            style_slug = style_slug or channel.style_id
            footer = channel.footer_text
            header_enabled = channel.header_enabled
    style = await resolve_style(db, style_slug)
    source = payload.text
    ai_note = None
    if payload.use_ai:
        enhanced = await enhance_with_ai(payload.text, "general", runtime=runtime, limit=900 if payload.is_caption else 3600)
        if enhanced:
            source = enhanced
            ai_note = "ai_enhanced"
    result = format_message(
        raw_text=source,
        is_caption=payload.is_caption,
        channel_style_slug=style_slug,
        footer_text=footer,
        emoji_mappings=maps,
        enable_emoji=payload.enable_emoji and runtime.premium_mode != "off",
        header_enabled=header_enabled,
        persian_normalize=runtime.persian_normalize,
        max_emoji=runtime.max_emoji_per_post,
        style_config=style,
    )
    rules = list(result.applied_rules)
    if ai_note:
        rules.append(ai_note)
    return PreviewResponse(
        original=payload.text,
        formatted=result.text,
        html_formatted=result.html_text,
        changed=result.changed or source != payload.text,
        category=result.category,
        style=result.style_slug,
        applied_rules=rules,
        warnings=result.warnings,
    )
