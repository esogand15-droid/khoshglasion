"""Collect public channel notes, draft an original post, and publish on a slot.

The premium session only reads channels it can already open. It does not join
private invites. A draft is never the source text copied verbatim.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.content.pipeline import extra_long_numbers, extract_facts, invented_quotes
from backend.app.content.prompts import MODE_PROMPT, PROMPTS
from backend.app.formatting.editor import analyze_post
from backend.app.formatting.textutil import missing_long_numbers
from backend.app.models.automation import AutomationConfig, DraftPost, HashtagRule, NewsSource, PromptVersion, PublishSlot
from backend.app.services.ai import complete_text
from backend.app.services.prompts import wrap_post

logger = logging.getLogger(__name__)
TEHRAN = timezone(timedelta(hours=3, minutes=30))
SOURCE_RE = re.compile(r"^(?:-?\d{5,}|[A-Za-z][A-Za-z0-9_]{3,31})$")
COLLECT_GAP = timedelta(minutes=20)


def normalize_source(raw: str) -> str | None:
    text = (raw or "").strip()
    text = re.sub(r"^https?://", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(?:t\.me|telegram\.me)/", "", text, flags=re.IGNORECASE)
    text = text.split("?")[0].strip("/")
    if text.startswith("+") or text.startswith("joinchat") or "/+" in text:
        return None
    text = text.split("/")[0].lstrip("@")
    return text if SOURCE_RE.fullmatch(text) else None


def too_verbatim(source: str, draft: str) -> bool:
    compact_source = re.sub(r"\s+", " ", source or "")
    compact_draft = re.sub(r"\s+", " ", draft or "")
    window = 90
    if len(compact_source) < window:
        return False
    for index in range(0, len(compact_source) - window + 1, 30):
        if compact_source[index:index + window] in compact_draft:
            return True
    return False


def accept_draft(source_blob: str, draft: str | None) -> tuple[str | None, str]:
    cleaned = (draft or "").strip()
    if not cleaned or cleaned.upper() == "SKIP":
        return None, "skip"
    if len(cleaned) < 40:
        return None, "too_short"
    if missing_long_numbers(source_blob, cleaned):
        return None, "dropped_numbers"
    if extra_long_numbers(source_blob, cleaned):
        return None, "invented_numbers"
    if invented_quotes(source_blob, cleaned):
        return None, "invented_quote"
    if too_verbatim(source_blob, cleaned):
        return None, "verbatim"
    return cleaned, "ok"


def tehran_now(now: datetime | None = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(TEHRAN)


def next_slot_time(slots: list[PublishSlot], now: datetime | None = None, category: str | None = None) -> datetime | None:
    local = tehran_now(now)
    enabled = [
        slot for slot in slots
        if slot.enabled and (not category or not slot.category or slot.category == category)
    ]
    if not enabled:
        return None
    best: datetime | None = None
    for day in range(0, 8):
        base = (local + timedelta(days=day)).replace(second=0, microsecond=0)
        for slot in enabled:
            candidate = base.replace(hour=int(slot.hour), minute=int(slot.minute))
            if candidate <= local:
                continue
            if best is None or candidate < best:
                best = candidate
    return best


def slot_is_due(slot: PublishSlot, now: datetime | None = None, used_keys: set[str] | None = None) -> bool:
    if not slot.enabled:
        return False
    local = tehran_now(now)
    if int(slot.hour) != local.hour or not (int(slot.minute) <= local.minute < int(slot.minute) + 5):
        return False
    key = f"{slot.id}:{local.date().isoformat()}"
    return key not in (used_keys or set())


def slot_key(slot: PublishSlot, now: datetime | None = None) -> str:
    return f"{slot.id}:{tehran_now(now).date().isoformat()}"


async def get_config(db: AsyncSession) -> AutomationConfig:
    row = (await db.execute(select(AutomationConfig).limit(1))).scalar_one_or_none()
    if row is None:
        row = AutomationConfig()
        db.add(row)
        await db.flush()
    return row


async def active_prompt(db: AsyncSession, name: str) -> str:
    row = (
        await db.execute(
            select(PromptVersion).where(PromptVersion.name == name, PromptVersion.active == True).limit(1)  # noqa: E712
        )
    ).scalar_one_or_none()
    if row and row.body:
        return row.body
    return PROMPTS.get(name) or PROMPTS["generator"]


async def ensure_content_defaults(db: AsyncSession) -> None:
    from backend.app.content.pipeline import OFFICIAL_HASHTAGS

    existing = (await db.execute(select(HashtagRule.id).limit(1))).first()
    if existing is None:
        for index, (tag, category) in enumerate(OFFICIAL_HASHTAGS):
            db.add(HashtagRule(tag=tag, category=category, priority=100 - index))
    present = set((await db.execute(select(PromptVersion.name))).scalars().all())
    for name, body in PROMPTS.items():
        if name not in present:
            db.add(PromptVersion(name=name, version=1, body=body, active=True))
    await db.flush()


async def draft_from_source(
    source_text: str,
    source_label: str,
    runtime,
    *,
    mode: str = "generate",
    avoid: list[str] | None = None,
    template_hint: str | None = None,
    system_prompt: str | None = None,
) -> tuple[str | None, str, str]:
    decision = analyze_post(source_text)
    if runtime is None or not runtime.ai_ready:
        return None, decision.category, "not_ready"
    prompt_name = MODE_PROMPT.get(mode, "generator")
    facts = extract_facts(source_text)
    openings = " | ".join(item for item in (avoid or []) if item) or "هیچ"
    raw = await complete_text(runtime, [
        {"role": "system", "content": system_prompt or PROMPTS[prompt_name]},
        {
            "role": "user",
            "content": (
                f"زاویه: {template_hint or 'طبیعی'}\n"
                f"شروع‌های اخیر که نباید تکرار شوند: {openings}\n"
                f"عددهای مجاز: {', '.join(facts['numbers']) or 'هیچ'}\n"
                f"منبع: {source_label}\n"
                f"{wrap_post(source_text[:1800])}"
            ),
        },
    ])
    accepted, guard = accept_draft(source_text, raw)
    return (accepted, decision.category, "ok") if accepted else (None, decision.category, guard)


def append_hashtags(body: str, tags: list[str]) -> str:
    existing = set(re.findall(r"#([\w\u0600-\u06FF_]+)", body or ""))
    fresh = [tag for tag in tags if tag not in existing]
    if not fresh:
        return body.strip()
    return body.strip() + "\n\n" + " ".join(f"#{tag}" for tag in fresh)


def remember_version(draft: DraftPost, body: str, reason: str) -> None:
    import json
    history = []
    if draft.versions_json:
        try:
            history = json.loads(draft.versions_json)
        except json.JSONDecodeError:
            history = []
    history.append({"version": draft.version or 1, "body": draft.body or "", "reason": reason})
    draft.versions_json = json.dumps(history[-8:], ensure_ascii=False)
    draft.version = (draft.version or 1) + 1
    draft.body = body
    draft.updated_at = datetime.now(timezone.utc)
