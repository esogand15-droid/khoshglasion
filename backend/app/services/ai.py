from __future__ import annotations

import hashlib
import logging
import time
from typing import Optional

import httpx

from backend.app.core.runtime import RuntimeState
from backend.app.services.ai_models import AIModel, configured_models
from backend.app.services.ai_provider import (
    build_headers,
    build_payload,
    extract_message_text,
    format_http_error,
    redact,
    resolve_chat_completions_url,
)
from backend.app.formatting.textutil import (
    clean_ai_output,
    looks_like_refusal,
    missing_long_numbers,
    missing_protected_tokens,
    restore_protected_tokens,
)
from backend.app.services.prompts import SYSTEM_PROMPT, wrap_post

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
    "lesson": "این متن آموزشی است. ساختار قابل اسکن بده و واقعیت علمی متن را عوض نکن.",
    "qa": "این متن پرسش و پاسخ است. سوال و جواب موجود را جابه‌جا یا عوض نکن.",
    "ad": "این متن تبلیغاتی است. شفاف بنویس و ادعای تازه نساز.",
    "general": "ساختار خوانا بده: تیتر کوتاه، بدنه، و در صورت نیاز بولت.",
}


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _record_output(text: str) -> None:
    _recent_hashes.append(_content_hash(text))
    opening = (text or "").strip().split("\n", 1)[0][:80]
    if opening:
        _recent_hashes.append("open:" + _content_hash(opening))
    del _recent_hashes[:-_MAX_HISTORY]


TIDY_HINT = (
    "این متن را بخوان و فقط چینش را خواناتر کن. "
    "تیتر را از خود متن بردار، لیست را اگر هست بولت کن، و بین بخش‌ها یک خط فاصله بگذار. "
    "جمله، عدد، اسم، تاریخ، قیمت و لینک را عوض نکن و جملهٔ تازه نساز. "
    "فوتر، خط ━ و دعوت عضویت را ننویس."
)


def build_messages(
    text: str,
    category: str,
    previous_context: str = "",
    extra_variation: bool = False,
    mode: str = "rewrite",
) -> list[dict]:
    hint = TIDY_HINT if mode == "tidy" else CATEGORY_HINTS.get(category, CATEGORY_HINTS["general"])
    user = f"{hint}\n\nمتن اصلی:\n{wrap_post(text)}"
    if previous_context and mode == "rewrite":
        user += f"\n\nبرای اینکه این پست شبیه پست قبلی نشود، فقط لحن و چینش را عوض کن. پست قبلی این بود:\n{previous_context[:280]}"
    if extra_variation and mode == "rewrite":
        user += "\n\nاین بار ساختار جمله‌ها را کاملاً متفاوت بچین، ولی واقعیت‌ها همان بماند."
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def accept_ai_output(original: str, raw: str | None, limit: int, required: list[str] | None = None) -> tuple[str | None, str]:
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
    for item in required or []:
        if item and item not in cleaned and f"«{item}»" not in cleaned:
            return None, "dropped_quote"
    missing = missing_protected_tokens(original, cleaned)
    if missing:
        cleaned = restore_protected_tokens(cleaned, missing)
        if len(cleaned) > limit:
            return None, "tokens_overflow"
    return cleaned, "ok"


def _spec(model: AIModel, messages: list[dict], *, health: bool = False, max_tokens: int | None = None) -> tuple[str, dict]:
    url = resolve_chat_completions_url(model.base_url)
    payload = build_payload(
        model.provider,
        model.model,
        messages,
        max_tokens=256 if health else max_tokens,
        health=health,
    )
    return url, {
        "provider": model.provider,
        "headers": build_headers(model.provider, model.api_key),
        "payload": payload,
    }


async def _post_model(model: AIModel, messages: list[dict], *, health: bool = False) -> tuple[str | None, str | None, str]:
    """One model. A high internal budget is only a retry if the gateway rejects the open call."""
    timeout = httpx.Timeout(20.0 if health else 40.0, connect=8.0)
    caps: list[int | None] = [None] if health else [None, 16384]
    last_error = "مدل پاسخ نداد"
    url = ""
    async with httpx.AsyncClient(timeout=timeout) as client:
        for cap in caps:
            url, spec = _spec(model, messages, health=health, max_tokens=cap)
            try:
                response = await client.post(url, json=spec["payload"], headers=spec["headers"])
            except httpx.TimeoutException:
                return None, "زمان مدل تمام شد", url
            except Exception as exc:
                return None, redact(f"{type(exc).__name__}", model.api_key), url
            if response.status_code == 400 and cap is None and not health:
                last_error = format_http_error(400, response.text, url, model.provider, model.api_key)
                continue
            if response.status_code >= 400:
                return None, format_http_error(response.status_code, response.text, url, model.provider, model.api_key), url
            try:
                text, _finish = extract_message_text(response.json())
            except Exception:
                return None, "پاسخ مدل خوانده نشد", url
            if text:
                return text, None, url
            last_error = "مدل پاسخ خالی داد"
            if health:
                return None, last_error, url
    return None, last_error, url


async def call_models(runtime: RuntimeState, messages: list[dict], *, health: bool = False) -> dict:
    models = configured_models(runtime)
    if not models:
        return {"ok": False, "error": "هیچ مدل کاملی در فهرست نیست", "attempts": [], "provider": "unconfigured", "model": "", "endpoint": ""}
    attempts = []
    for index, model in enumerate(models):
        text, error, url = await _post_model(model, messages, health=health)
        attempt = {
            "ok": bool(text),
            "provider": model.provider,
            "model": model.model,
            "endpoint": url,
            "error": error,
        }
        attempts.append(attempt)
        if text:
            return {
                "ok": True,
                "text": text,
                "provider": model.provider,
                "model": model.model,
                "endpoint": url,
                "fallback": index > 0,
                "attempts": attempts,
            }
        logger.info("AI model unavailable, next if any: %s %s", model.provider, model.model)
    last = attempts[-1]
    return {
        "ok": False,
        "text": None,
        "error": last.get("error") or "همهٔ مدل‌ها از دسترس خارج بودند",
        "provider": last.get("provider"),
        "model": last.get("model"),
        "endpoint": last.get("endpoint") or "",
        "fallback": False,
        "attempts": attempts,
    }


LAYOUTS = {"title", "scatter", "list", "closing"}


def parse_layout_token(raw: str | None) -> str | None:
    token = ((raw or "").strip().lower().split() or [""])[0].strip(".,:\"'`")
    return token if token in LAYOUTS else None


async def complete_text(runtime: RuntimeState, messages: list[dict]) -> str | None:
    if not runtime.ai_ready:
        return None
    result = await call_models(runtime, messages)
    return result.get("text") or None


async def pick_layout(text: str, runtime: RuntimeState) -> str | None:
    """Ask the model which decoration fits. Failure falls back to rotation."""
    if not runtime.ai_ready or not text or len(text.strip()) < 20:
        return None
    result = await call_models(
        runtime,
        [
            {
                "role": "system",
                "content": "فقط یکی از این کلمه‌ها را برگردان: title یا scatter یا list یا closing. توضیح ننویس.",
            },
            {"role": "user", "content": wrap_post(text[:1200])},
        ],
        health=True,
    )
    return parse_layout_token(result.get("text"))


async def edit_with_ai(
    text: str,
    category: str = "general",
    previous_context: str = "",
    runtime: RuntimeState | None = None,
    limit: int = 3600,
    required: list[str] | None = None,
    mode: str = "rewrite",
) -> tuple[str | None, str]:
    """Return the accepted text and a reason the caller can store on the log."""
    if runtime is None or not runtime.ai_ready:
        return None, "not_ready"
    if not text or not text.strip():
        return None, "too_short"
    if mode not in {"rewrite", "tidy"}:
        mode = "tidy"

    messages = build_messages(text, category, previous_context, mode=mode)
    varied = False
    last_reason = "empty"
    for model in configured_models(runtime):
        raw, error, _url = await _post_model(model, messages)
        if error or not raw:
            last_reason = "timeout" if error and "زمان" in error else "http_error"
            continue
        accepted, reason = accept_ai_output(text, raw, limit, required)
        opening = _content_hash((accepted or "").strip().split("\n", 1)[0][:80]) if accepted else ""
        repeated = bool(accepted) and (_content_hash(accepted) in _recent_hashes or f"open:{opening}" in _recent_hashes)
        if repeated and mode == "rewrite" and not varied:
            varied = True
            logger.info("AI output repeated a recent post; retrying once")
            raw, error, _url = await _post_model(model, build_messages(text, category, previous_context, extra_variation=True, mode=mode))
            if raw and not error:
                accepted, reason = accept_ai_output(text, raw, limit, required)
        if accepted:
            _record_output(accepted)
            logger.info("AI enhanced category=%s mode=%s len=%s model=%s", category, mode, len(accepted), model.model)
            return accepted, "ok"
        last_reason = reason
        logger.info("AI output rejected by %s: %s", model.model, reason)
    return None, last_reason


async def enhance_with_ai(
    text: str,
    category: str = "general",
    previous_context: str = "",
    runtime: RuntimeState | None = None,
    limit: int = 3600,
    required: list[str] | None = None,
    mode: str = "rewrite",
) -> Optional[str]:
    accepted, _reason = await edit_with_ai(
        text,
        category,
        previous_context,
        runtime=runtime,
        limit=limit,
        required=required,
        mode=mode,
    )
    return accepted


async def test_ai_connection(runtime: RuntimeState) -> dict:
    models = configured_models(runtime)
    provider = models[0].provider if models else "unconfigured"
    model_name = models[0].model if models else getattr(runtime, "ai_model", "")
    if not models:
        return {
            "ok": False,
            "provider": provider,
            "model": model_name,
            "endpoint": "",
            "error": "هیچ مدل کاملی در فهرست نیست",
            "attempts": [],
        }
    started = time.perf_counter()
    result = await call_models(runtime, [{"role": "user", "content": "فقط همین کلمه را برگردان: سلام"}], health=True)
    latency = round((time.perf_counter() - started) * 1000)
    result["latency_ms"] = latency
    result["sample"] = (result.get("text") or "")[:80]
    result.pop("text", None)
    if not result.get("ok") and not result.get("error"):
        result["error"] = "همهٔ مدل‌ها از دسترس خارج بودند"
    return result
