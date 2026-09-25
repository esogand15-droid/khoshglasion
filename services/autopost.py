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

from backend.app.formatting.editor import analyze_post
from backend.app.formatting.textutil import missing_long_numbers
from backend.app.models.automation import AutomationConfig, DraftPost, NewsSource, PublishSlot
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
    if too_verbatim(source_blob, cleaned):
        return None, "verbatim"
    return cleaned, "ok"


def tehran_now(now: datetime | None = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(TEHRAN)


def next_slot_time(slots: list[PublishSlot], now: datetime | None = None) -> datetime | None:
    local = tehran_now(now)
    enabled = [slot for slot in slots if slot.enabled]
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


async def draft_from_source(source_text: str, source_label: str, runtime) -> tuple[str | None, str, str]:
    decision = analyze_post(source_text)
    if runtime is None or not runtime.ai_ready:
        return None, decision.category, "not_ready"
    raw = await complete_text(runtime, [
        {
            "role": "system",
            "content": (
                "تو ویراستار کانال مشاوره کنکور هستی. از یادداشت منبع یک پست کوتاه و مستقل بنویس. "
                "جمله را کپی نکن. عدد، تاریخ و اسم را فقط اگر در منبع هست نگه دار. چیز تازه اختراع نکن. "
                "فوتر و خط جداکننده ننویس. اگر قابل استفاده نیست فقط SKIP بنویس."
            ),
        },
        {"role": "user", "content": f"منبع: {source_label}\n{wrap_post(source_text[:1800])}"},
    ])
    accepted, guard = accept_draft(source_text, raw)
    return (accepted, decision.category, "ok") if accepted else (None, decision.category, guard)
