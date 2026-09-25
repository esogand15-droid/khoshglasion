"""One reading of a collected post: text and photo together.

The channel name and a hashtag already on the message are not the decision.
A short joke is not news. A shop banner is not a draft.
"""
from __future__ import annotations

from backend.app.content.intake import promotion_reason
from backend.app.services.finetune import classify_style, hard_news

_AD_NOTE = ("تبلیغ", "تخفیف", "بنر فروش", "سفارش", "دایرکت", "عضو کانال", "کد تخفیف")
_FUN_NOTE = ("میم", "شوخی", "طنز", "خنده", "meme", "فان")


def image_kind(note: str) -> str:
    text = (note or "").strip()
    if not text:
        return ""
    first = text.splitlines()[0].strip().upper()
    if first in {"AD", "FUN", "NEWS", "OTHER"}:
        return first
    folded = text.replace("ي", "ی").replace("ك", "ک")
    if any(word in folded for word in _AD_NOTE):
        return "AD"
    if any(word in folded for word in _FUN_NOTE):
        return "FUN"
    return ""


def image_ad_reason(note: str, caption: str) -> str | None:
    if image_kind(note) != "AD":
        return None
    first = (note or "").strip().splitlines()[0].strip().upper()
    # A tuition notice can mention تخفیف. Only an explicit AD line overrides that.
    if hard_news(caption) and first != "AD":
        return None
    return "عکس تبلیغ، بنر فروش یا جذب عضو است"


def blend_style(text: str, image_note: str, parsed: dict | None) -> tuple[str, str | None, str]:
    """Return style folder, ad reason, and tone.

    A local ad is refused without waiting for the model. A low-confidence
    model ad is not refused here; the caller can flag it for review.
    """
    local = classify_style(text, image_note)
    ad = promotion_reason(text + "\n" + (image_note or "")) or image_ad_reason(image_note, text)
    if ad:
        return local, ad, "serious"
    tone = "humorous" if local == "fun" else "serious" if local in {"flash", "announce", "alert"} else "friendly"
    if not parsed:
        return local, None, tone
    confidence = str(parsed.get("confidence") or "")
    flagged = parsed.get("is_advertisement") in (True, "true", "True", 1)
    if flagged and confidence in {"medium", "high"}:
        reason = str(parsed.get("ad_reason") or "مدل این پست را تبلیغ تشخیص داد").strip()[:180]
        return local, reason or "مدل این پست را تبلیغ تشخیص داد", "serious"
    model_tone = str(parsed.get("tone") or "")
    if model_tone in {"serious", "friendly", "humorous"}:
        tone = model_tone
    if local == "fun" and not (confidence == "high" and hard_news(text)):
        return "fun", None, "humorous" if tone == "serious" else tone
    if tone == "humorous" and not hard_news(text):
        return "fun", None, "humorous"
    return local, None, tone


def review_ad(parsed: dict | None, refused: str | None) -> bool:
    """True when the model suspects an ad but not strongly enough to drop it."""
    if refused or not parsed:
        return False
    flagged = parsed.get("is_advertisement") in (True, "true", "True", 1)
    return flagged and str(parsed.get("confidence") or "") == "low"
