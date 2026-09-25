"""Text helpers shared by the formatter and the AI guard."""
from __future__ import annotations

import re

ARABIC_TO_PERSIAN = str.maketrans({
    "ي": "ی",
    "ك": "ک",
    "ى": "ی",
    "ة": "ه",
    "٠": "۰",
    "١": "۱",
    "٢": "۲",
    "٣": "۳",
    "٤": "۴",
    "٥": "۵",
    "٦": "۶",
    "٧": "۷",
    "٨": "۸",
    "٩": "۹",
})
PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
MENTION_RE = re.compile(r"@[A-Za-z0-9_]{3,}")
HASHTAG_RE = re.compile(r"#[\w\u0600-\u06FF]+", re.UNICODE)
FENCE_RE = re.compile(r"^```[a-zA-Z0-9_-]*\n?|```$", re.MULTILINE)
LEADING_LABELS = (
    "متن نهایی:",
    "متن بازنویسی‌شده:",
    "متن بازنویسی شده:",
    "بازنویسی:",
    "خروجی:",
    "نتیجه:",
)


def utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def utf16_slice(text: str, offset: int, length: int) -> str:
    raw = text.encode("utf-16-le")
    start = max(0, offset) * 2
    end = max(0, offset + length) * 2
    return raw[start:end].decode("utf-16-le", errors="ignore")


def normalize_persian(text: str) -> str:
    text = text.translate(ARABIC_TO_PERSIAN)
    text = text.replace("ـ", "")
    text = text.replace("\u200c\u200c", "\u200c")
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" +([،.!?؟:؛])", r"\1", text)
    return text


def normalize_digits(text: str) -> str:
    return text.translate(PERSIAN_DIGITS)


def extract_protected_tokens(text: str) -> list[str]:
    found: list[str] = []
    for regex in (URL_RE, MENTION_RE, HASHTAG_RE):
        for match in regex.findall(text or ""):
            token = match.rstrip(".,،؛)]}")
            if token and token not in found:
                found.append(token)
    return found


def missing_protected_tokens(original: str, output: str) -> list[str]:
    out = output or ""
    return [token for token in extract_protected_tokens(original) if token not in out]


def restore_protected_tokens(output: str, missing: list[str]) -> str:
    if not missing:
        return output
    return output.rstrip() + "\n\n" + "\n".join(missing)


def missing_long_numbers(original: str, output: str) -> list[str]:
    source = set(re.findall(r"\d{3,}", normalize_digits(original or "")))
    target = normalize_digits(output or "")
    return sorted(num for num in source if num not in target)


def clean_ai_output(raw: str | None) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    text = FENCE_RE.sub("", text).strip()
    for label in LEADING_LABELS:
        if text.startswith(label):
            text = text[len(label):].strip()
    if (text.startswith("«") and text.endswith("»")) or (text.startswith('"') and text.endswith('"')):
        text = text[1:-1].strip()
    # Drop a trailing explanation the model sometimes adds.
    text = re.split(r"\n{1,}(?:توضیح|نکته ویرایشی|note)\s*[:：]", text, maxsplit=1, flags=re.IGNORECASE)[0]
    return text.strip()


def looks_like_refusal(text: str) -> bool:
    lowered = (text or "").strip().lower()
    needles = (
        "can't assist",
        "cannot assist",
        "i can't",
        "as an ai",
        "نمی‌توانم این متن را",
        "نمیتوانم این متن را",
    )
    return any(n in lowered for n in needles)


def strip_footer_block(text: str, footer: str | None, divider: str | None = None) -> str:
    if not text:
        return text
    cleaned = text.rstrip()
    if footer and footer.strip() and footer.strip() in cleaned:
        cleaned = cleaned.replace(footer.strip(), "").rstrip()
    if divider and divider.strip():
        cleaned = re.sub(rf"(?:\n*{re.escape(divider.strip())})+\s*$", "", cleaned).rstrip()
    return cleaned.strip()
