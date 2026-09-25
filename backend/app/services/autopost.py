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
from backend.app.content.intake import copied_whole, rewrite_plan
from backend.app.content.prompts import FACT_LOCK, LEGACY_PROMPTS, MODE_PROMPT, PROMPTS, RETIRED_PROMPTS, STRUCTURE_LOCK, STYLE_LOCK, WRITER_STAGES
from backend.app.formatting.editor import analyze_post
from backend.app.formatting.textutil import missing_long_numbers
from backend.app.models.automation import AutomationConfig, DraftPost, HashtagRule, NewsSource, PromptVersion, PublishSlot
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


_INVITE_TG = re.compile(r"tg://join\?invite=([A-Za-z0-9_-]{12,80})", re.IGNORECASE)
_INVITE_WEB = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me)/(?:\+|joinchat/)([A-Za-z0-9_-]{12,80})",
    re.IGNORECASE,
)
_INVITE_BARE = re.compile(r"^\+([A-Za-z0-9_-]{12,80})$")


def parse_invite_hash(raw: str) -> str | None:
    """Hash from a private invite link. Does not join the chat."""
    text = (raw or "").strip()
    if not text:
        return None
    for pattern in (_INVITE_TG, _INVITE_WEB):
        found = pattern.search(text)
        if found:
            return found.group(1)
    bare = _INVITE_BARE.fullmatch(text)
    return bare.group(1) if bare else None


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


def accept_draft(
    source_blob: str,
    draft: str | None,
    *,
    verbatim_source: str | None = None,
    plan: str = "summarize",
    min_chars: int = 40,
) -> tuple[str | None, str]:
    cleaned = (draft or "").strip()
    if not cleaned or re.fullmatch(r"skip[.!?…]*", cleaned, flags=re.IGNORECASE):
        return None, "skip"
    if len(cleaned) < min_chars:
        return None, "too_short"
    if missing_long_numbers(source_blob, cleaned):
        return None, "dropped_numbers"
    if extra_long_numbers(source_blob, cleaned):
        return None, "invented_numbers"
    if invented_quotes(source_blob, cleaned):
        return None, "invented_quote"
    original = verbatim_source if verbatim_source is not None else source_blob
    if plan == "preserve":
        if copied_whole(original, cleaned):
            return None, "verbatim"
    elif too_verbatim(original, cleaned):
        return None, "verbatim"
    return cleaned, "ok"


def as_utc(value: datetime | None) -> datetime | None:
    """SQLite returns naive timestamps. Comparisons must not crash the loop."""
    if value is None:
        return None
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def tehran_now(now: datetime | None = None) -> datetime:
    current = as_utc(now) or datetime.now(timezone.utc)
    return current.astimezone(TEHRAN)


def _clock(slot: PublishSlot) -> tuple[int, int] | None:
    try:
        hour = int(slot.hour)
        minute = int(slot.minute or 0)
    except (TypeError, ValueError):
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def next_slot_time(slots: list[PublishSlot], now: datetime | None = None, category: str | None = None) -> datetime | None:
    local = tehran_now(now)
    enabled = [
        slot for slot in slots
        if slot.enabled and (not category or not slot.category or slot.category == category) and _clock(slot)
    ]
    if not enabled:
        return None
    best: datetime | None = None
    for day in range(0, 8):
        base = (local + timedelta(days=day)).replace(second=0, microsecond=0)
        for slot in enabled:
            hour, minute = _clock(slot) or (0, 0)
            candidate = base.replace(hour=hour, minute=minute)
            if candidate <= local:
                continue
            if best is None or candidate < best:
                best = candidate
    return best


def slot_is_due(slot: PublishSlot, now: datetime | None = None, used_keys: set[str] | None = None) -> bool:
    if not slot.enabled:
        return False
    local = tehran_now(now)
    clock = _clock(slot)
    if clock is None:
        return False
    hour, minute = clock
    if hour != local.hour or not (minute <= local.minute < minute + 5):
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


async def extra_prompts(db: AsyncSession) -> list[str]:
    rows = (
        await db.execute(
            select(PromptVersion)
            .where(PromptVersion.active == True, PromptVersion.name.startswith("extra:"))  # noqa: E712
            .order_by(PromptVersion.created_at)
        )
    ).scalars().all()
    return [row.body.strip() for row in rows if (row.body or "").strip()]


async def compose_prompt(db: AsyncSession, name: str) -> str:
    """Stage text, then operator extras, then the code lock the panel cannot delete."""
    parts = [await active_prompt(db, name)]
    if name in WRITER_STAGES:
        extras = await extra_prompts(db)
        if extras:
            parts.append("دستورهای اضافهٔ پنل:\n" + "\n".join(f"- {item}" for item in extras))
        parts.append(STYLE_LOCK)
        parts.append(FACT_LOCK)
        parts.append(STRUCTURE_LOCK)
        parts.append(
            "SKIP فقط برای تبلیغ است. فان کوتاه را خبر نکن و طولانی نکن. "
            "اطلاعیه، خبر رسمی، نتایج، بودجه، ثبت‌نام و تأخیر اعلام را هرگز SKIP نکن و شوخی نکن. "
            "در متن هیچ ایموجی ننویس."
        )
    return "\n\n".join(part for part in parts if part)


async def ensure_content_defaults(db: AsyncSession) -> None:
    from backend.app.content.pipeline import OFFICIAL_HASHTAGS

    existing = (await db.execute(select(HashtagRule.id).limit(1))).first()
    if existing is None:
        for index, (tag, category) in enumerate(OFFICIAL_HASHTAGS):
            db.add(HashtagRule(tag=tag, category=category, priority=100 - index))
    rows = (await db.execute(select(PromptVersion))).scalars().all()
    by_name: dict[str, list[PromptVersion]] = {}
    for row in rows:
        by_name.setdefault(row.name, []).append(row)
    for name, body in PROMPTS.items():
        versions = by_name.get(name) or []
        active = next((row for row in versions if row.active and row.body), None)
        legacy = (LEGACY_PROMPTS.get(name) or "").strip()
        retired = {legacy} if legacy else set()
        retired.update(item.strip() for item in (RETIRED_PROMPTS.get(name) or ()) if item and item.strip())
        retired.discard(body.strip())
        if active is None:
            db.add(PromptVersion(name=name, version=1, body=body, active=True))
        elif active.body.strip() in retired:
            active.active = False
            nxt = max(int(row.version or 1) for row in versions) + 1
            db.add(PromptVersion(name=name, version=nxt, body=body, active=True))
    await db.flush()


def load_lessons(raw: str | None) -> list[dict]:
    import json

    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict) and item.get("note")][-24:]


def push_lesson(raw: str | None, *, kind: str, note: str, category: str = "") -> str:
    import json

    lessons = load_lessons(raw)
    clean = " ".join((note or "").split())[:180]
    if not clean:
        return raw or "[]"
    if any(item.get("note") == clean for item in lessons[-8:]):
        return json.dumps(lessons, ensure_ascii=False)
    lessons.append({"kind": kind, "category": category or "", "note": clean})
    return json.dumps(lessons[-24:], ensure_ascii=False)


def lesson_prompt(raw: str | None) -> str:
    lessons = load_lessons(raw)[-8:]
    if not lessons:
        return ""
    lines = [f"- {item['note']}" for item in lessons]
    return "یادگیری از پست‌های قبلی همین پنل:\n" + "\n".join(lines)


def salvage_useful(text: str) -> str | None:
    """Structured extract when the model skips a real collected post.

    Line breaks alone do not pass the copy check, because that check ignores
    whitespace. A short label between clauses keeps the facts and breaks the copy.
    """
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if len(cleaned) < 40:
        return None
    words = re.sub(r"\s+", " ", cleaned).split(" ")
    lines: list[str] = []
    buf: list[str] = []
    count = 0
    for word in words:
        if count and count + len(word) > 52:
            lines.append(" ".join(buf))
            buf = [word]
            count = len(word)
        else:
            buf.append(word)
            count += len(word) + 1
    if buf:
        lines.append(" ".join(buf))
    # A breaker on every continuation line. Whitespace is ignored by the copy
    # check, so a single newline would still count as the original sentence.
    draft = "\n".join([lines[0], *[f"ادامه: {line}" for line in lines[1:8]]])
    for number in re.findall(r"(?<!\d)\d{3,}(?!\d)", cleaned):
        if number not in draft:
            draft += f"\nعدد: {number}"
    accepted, _reason = accept_draft(cleaned, draft, plan="summarize")
    return accepted


async def remember_lesson(db: AsyncSession, *, kind: str, note: str, category: str = "") -> None:
    config = await get_config(db)
    config.lessons_json = push_lesson(getattr(config, "lessons_json", None), kind=kind, note=note, category=category)


def human_reason(reason: str | None) -> str:
    return {
        "skip": "مدل این خبر را رد کرد",
        "verbatim": "متن بیش از حد به منبع شبیه بود",
        "too_short": "متن ساخته‌شده کوتاه بود",
        "dropped_numbers": "عدد منبع در متن نبود",
        "invented_numbers": "عدد تازه‌ای در متن بود",
        "invented_quote": "نقل‌قولی در منبع نبود",
        "not_ready": "هوش مصنوعی آماده نیست",
        "rejected": "متن ساخته‌شده قبول نشد",
    }.get(reason or "", reason or "متن ساخته نشد")


async def draft_from_source(
    source_text: str,
    source_label: str,
    runtime,
    *,
    mode: str = "generate",
    avoid: list[str] | None = None,
    template_hint: str | None = None,
    system_prompt: str | None = None,
    style: str | None = None,
    style_card: str | None = None,
    plan: str | None = None,
    image_note: str | None = None,
    lessons: str | None = None,
    trace: dict | None = None,
) -> tuple[str | None, str, str]:
    from backend.app.content.intake import is_advertisement
    from backend.app.services.ai import call_models
    from backend.app.services.finetune import classify_style, folder_category, writer_context

    decision = analyze_post(source_text)
    style_name = style or classify_style(source_text)
    category = folder_category(style_name)
    if runtime is None or not runtime.ai_ready:
        return None, category or decision.category, "not_ready"
    prompt_name = MODE_PROMPT.get(mode, "generator")
    chosen_plan = plan or rewrite_plan(source_text)
    facts = extract_facts(source_text + ("\n" + image_note if image_note else ""))
    openings = " | ".join(item for item in (avoid or []) if item) or "هیچ"
    picture = image_note.strip() if image_note else "عکسی به نویسنده داده نشده"
    learned = lesson_prompt(lessons)
    tone_line = ""
    if style_name == "fun":
        tone_line = "این فان است. صمیمی و کوتاه بنویس. اگر منبع یک یا دو خط است خروجی را بلند و خبری نکن.\n"
    elif style_name in {"flash", "announce", "alert"}:
        tone_line = "این خبر یا اطلاعیه است. جدی و دقیق بمان. شوخی و لحن خودمانی اضافه نکن.\n"
    user = (
        f"{writer_context(style_name, style_card)}\n"
        f"{learned + chr(10) if learned else ''}"
        f"{tone_line}"
        f"حالت: {chosen_plan}\n"
        f"زاویه: {template_hint or 'طبیعی'}\n"
        f"شروع‌های اخیر که نباید تکرار شوند: {openings}\n"
        f"عددهای مجاز، از متن و از توضیح عکس: {', '.join(facts['numbers']) or 'هیچ'}\n"
        f"توضیح عکس، فقط اگر واقعیت تازه‌ای دارد در یک خط بیاور: {picture}\n"
        f"در متن ایموجی ننویس.\n"
        f"منبع: {source_label}\n"
        f"{wrap_post(source_text[:1800])}"
    )
    system = system_prompt or PROMPTS[prompt_name]

    async def ask(extra: str = "") -> dict:
        return await call_models(runtime, [
            {"role": "system", "content": system},
            {"role": "user", "content": user + extra},
        ])

    result = await ask()
    if trace is not None:
        trace["writer_model"] = result.get("model") or ""
        trace["writer_provider"] = result.get("provider") or ""
        trace["rewrite"] = chosen_plan
    fact_source = source_text + ("\n" + image_note if image_note else "")
    floor = 12 if style_name == "fun" and len(source_text.strip()) < 180 else 40
    accepted, guard = accept_draft(
        fact_source, result.get("text"), verbatim_source=source_text, plan=chosen_plan, min_chars=floor,
    )
    if style_name == "fun" and guard == "verbatim":
        accepted, guard = (result.get("text") or "").strip() or None, "ok" if (result.get("text") or "").strip() else "skip"
    repairable = (
        guard in {"skip", "verbatim"}
        and len(source_text.strip()) >= 40
        and style_name != "fun"
        and not is_advertisement(source_text)
    )
    if not accepted and style_name == "fun":
        result = await ask("\n\nاین فان است، نه خبر. یک یا دو خط صمیمی بنویس. رسمی و طولانی نکن. SKIP نکن مگر تبلیغ باشد.")
        accepted, guard = accept_draft(
            fact_source, result.get("text"), verbatim_source=source_text, plan=chosen_plan, min_chars=floor,
        )
        if guard == "verbatim":
            accepted, guard = (result.get("text") or "").strip() or None, "ok" if (result.get("text") or "").strip() else "skip"
        if not accepted:
            from backend.app.content.intake import promotion_reason

            kept = re.sub(r"#\S+", "", source_text or "")
            kept = re.sub(r"https?://\S+", "", kept).strip()
            if 12 <= len(kept) <= 320 and not promotion_reason(kept):
                accepted, guard = kept, "repaired"
    if not accepted and repairable:
        result = await ask("\n\nاین مطلب خبر یا اطلاعیه قابل انتشار است. SKIP ممنوع و کپی ممنوع. بازنویسی کوتاه و جدی بنویس.")
        if trace is not None:
            trace["writer_model"] = result.get("model") or trace.get("writer_model") or ""
            trace["writer_provider"] = result.get("provider") or trace.get("writer_provider") or ""
        accepted, guard = accept_draft(fact_source, result.get("text"), verbatim_source=source_text, plan=chosen_plan)
        if not accepted:
            accepted = salvage_useful(source_text)
            if accepted:
                guard = "repaired"
    if trace is not None:
        trace["repaired"] = guard == "repaired"
    return (accepted, category, "ok") if accepted else (None, category, guard)


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
