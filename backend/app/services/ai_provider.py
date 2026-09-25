"""OpenAI-compatible provider adapter.

Business code must not guess the final URL. NVIDIA, OpenRouter, Groq and
Ollama document a base URL that already ends in ``/v1``. The OpenAI SDK then
posts to ``{base}/chat/completions``. This project used to always append
``/v1/chat/completions``, so a saved NVIDIA URL became
``https://integrate.api.nvidia.com/v1/v1/chat/completions`` and the gateway
answered ``404 page not found``.
"""
from __future__ import annotations

from urllib.parse import urlparse

CHAT_SUFFIX = "/chat/completions"


def detect_provider(base_url: str | None) -> str:
    host = (urlparse(base_url or "").netloc or "").lower()
    blob = f"{host} {(base_url or '').lower()}"
    if "integrate.api.nvidia.com" in blob or host.endswith("nvidia.com"):
        return "nvidia"
    if "openrouter.ai" in host:
        return "openrouter"
    if "api.openai.com" in host:
        return "openai"
    if "groq.com" in host:
        return "groq"
    if "11434" in blob or "ollama" in blob:
        return "ollama"
    if "9router" in blob or "ninerouter" in blob:
        return "ninerouter"
    if not (base_url or "").strip():
        return "unconfigured"
    return "openai-compatible"


def resolve_chat_completions_url(base_url: str | None) -> str:
    """Return the chat-completions URL without doubling ``/v1``."""
    raw = (base_url or "").strip()
    if not raw:
        raise ValueError("AI base URL is empty")
    raw = raw.rstrip("/")
    lowered = raw.lower()
    if lowered.endswith(CHAT_SUFFIX):
        return raw
    path = urlparse(raw).path.rstrip("/")
    if path.endswith("/v1"):
        return raw + CHAT_SUFFIX
    return raw + "/v1" + CHAT_SUFFIX


def build_headers(provider: str, api_key: str) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://khoshgelasion.local"
        headers["X-Title"] = "Khoshgelasion"
    return headers


def build_payload(
    provider: str,
    model: str,
    messages: list[dict],
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    health: bool = False,
) -> dict:
    """Real calls do not send a temperature or token ceiling.

    A health probe still asks for a short answer so the test button returns.
    Provider defaults decide the real completion. Penalties are not sent:
    they narrow the model on purpose.
    """
    payload: dict = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    if health:
        payload["temperature"] = 0
        payload["max_tokens"] = 256
        return payload
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens:
        payload["max_tokens"] = int(max_tokens)
    return payload


def extract_message_text(data: dict) -> tuple[str, str | None]:
    choice = (data.get("choices") or [{}])[0] or {}
    message = choice.get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(str(part.get("text") or part.get("content") or ""))
        content = "".join(parts)
    text = (content or "").strip() if isinstance(content, str) else ""
    if not text:
        text = str(message.get("reasoning_content") or message.get("reasoning") or "").strip()
    return text, choice.get("finish_reason")


def redact(text: str, secret: str | None) -> str:
    cleaned = (text or "").replace("\n", " ").strip()
    if secret and secret in cleaned:
        cleaned = cleaned.replace(secret, "***")
    return cleaned[:240]


def format_http_error(status: int, body: str, url: str, provider: str, secret: str | None = None) -> str:
    snippet = redact(body, secret)
    if status == 404:
        return (
            f"HTTP 404 از {provider}. درخواست به {url} رفت و این مسیر وجود ندارد. "
            "Base URL را همان مقدار مستند provider بگذار؛ برای NVIDIA دقیقاً "
            "https://integrate.api.nvidia.com/v1 کافی است و /chat/completions را خود سیستم اضافه می‌کند. "
            f"پاسخ: {snippet or '404 page not found'}"
        )
    if status in {401, 403}:
        return f"HTTP {status}: کلید API رد شد. کلید در پاسخ و لاگ چاپ نمی‌شود."
    if status == 429:
        return "HTTP 429: سقف درخواست provider پر شده. کمی بعد دوباره تست کن."
    if status == 400:
        return f"HTTP 400: مدل یا پارامتر با این provider نمی‌خواند. {snippet}"
    return f"HTTP {status}: {snippet or 'بدون متن خطا'}"
