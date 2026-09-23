from __future__ import annotations

import hashlib
import logging
import time
from typing import Optional

import httpx

from backend.app.core.runtime import RuntimeState
from backend.app.services.ai_provider import (
    build_headers,
    build_payload,
    detect_provider,
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
from backend.app.services.retry import retry_wait_seconds, should_retry_status

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


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _record_output(text: str) -> None:
    _recent_hashes.append(_content_hash(text))
    opening = (text or "").strip().split("\n", 1)[0][:80]
    if opening:
        _recent_hashes.append("open:" + _content_hash(opening))
    del _recent_hashes[:-_MAX_HISTORY]


def build_messages(text: str, category: str, previous_context: str = "", extra_variation: bool = False) -> list[dict]:
    hint = CATEGORY_HINTS.get(category, CATEGORY_HINTS["general"])
    user = f"{hint}\n\nمتن اصلی:\n{wrap_post(text)}"
    if previous_context:
        user += f"\n\nبرای اینکه این پست شبیه پست قبلی نشود، فقط لحن و چینش را عوض کن. پست قبلی این بود:\n{previous_context[:280]}"
    if extra_variation:
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


def _provider_call(runtime: RuntimeState, messages: list[dict], temperature: float, *, health: bool = False) -> tuple[str, dict]:
    provider = detect_provider(runtime.ai_base_url)
    url = resolve_chat_completions_url(runtime.ai_base_url)
    payload = build_payload(
        provider,
        runtime.ai_model,
        messages,
        temperature=temperature,
        max_tokens=runtime.ai_max_tokens,
        health=health,
    )
    return url, {
        "provider": provider,
        "headers": build_headers(provider, runtime.ai_api_key),
        "payload": payload,
    }


async def _call_model(runtime: RuntimeState, messages: list[dict], temperature: float) -> str | None:
    url, spec = _provider_call(runtime, messages, temperature)
    timeout = httpx.Timeout(45.0, connect=10.0)
    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(3):
            try:
                response = await client.post(url, json=spec["payload"], headers=spec["headers"])
            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt == 2:
                    raise
                await _sleep_retry(attempt, None)
                continue
            if response.status_code >= 400:
                if should_retry_status(response.status_code) and attempt < 2:
                    hinted = response.headers.get("retry-after")
                    await _sleep_retry(attempt, hinted)
                    continue
                raise httpx.HTTPStatusError(
                    format_http_error(response.status_code, response.text, url, spec["provider"], runtime.ai_api_key),
                    request=response.request,
                    response=response,
                )
            text, _reason = extract_message_text(response.json())
            return text
    if last_error:
        raise last_error
    return None


async def _sleep_retry(attempt: int, retry_after: str | None) -> None:
    import asyncio
    wait = retry_wait_seconds(attempt, float(retry_after) if retry_after and retry_after.replace(".", "", 1).isdigit() else None)
    logger.info("AI provider blip, retrying in %.1fs", wait)
    await asyncio.sleep(wait)


async def enhance_with_ai(
    text: str,
    category: str = "general",
    previous_context: str = "",
    runtime: RuntimeState | None = None,
    limit: int = 3600,
    required: list[str] | None = None,
) -> Optional[str]:
    if runtime is None or not runtime.ai_ready:
        return None
    if not text or len(text.strip()) < runtime.ai_min_chars:
        return None

    messages = build_messages(text, category, previous_context)
    try:
        raw = await _call_model(runtime, messages, runtime.ai_temperature)
        accepted, reason = accept_ai_output(text, raw, limit, required)
        opening = _content_hash((accepted or "").strip().split("\n", 1)[0][:80]) if accepted else ""
        repeated = bool(accepted) and (_content_hash(accepted) in _recent_hashes or f"open:{opening}" in _recent_hashes)
        if repeated:
            logger.info("AI output repeated a recent post; retrying once")
            messages = build_messages(text, category, previous_context, extra_variation=True)
            raw = await _call_model(runtime, messages, min(0.95, runtime.ai_temperature + 0.15))
            accepted, reason = accept_ai_output(text, raw, limit, required)
        if not accepted:
            logger.info("AI output rejected: %s", reason)
            return None
        _record_output(accepted)
        logger.info("AI enhanced category=%s len=%s", category, len(accepted))
        return accepted
    except httpx.HTTPStatusError as exc:
        logger.error("AI API error %s", redact(str(exc), runtime.ai_api_key if runtime else None))
    except httpx.TimeoutException:
        logger.error("AI request timed out")
    except Exception as exc:
        logger.error("AI call failed: %s: %s", type(exc).__name__, exc)
    return None


async def test_ai_connection(runtime: RuntimeState) -> dict:
    provider = detect_provider(runtime.ai_base_url)
    if not runtime.ai_ready:
        return {
            "ok": False,
            "provider": provider,
            "model": runtime.ai_model,
            "endpoint": "",
            "error": "AI کامل تنظیم نشده (آدرس، مدل یا کلید)",
        }
    try:
        url = resolve_chat_completions_url(runtime.ai_base_url)
    except ValueError as exc:
        return {"ok": False, "provider": provider, "model": runtime.ai_model, "endpoint": "", "error": str(exc)}
    messages = [{"role": "user", "content": "فقط همین کلمه را برگردان: سلام"}]
    spec_url, spec = _provider_call(runtime, messages, 0.2, health=True)
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            response = await client.post(spec_url, json=spec["payload"], headers=spec["headers"])
        latency = round((time.perf_counter() - started) * 1000)
        if response.status_code != 200:
            return {
                "ok": False,
                "provider": provider,
                "model": runtime.ai_model,
                "endpoint": url,
                "status_code": response.status_code,
                "latency_ms": latency,
                "error": format_http_error(response.status_code, response.text, url, provider, runtime.ai_api_key),
            }
        text, finish = extract_message_text(response.json())
        if not text:
            return {
                "ok": False,
                "provider": provider,
                "model": runtime.ai_model,
                "endpoint": url,
                "status_code": 200,
                "latency_ms": latency,
                "finish_reason": finish,
                "error": "مدل پاسخ خالی داد. اگر مدل reasoning است، سقف توکن را بالاتر ببر.",
            }
        return {
            "ok": True,
            "provider": provider,
            "model": runtime.ai_model,
            "endpoint": url,
            "status_code": 200,
            "latency_ms": latency,
            "finish_reason": finish,
            "sample": text[:80],
        }
    except Exception as exc:
        return {
            "ok": False,
            "provider": provider,
            "model": runtime.ai_model,
            "endpoint": url,
            "error": redact(str(exc), runtime.ai_api_key),
        }
