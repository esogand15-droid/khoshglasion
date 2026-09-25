import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.runtime import load_runtime
from backend.app.db.base import get_db
from backend.app.formatting.diff import line_diff
from backend.app.formatting.editor import ai_plan, analyze_post
from backend.app.formatting.emoji import EmojiMapping as EmojiMap
from backend.app.formatting.engine import format_message
from backend.app.models.channel import Channel
from backend.app.models.emoji import EmojiMapping
from backend.app.schemas.preview import PreviewRequest, PreviewResponse
from backend.app.security.deps import assert_editor, get_current_admin
from backend.app.services.ai import edit_with_ai
from backend.app.telegram.pipeline import parse_contexts, resolve_style

router = APIRouter(prefix="/api/preview", tags=["preview"])


def preview_ai_plan(text: str, use_ai: bool, ai_ready: bool) -> tuple[bool, dict, str | None]:
    """The lab uses the same lock as the bot. Exam options are never rewritten."""
    decision_obj = analyze_post(text)
    decision = decision_obj.as_dict()
    decision["ai_mode"] = ai_plan(decision_obj)
    if not use_ai:
        return False, decision, None
    if not ai_ready:
        return False, decision, "هوش مصنوعی آماده نیست"
    if decision["ai_mode"] == "skip":
        if decision_obj.has_options or decision_obj.category == "solution":
            return False, decision, "گزینه و پاسخ آزمون بازنویسی نمی‌شود"
        return False, decision, "متن کوتاه است و به هوش مصنوعی داده نمی‌شود"
    return True, decision, None


class AIPreviewRequest(BaseModel):
    text: str
    category: str = "general"


@router.post("/ai-enhance")
async def preview_ai_enhance(payload: AIPreviewRequest, db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    assert_editor(admin)
    runtime = await load_runtime(db)
    should_ai, decision, reason = preview_ai_plan(payload.text, True, runtime.ai_ready)
    enhanced = None
    if should_ai:
        enhanced, ai_reason = await edit_with_ai(
            payload.text,
            decision.get("category") or payload.category,
            runtime=runtime,
            mode=decision.get("ai_mode") or "tidy",
        )
        if not enhanced and not reason:
            reason = ai_reason
    return {
        "original": payload.text,
        "enhanced": enhanced,
        "category": decision.get("category") or payload.category,
        "ai_used": enhanced is not None,
        "ai_ready": runtime.ai_ready,
        "strategy": decision.get("strategy"),
        "reason": reason,
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
            category=row.category,
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
    should_ai, decision, lock_reason = preview_ai_plan(payload.text, payload.use_ai, runtime.ai_ready)
    if should_ai:
        enhanced, ai_reason = await edit_with_ai(
            payload.text,
            decision.get("category") or "general",
            runtime=runtime,
            limit=900 if payload.is_caption else 3600,
            mode=decision.get("ai_mode") or "tidy",
        )
        if enhanced:
            source = enhanced
        elif not lock_reason:
            lock_reason = f"خروجی مدل پذیرفته نشد: {ai_reason}"
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
        footer_url=runtime.footer_url,
        support_username=runtime.support_username,
    )
    rules = list(result.applied_rules)
    if ai_note:
        rules.append(ai_note)
    rules.append(f"strategy:{decision.get('strategy')}")
    warnings = list(result.warnings)
    if lock_reason:
        warnings.append(lock_reason)
    return PreviewResponse(
        original=payload.text,
        formatted=result.text,
        html_formatted=result.html_text,
        changed=result.changed or source != payload.text,
        category=result.category,
        style=result.style_slug,
        applied_rules=rules,
        warnings=warnings,
        decision=decision,
        ai_used=bool(ai_note),
        strategy=decision.get("strategy"),
        diff=line_diff(payload.text, result.text),
    )
