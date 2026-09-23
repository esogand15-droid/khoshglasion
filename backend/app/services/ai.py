from __future__ import annotations

import hashlib
import logging
from typing import Optional

import httpx

from backend.app.core.runtime import RuntimeState
from backend.app.formatting.textutil import (
    clean_ai_output,
    looks_like_refusal,
    missing_long_numbers,
    missing_protected_tokens,
    restore_protected_tokens,
)

logger = logging.getLogger(__name__)

_recent_hashes: list[str] = []
_MAX_HISTORY = 40

CATEGORY_HINTS = {
    "announcement": "این متن اطلاعیه است. تیتر واضح، لحن معتبر و صمیمی، و اگر اقدام لازم است همان را برجسته کن.",
    "exam": "این متن درباره آزمون یا تست است. نکته کاربردی را جدا کن و لحن را مشوق اما دقیق نگه دار.",
    "resource": "این متن معرفی منبع است. بگو برای چه سطحی مناسب است، بدون لحن فروشنده.",
    "motivational": "این متن انگیزشی است. واقعی و کنکوری بنویس، نه شعار اینستاگرامی.",
    "consulting": "این متن مشاوره‌ای است. مسئله را روشن کن و اگر راهکار در متن هست، قدم‌به‌قدم و کوتاه بچین.",
    "news": "این متن خبری است. واقعیت را دقیق نگه دار و اثرش روی داوطلب را فقط اگر در خود متن هست بگو.",
    "planning": "این متن برنامه‌ریزی است. ساختار قابل اسکن بده، بدون اختراع برنامه جدید.",
    "rank": "این متن درباره رتبه یا نتیجه است. امید واقعی بده و آمار را دست نزن.",
    "discount": "این متن پیشنهاد یا تخفیف است. شفاف بنویس، فشار فروش نساز.",
    "general": "ساختار خوانا بده: تیتر کوتاه، بدنه، و در صورت نیاز بولت.",
}

SYSTEM_PROMPT = """تو ویراستار کانال تلگرام «رتبه لند» هستی؛ کانال مشاوره کنکور.
متن ادمین را خوشگل، خوانا و طبیعی کن. واقعیت را عوض نکن.

قانون‌های سخت:
- عدد، تاریخ، درصد، قیمت، اسم شخص، اسم کتاب، لینک، @یوزرنیم و هشتگ را حذف یا عوض نکن.
- ادعا، خبر یا توصیهٔ تازه اختراع نکن. اگر متن کوتاه است، زیادش نکن.
- لحن: صمیمی، دقیق، کنکوری. کلیشه و شعار توخالی ننویس.
- ایموجی یونیکد را فقط در تیتر و چند نقطهٔ کلیدی بگذار، نه ته هر خط.
- فوتر کانال، خط ━ و دعوت عضویت را ننویس؛ سیستم جدا اضافه می‌کند.
- فقط متن نهایی را برگردان. توضیح، مارک‌داون کد و پیشوند «بازنویسی» ممنوع.
- از الگوهای تکراری پست‌های قبلی فاصله بگیر، ولی معنی این پست را حفظ کن."""


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _record_output(text: str) -> None:
    _recent_hashes.append(_content_hash(text))
    del _recent_hashes[:-_MAX_HISTORY]


def build_messages(text: str, category: str, previous_context: str = "", extra_variation: bool = False) -> list[dict]:
    hint = CATEGORY_HINTS.get(category, CATEGORY_HINTS["general"])
    user = f"{hint}\n\nمتن اصلی:\n{text}"
    if previous_context:
        user += f"\n\nبرای اینکه این پست شبیه پست قبلی نشود، فقط لحن و چینش را عوض کن. پست قبلی این بود:\n{previous_context[:280]}"
    if extra_variation:
        user += "\n\nاین بار ساختار جمله‌ها را کاملاً متفاوت بچین، ولی واقعیت‌ها همان بماند."
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def accept_ai_output(original: str, raw: str | None, limit: int) -> tuple[str | None, str]:
    cleaned = clean_ai_output(raw)
    if not cleaned or len(cleaned) < 8:
        return None, "empty"
    if looks_like_refusal(cleaned):
        return None, "refusal"
    if len(cleaned) > limit:
        return None, "too_long"
    if len(original) > 120 and len(cleaned) < int(len(original) * 0.35):
        return None, "too_short"
    if missing_long_numbers(original, cleaned):
        return None, "dropped_numbers"
    missing = missing_protected_tokens(original, cleaned)
    if missing:
        cleaned = restore_protected_tokens(cleaned, missing)
        if len(cleaned) > limit:
            return None, "tokens_overflow"
    return cleaned, "ok"


async def _call_model(runtime: RuntimeState, messages: list[dict], temperature: float) -> str | None:
    headers = {
        "Authorization": f"Bearer {runtime.ai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": runtime.ai_model,
        "messages": messages,
        "temperature": temperature,
        "top_p": 0.9,
        "max_tokens": runtime.ai_max_tokens,
        "presence_penalty": 0.4,
        "frequency_penalty": 0.2,
    }
    url = runtime.ai_base_url.rstrip("/") + "/v1/chat/completions"
    timeout = httpx.Timeout(40.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")


async def enhance_with_ai(
    text: str,
    category: str = "general",
    previous_context: str = "",
    runtime: RuntimeState | None = None,
    limit: int = 3600,
) -> Optional[str]:
    if runtime is None or not runtime.ai_ready:
        return None
    if not text or len(text.strip()) < runtime.ai_min_chars:
        return None

    messages = build_messages(text, category, previous_context)
    try:
        raw = await _call_model(runtime, messages, runtime.ai_temperature)
        accepted, reason = accept_ai_output(text, raw, limit)
        if accepted and _content_hash(accepted) in _recent_hashes:
            logger.info("AI output repeated a recent post; retrying once")
            messages = build_messages(text, category, previous_context, extra_variation=True)
            raw = await _call_model(runtime, messages, min(0.95, runtime.ai_temperature + 0.15))
            accepted, reason = accept_ai_output(text, raw, limit)
        if not accepted:
            logger.info("AI output rejected: %s", reason)
            return None
        _record_output(accepted)
        logger.info("AI enhanced category=%s len=%s", category, len(accepted))
        return accepted
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:180].replace("\n", " ")
        logger.error("AI API error %s: %s", exc.response.status_code, body)
    except httpx.TimeoutException:
        logger.error("AI request timed out")
    except Exception as exc:
        logger.error("AI call failed: %s: %s", type(exc).__name__, exc)
    return None


async def test_ai_connection(runtime: RuntimeState) -> dict:
    if not runtime.ai_ready:
        return {"ok": False, "error": "AI کامل تنظیم نشده (آدرس، مدل یا کلید)"}
    headers = {"Authorization": f"Bearer {runtime.ai_api_key}", "Content-Type": "application/json"}
    payload = {
        "model": runtime.ai_model,
        "messages": [{"role": "user", "content": "فقط همین کلمه را برگردان: سلام"}],
        "max_tokens": 16,
        "temperature": 0,
    }
    url = runtime.ai_base_url.rstrip("/") + "/v1/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                return {"ok": True, "model": runtime.ai_model}
            return {"ok": False, "error": f"HTTP {response.status_code}: {response.text[:180]}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
