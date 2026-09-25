"""Normalize, classify, dedupe and validate source notes before a draft exists.

AI is not called here. Generation stays in the service layer so a duplicate
never spends a model call.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re

OFFICIAL_HASHTAGS = (
    ("خبر", "news"),
    ("مشاوره", "consulting"),
    ("انگیزشی", "motivational"),
    ("فارغ_از_درس", "general"),
    ("آموزشی", "lesson"),
    ("انتخاب_رشته", "major_choice"),
    ("معرفی_رشته", "major_choice"),
    ("نکات_درسی", "lesson"),
    ("تکنیک_مطالعه", "planning"),
    ("مدیریت_زمان", "planning"),
    ("کنکوری", "exam"),
    ("دانشگاه", "school"),
    ("بازار_کار", "general"),
    ("درآمد", "discount"),
    ("تجربه_دانشجویی", "experience"),
    ("سوال_شما", "qa"),
    ("نکته", "lesson"),
    ("آمار_و_اطلاعات", "rank"),
    ("تجربه", "experience"),
    ("حرف_دل", "motivational"),
    ("طنز", "general"),
    ("معرفی", "resource"),
    ("اطلاعیه", "announcement"),
)

CATEGORY_TAG = {
    "news": "خبر",
    "announcement": "اطلاعیه",
    "registration": "اطلاعیه",
    "consulting": "مشاوره",
    "motivational": "انگیزشی",
    "lesson": "آموزشی",
    "planning": "تکنیک_مطالعه",
    "resource": "معرفی",
    "exam": "کنکوری",
    "rank": "آمار_و_اطلاعات",
    "major_choice": "انتخاب_رشته",
    "experience": "تجربه",
    "qa": "سوال_شما",
    "discount": "درآمد",
    "school": "دانشگاه",
    "general": "نکته",
}

AD_WORDS = ("تبلیغ", "اسپانسر", "همکاری تبلیغاتی", "کد تخفیف", "فالو کن و جایزه")
LOW_VALUE = ("جوک", "استیکر", "فقط فوروارد")


def normalize_text(text: str) -> str:
    folded = (text or "").replace("ي", "ی").replace("ك", "ک")
    folded = re.sub(r"https?://\S+", " ", folded)
    folded = re.sub(r"[@#][\w\u0600-\u06FF_]+", " ", folded)
    folded = re.sub(r"\s+", " ", folded).strip().lower()
    return folded


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()[:24]


def opening_signature(text: str) -> str:
    line = next((item.strip() for item in (text or "").splitlines() if item.strip()), "")
    line = re.sub(r"^[^\w\u0600-\u06FF]+", "", line)
    return re.sub(r"\s+", " ", line)[:42]


def too_similar(new_text: str, recent: list[str], threshold: float = 0.72) -> bool:
    signature = opening_signature(new_text)
    if len(signature) >= 12 and any(opening_signature(old) == signature for old in recent):
        return True
    fresh = _shingles(new_text)
    if len(fresh) < 4:
        return False
    for old in recent:
        previous = _shingles(old)
        if len(previous) < 4:
            continue
        overlap = len(fresh & previous) / min(len(fresh), len(previous))
        if overlap >= threshold:
            return True
    return False


def _shingles(text: str, size: int = 4) -> set[str]:
    words = normalize_text(text).split()
    if len(words) < size:
        return set(words)
    return {" ".join(words[index:index + size]) for index in range(0, len(words) - size + 1)}


def choose_hashtags(category: str, text: str, *, enabled: set[str] | None = None, forbidden: set[str] | None = None) -> list[str]:
    blocked = forbidden or set()
    primary = CATEGORY_TAG.get(category, "نکته")
    chosen: list[str] = []
    if primary not in blocked and (enabled is None or primary in enabled):
        chosen.append(primary)
    folded = text or ""
    for tag, _mapped in OFFICIAL_HASHTAGS:
        if tag in blocked or tag in chosen:
            continue
        if enabled is not None and tag not in enabled:
            continue
        if tag.replace("_", " ") in folded or f"#{tag}" in folded:
            chosen.append(tag)
        if len(chosen) >= 3:
            break
    return [tag for tag in chosen if tag not in blocked][:3]


def judge_value(text: str, *, created_at: datetime | None = None, now: datetime | None = None) -> dict:
    raw = (text or "").strip()
    reasons: list[str] = []
    if len(raw) < 40:
        return {"value": "LOW_VALUE", "importance": "low", "confidence": "low", "reasons": ["too_short"]}
    if any(word in raw for word in AD_WORDS):
        reasons.append("advertisement")
        return {"value": "ADVERTISEMENT", "importance": "low", "confidence": "low", "reasons": reasons}
    if any(word in raw for word in LOW_VALUE):
        return {"value": "LOW_VALUE", "importance": "low", "confidence": "low", "reasons": ["low_value"]}
    current = now or datetime.now(timezone.utc)
    if created_at and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age_hours = None
    if created_at:
        age_hours = (current - created_at.astimezone(timezone.utc)).total_seconds() / 3600
        if age_hours > 72:
            reasons.append("stale")
    importance = "high" if any(word in raw for word in ("فوری", "اطلاعیه", "اعلام شد", "مهلت")) else "normal"
    if age_hours is not None and age_hours > 72 and importance != "high":
        return {"value": "OUTDATED", "importance": "low", "confidence": "medium", "reasons": reasons, "age_hours": round(age_hours, 1)}
    value = "BREAKING" if importance == "high" else "USEFUL"
    return {
        "value": value,
        "importance": importance,
        "confidence": "medium",
        "reasons": reasons,
        "age_hours": None if age_hours is None else round(age_hours, 1),
    }


def source_url(username: str, message_id: int) -> str:
    handle = (username or "").lstrip("@")
    if handle.lstrip("-").isdigit():
        return ""
    return f"https://t.me/{handle}/{message_id}"


def attribution_line(username: str, mode: str, category: str) -> str:
    if mode == "never":
        return ""
    if mode == "news" and category not in {"news", "announcement", "registration"}:
        return ""
    handle = (username or "").lstrip("@")
    if not handle or handle.lstrip("-").isdigit():
        return ""
    return f"منبع: @{handle}"


def should_auto_schedule(judgment: dict, validation_ok: bool, similar: bool) -> bool:
    if not validation_ok or similar:
        return False
    if judgment.get("confidence") == "low":
        return False
    if judgment.get("value") in {"LOW_VALUE", "ADVERTISEMENT", "IRRELEVANT", "OUTDATED", "DUPLICATE", "UNTRUSTED"}:
        return False
    return True


def extract_facts(text: str) -> dict:
    from backend.app.formatting.textutil import extract_protected_tokens, normalize_digits

    raw = text or ""
    numbers = sorted(set(re.findall(r"\d{2,}", normalize_digits(raw))))
    tokens = extract_protected_tokens(raw)
    return {
        "numbers": numbers[:12],
        "links": [token for token in tokens if token.startswith("http")][:6],
        "mentions": [token for token in tokens if token.startswith("@")][:6],
    }


def extra_long_numbers(source: str, draft: str) -> list[str]:
    from backend.app.formatting.textutil import normalize_digits

    source_nums = set(re.findall(r"\d{3,}", normalize_digits(source or "")))
    draft_nums = set(re.findall(r"\d{3,}", normalize_digits(draft or "")))
    return sorted(draft_nums - source_nums)


def invented_quotes(source: str, draft: str) -> bool:
    for quote in re.findall(r"«([^»]{8,})»", draft or ""):
        if quote not in (source or ""):
            return True
    return False


def parse_analysis(raw: str | None) -> dict | None:
    import json

    text = (raw or "").strip()
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def merge_analysis(base: dict, parsed: dict | None, source: str) -> dict:
    merged = dict(base)
    if not parsed:
        merged["confidence"] = "low"
        merged["reasons"] = list(merged.get("reasons") or []) + ["analysis_unparsed"]
        return merged
    summary = str(parsed.get("summary") or "").strip()
    if summary and extra_long_numbers(source, summary):
        merged["confidence"] = "low"
        merged["reasons"] = list(merged.get("reasons") or []) + ["ai_invented_number"]
        return merged
    if summary:
        merged["summary"] = summary[:400]
    category = str(parsed.get("category") or "")
    if category in CATEGORY_TAG:
        merged["category"] = category
    importance = str(parsed.get("importance") or "")
    if importance in {"low", "normal", "high"}:
        merged["importance"] = importance
    confidence = str(parsed.get("confidence") or "")
    if confidence in {"low", "medium", "high"}:
        merged["confidence"] = confidence
    merged["ai"] = True
    return merged


ANGLES = (
    ("news_short", "کوتاه و خبری"),
    ("formal", "رسمی و دقیق"),
    ("consult", "صمیمی و مشاوره‌ای"),
    ("points", "فهرست نکته"),
)


def pick_angle(recent: list[str]) -> tuple[str, str]:
    from backend.app.formatting.rotation import pick_avoiding_recent

    key = pick_avoiding_recent(tuple(item[0] for item in ANGLES), recent)
    return key, dict(ANGLES)[key]
