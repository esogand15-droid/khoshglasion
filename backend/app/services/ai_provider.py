"""OpenAI-compatible provider adapter.

Business code must not guess the final URL. A saved base is the prefix a
provider documents for an OpenAI client, not the full chat path. NVIDIA ends
in ``/v1``. Gemini's OpenAI-compatible base ends in ``/v1beta/openai`` and
must not grow another ``/v1``. Groq ends in ``/openai/v1``. GLM's coding
transport ends in ``/v4``.

The catalog bases and model-list URLs come from the 9router provider registry
(decolua/9router, open-sse/providers/registry) plus the provider's own
OpenAI-compatible path where 9router speaks a native format instead.
"""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

import httpx

CHAT_SUFFIX = "/chat/completions"
MODEL_CAP = 200
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "host.docker.internal"}
_NON_CHAT = (
    "embed",
    "whisper",
    "tts",
    "transcri",
    "dall-e",
    "imagen",
    "flux",
    "veo",
    "sora",
    "rerank",
    "moderation",
    "audio",
    "speech",
    "aqa",
    "-image",
    "/image",
)


# Paste-ready bases. ``models_url`` is set only when it is not ``{base}/models``.
# Hints are for the admin panel. No secrets belong in this table.
_CATALOG = (
    {
        "id": "nvidia",
        "label": "NVIDIA",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "models_url": "https://integrate.api.nvidia.com/v1/models",
        "key_url": "https://build.nvidia.com/settings/api-keys",
        "hint": "همین آدرس کافی است. مسیر chat/completions را ننویس.",
    },
    {
        "id": "gemini",
        "label": "Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "models_url": "https://generativelanguage.googleapis.com/v1beta/openai/models",
        "key_url": "https://aistudio.google.com/app/apikey",
        "hint": "بعد از openai یک /v1 نگذار. کلید AI Studio با Bearer می‌رود. 9router مسیر بومی /v1beta/models را با هدر x-goog-api-key می‌زند؛ این پنل مسیر سازگار با OpenAI را می‌زند.",
    },
    {
        "id": "openai",
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models_url": "https://api.openai.com/v1/models",
        "key_url": "https://platform.openai.com/api-keys",
        "hint": "آدرس پایه تا /v1 است.",
    },
    {
        "id": "openrouter",
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "models_url": "https://openrouter.ai/api/v1/models",
        "key_url": "https://openrouter.ai/settings/keys",
        "hint": "یک کلید، چند مدل. تشخیص خودکار فهرست زنده را می‌آورد.",
    },
    {
        "id": "groq",
        "label": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "models_url": "https://api.groq.com/openai/v1/models",
        "key_url": "https://console.groq.com/keys",
        "hint": "مسیر openai/v1 است، نه /v1 تنها.",
    },
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "models_url": "https://api.deepseek.com/models",
        "key_url": "https://platform.deepseek.com/api_keys",
        "hint": "9router مستقیم به /chat/completions می‌زند. DeepSeek هم آن را می‌پذیرد هم /v1. این پنل /v1 را نگه می‌دارد.",
    },
    {
        "id": "together",
        "label": "Together",
        "base_url": "https://api.together.xyz/v1",
        "models_url": "https://api.together.xyz/v1/models",
        "key_url": "https://api.together.xyz/settings/api-keys",
        "hint": "آدرس پایه تا /v1 است.",
    },
    {
        "id": "fireworks",
        "label": "Fireworks",
        "base_url": "https://api.fireworks.ai/inference/v1",
        "models_url": "https://api.fireworks.ai/inference/v1/models",
        "key_url": "https://fireworks.ai/account/api-keys",
        "hint": "inference/v1 را حذف نکن.",
    },
    {
        "id": "mistral",
        "label": "Mistral",
        "base_url": "https://api.mistral.ai/v1",
        "models_url": "https://api.mistral.ai/v1/models",
        "key_url": "https://console.mistral.ai/api-keys",
        "hint": "آدرس پایه تا /v1 است.",
    },
    {
        "id": "xai",
        "label": "xAI",
        "base_url": "https://api.x.ai/v1",
        "models_url": "https://api.x.ai/v1/models",
        "key_url": "https://console.x.ai",
        "hint": "آدرس پایه تا /v1 است.",
    },
    {
        "id": "cerebras",
        "label": "Cerebras",
        "base_url": "https://api.cerebras.ai/v1",
        "models_url": "https://api.cerebras.ai/v1/models",
        "key_url": "https://cloud.cerebras.ai/platform",
        "hint": "آدرس پایه تا /v1 است.",
    },
    {
        "id": "siliconflow",
        "label": "SiliconFlow",
        "base_url": "https://api.siliconflow.com/v1",
        "models_url": "https://api.siliconflow.com/v1/models",
        "key_url": "https://cloud.siliconflow.com/account/ak",
        "hint": "آدرس پایه تا /v1 است.",
    },
    {
        "id": "kimi",
        "label": "Kimi",
        "base_url": "https://api.kimi.com/coding/v1",
        "models_url": "https://api.kimi.com/coding/v1/models",
        "key_url": "https://platform.moonshot.ai/console/api-keys",
        "hint": "این مسیر coding/v1 در 9router است. اگر کلید Moonshot است، ارائه‌دهنده Moonshot را انتخاب کن.",
    },
    {
        "id": "moonshot",
        "label": "Moonshot",
        "base_url": "https://api.moonshot.cn/v1",
        "models_url": "https://api.moonshot.cn/v1/models",
        "key_url": "https://platform.moonshot.ai/console/api-keys",
        "hint": "9router برای چت Moonshot همین /v1 را دارد. اگر این میزبان کلیدت را نپذیرفت، آدرس را دستی عوض کن و دوباره تشخیص بزن.",
    },
    {
        "id": "glm",
        "label": "GLM",
        "base_url": "https://api.z.ai/api/coding/paas/v4",
        "models_url": "https://api.z.ai/api/coding/paas/v4/models",
        "key_url": "https://open.bigmodel.cn/usercenter/apikeys",
        "hint": "مسیر کدینگ 9router تا v4 است. /v1 اضافه نکن.",
    },
    {
        "id": "ollama",
        "label": "Ollama Cloud",
        "base_url": "https://ollama.com/v1",
        "models_url": "https://ollama.com/v1/models",
        "key_url": "https://ollama.com/settings/keys",
        "hint": "لایه OpenAI روی /v1 است، نه /api/v1. 9router برای چت بومی /api/chat می‌زند.",
    },
    {
        "id": "ollama-local",
        "label": "Ollama",
        "base_url": "http://127.0.0.1:11434/v1",
        "models_url": "http://127.0.0.1:11434/v1/models",
        "key_url": "",
        "hint": "اگر کلید نخواست، خالی بگذار. فقط روی همین دستگاه.",
    },
    {
        "id": "ninerouter",
        "label": "9router",
        "base_url": "http://127.0.0.1:20128/v1",
        "models_url": "http://127.0.0.1:20128/v1/models",
        "key_url": "https://github.com/decolua/9router",
        "hint": "9router باید روی همین دستگاه روشن باشد. این آدرس API است، نه داشبورد.",
    },
)


def provider_catalog() -> list[dict]:
    rows = []
    for item in _CATALOG:
        rows.append({
            "id": item["id"],
            "label": item["label"],
            "base_url": item["base_url"],
            "models_url": item["models_url"],
            "endpoint": resolve_chat_completions_url(item["base_url"]),
            "key_url": item["key_url"],
            "hint": item["hint"],
        })
    return rows


def _preset(provider_id: str) -> dict | None:
    for item in _CATALOG:
        if item["id"] == provider_id:
            return item
    return None


def _host_key(host: str) -> str:
    cleaned = (host or "").lower().strip("[]")
    if cleaned in {"localhost", "::1"}:
        return "127.0.0.1"
    return cleaned


def _parsed(url: str):
    return urlparse((url or "").strip())


def detect_provider(base_url: str | None) -> str:
    parsed = _parsed(base_url or "")
    host = (parsed.hostname or "").lower()
    blob = f"{host} {(base_url or '').lower()}"
    port = parsed.port
    if "generativelanguage.googleapis.com" in blob:
        return "gemini"
    if "integrate.api.nvidia.com" in blob or host.endswith("nvidia.com"):
        return "nvidia"
    if host == "openrouter.ai" or host.endswith(".openrouter.ai"):
        return "openrouter"
    if host == "api.openai.com":
        return "openai"
    if "groq.com" in host:
        return "groq"
    if "deepseek.com" in host:
        return "deepseek"
    if "together.xyz" in host or "together.ai" in host:
        return "together"
    if "fireworks.ai" in host:
        return "fireworks"
    if "mistral.ai" in host:
        return "mistral"
    if host == "api.x.ai" or host.endswith(".x.ai"):
        return "xai"
    if "cerebras.ai" in host:
        return "cerebras"
    if "siliconflow.com" in host or "siliconflow.cn" in host:
        return "siliconflow"
    if host == "api.kimi.com":
        return "kimi"
    if "moonshot.cn" in host or "moonshot.ai" in host:
        return "moonshot"
    if host == "api.z.ai" or "bigmodel.cn" in host:
        return "glm"
    if host == "ollama.com":
        return "ollama"
    if port == 11434 or (host in _LOCAL_HOSTS and "11434" in blob):
        return "ollama-local"
    if port == 20128 or "9router" in blob or "ninerouter" in blob:
        return "ninerouter"
    if "11434" in blob or "ollama" in blob:
        return "ollama"
    if not (base_url or "").strip():
        return "unconfigured"
    return "openai-compatible"


def _strip_known_suffix(raw: str) -> str:
    text = (raw or "").strip().rstrip("/")
    lowered = text.lower()
    for suffix in ("/chat/completions", "/models", "/completions"):
        if lowered.endswith(suffix):
            text = text[: -len(suffix)].rstrip("/")
            lowered = text.lower()
    if lowered.endswith("/v1/v1"):
        text = text[:-3]
    return text


def _versioned_base(path: str) -> bool:
    cleaned = (path or "").rstrip("/").lower()
    if not cleaned:
        return False
    if cleaned.endswith(("/v1", "/openai", "/openai/v1", "/v1beta/openai")):
        return True
    return bool(re.search(r"/v\d+$", cleaned))


def _ports_match(left, right) -> bool:
    if left == right:
        return True
    return left in (None, 80, 443) and right in (None, 80, 443)


def _preset_for(base_url: str) -> dict | None:
    parsed = _parsed(_strip_known_suffix(base_url))
    host = _host_key(parsed.hostname or "")
    if not host:
        return None
    if host == "generativelanguage.googleapis.com":
        return _preset("gemini")
    if host == "ollama.com":
        return _preset("ollama")
    if parsed.port == 11434 and host in {"127.0.0.1", "host.docker.internal"}:
        return _preset("ollama-local")
    if parsed.port == 20128 and host == "127.0.0.1":
        return _preset("ninerouter")
    matches = []
    for item in _CATALOG:
        other = _parsed(item["base_url"])
        if _host_key(other.hostname or "") != host:
            continue
        if not _ports_match(parsed.port, other.port):
            continue
        matches.append(item)
    if len(matches) == 1:
        path = (parsed.path or "").rstrip("/").lower()
        preset_path = (_parsed(matches[0]["base_url"]).path or "").rstrip("/").lower()
        if path in {"", preset_path, "/v1", "/openai", "/openai/v1"}:
            return matches[0]
        if preset_path and path == preset_path:
            return matches[0]
    provider = detect_provider(base_url)
    for item in matches:
        if item["id"] == provider and (parsed.path or "").rstrip("/").lower() in {
            "",
            (_parsed(item["base_url"]).path or "").rstrip("/").lower(),
            "/v1",
        }:
            return item
    return None


def canonical_base_url(base_url: str | None) -> str:
    raw = _strip_known_suffix(base_url or "")
    if not raw:
        return ""
    preset = _preset_for(raw)
    if preset:
        return preset["base_url"]
    return raw


def resolve_chat_completions_url(base_url: str | None) -> str:
    """Return the chat-completions URL without doubling a version prefix."""
    raw = canonical_base_url(base_url)
    if not raw:
        raise ValueError("AI base URL is empty")
    lowered = raw.lower()
    if lowered.endswith(CHAT_SUFFIX):
        return raw
    path = urlparse(raw).path
    if _versioned_base(path):
        return raw + CHAT_SUFFIX
    return raw + "/v1" + CHAT_SUFFIX


def resolve_models_url(base_url: str | None) -> str:
    raw = canonical_base_url(base_url)
    preset = _preset_for(raw) if raw else None
    if preset and preset.get("models_url"):
        return preset["models_url"]
    chat = resolve_chat_completions_url(raw)
    if chat.lower().endswith(CHAT_SUFFIX):
        return chat[: -len(CHAT_SUFFIX)] + "/models"
    return chat.rstrip("/") + "/models"


def build_headers(provider: str, api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
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
            "Base URL را از فهرست ارائه‌دهنده بردار. برای Gemini دقیقاً "
            "https://generativelanguage.googleapis.com/v1beta/openai است و بعد از openai "
            "یک /v1 اضافه نمی‌شود. برای NVIDIA دقیقاً https://integrate.api.nvidia.com/v1. "
            f"پاسخ: {snippet or '404 page not found'}"
        )
    if status in {401, 403}:
        return f"HTTP {status}: کلید API رد شد. کلید در پاسخ و لاگ چاپ نمی‌شود."
    if status == 429:
        return "HTTP 429: سقف درخواست provider پر شده. کمی بعد دوباره تست کن."
    if status == 400:
        return f"HTTP 400: مدل یا پارامتر با این provider نمی‌خواند. {snippet}"
    return f"HTTP {status}: {snippet or 'بدون متن خطا'}"


def _is_chat_model(model_id: str) -> bool:
    low = model_id.lower()
    return not any(token in low for token in _NON_CHAT)


def parse_provider_models(data) -> tuple[list[dict], bool]:
    rows: list[dict] = []
    source = []
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        source = data["data"]
    elif isinstance(data, dict) and isinstance(data.get("models"), list):
        source = data["models"]
    for row in source:
        if not isinstance(row, dict):
            continue
        methods = row.get("supportedGenerationMethods") or row.get("supported_generation_methods") or []
        if methods and "generateContent" not in methods and "chat" not in {str(item).lower() for item in methods}:
            continue
        raw_name = str(row.get("id") or row.get("name") or row.get("model") or "").strip()
        if raw_name.startswith("models/"):
            raw_name = raw_name.split("/", 1)[1]
        model_id = raw_name.strip()
        if not model_id or len(model_id) > 160:
            continue
        display = str(row.get("displayName") or row.get("display_name") or row.get("name") or model_id).strip()
        if display.startswith("models/"):
            display = display.split("/", 1)[1]
        if display == model_id or len(display) > 160:
            display = model_id
        rows.append({"id": model_id, "name": display[:160]})
    chat = [row for row in rows if _is_chat_model(row["id"])]
    chosen = chat or rows
    seen = set()
    out = []
    for row in chosen:
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        out.append(row)
        if len(out) >= MODEL_CAP:
            break
    return out, len(chosen) > MODEL_CAP


def _local_base(url: str) -> bool:
    parsed = _parsed(url)
    return parsed.scheme == "http" and _host_key(parsed.hostname or "") in {"127.0.0.1", "host.docker.internal"}


def guard_base_url(base_url: str) -> str:
    raw = (base_url or "").strip()
    if not raw or len(raw) > 300:
        raise ValueError("آدرس پایه خالی یا طولانی است")
    if any(ch in raw for ch in "\n\r\t "):
        raise ValueError("آدرس پایه نامعتبر است")
    parsed = _parsed(raw)
    if parsed.username or parsed.password:
        raise ValueError("کلید را در آدرس نگذار")
    scheme = (parsed.scheme or "").lower()
    host = _host_key(parsed.hostname or "")
    if not host or scheme not in {"http", "https"}:
        raise ValueError("فقط آدرس http یا https مجاز است")
    local = host in {"127.0.0.1", "host.docker.internal"}
    if scheme == "http" and not local:
        raise ValueError("http فقط برای سرویس روی همین دستگاه مجاز است")
    if host in {"metadata.google.internal", "169.254.169.254"}:
        raise ValueError("این آدرس مجاز نیست")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and not local:
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise ValueError("این آدرس مجاز نیست")
    return raw


def _detect_payload(
    *,
    ok: bool,
    provider: str,
    base_url: str,
    models_url: str,
    endpoint: str,
    models: list[dict] | None = None,
    error: str = "",
    truncated: bool = False,
    note: str = "",
) -> dict:
    preset = _preset(provider) or {}
    return {
        "ok": ok,
        "provider": provider,
        "label": preset.get("label") or provider,
        "base_url": base_url,
        "models_url": models_url,
        "endpoint": endpoint,
        "models": models or [],
        "truncated": truncated,
        "hint": preset.get("hint") or "",
        "key_url": preset.get("key_url") or "",
        "note": note,
        "error": error,
    }


async def _get_json(url: str, headers: dict[str, str]) -> tuple[int, object, str]:
    timeout = httpx.Timeout(20.0, connect=8.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        response = await client.get(url, headers=headers)
    if response.status_code in {301, 302, 303, 307, 308}:
        return response.status_code, {}, "redirect"
    text = response.text or ""
    try:
        return response.status_code, response.json(), text
    except ValueError:
        return response.status_code, {}, text


def _status_error(status: int, body: str, models_url: str, secret: str) -> str:
    if status in {301, 302, 303, 307, 308}:
        return "این آدرس به جای دیگری می‌رود. Base را مستقیم از فهرست ارائه‌دهنده بگذار."
    if status in {401, 403}:
        return "کلید رد شد. کلید در پاسخ چاپ نمی‌شود."
    if status == 404:
        return f"مسیر فهرست مدل پیدا نشد: {models_url}. آدرس را از فهرست ارائه‌دهنده انتخاب کن، نه مسیر chat."
    if status == 429:
        return "سقف درخواست provider پر شده. کمی بعد دوباره تشخیص بزن."
    return f"HTTP {status} از {models_url}: {redact(body, secret) or 'بدون متن'}"


async def list_provider_models(base_url: str, api_key: str) -> dict:
    guarded = guard_base_url(base_url)
    canonical = canonical_base_url(guarded)
    provider = detect_provider(canonical or guarded)
    models_url = resolve_models_url(canonical or guarded)
    endpoint = resolve_chat_completions_url(canonical or guarded)
    secret = (api_key or "").strip()
    if not secret and not _local_base(canonical or guarded):
        return _detect_payload(
            ok=False,
            provider=provider,
            base_url=canonical or guarded,
            models_url=models_url,
            endpoint=endpoint,
            error="کلید API لازم است. اگر این ردیف قبلاً ذخیره شده، فیلد کلید را خالی بگذار تا همان کلید استفاده شود.",
        )
    headers = build_headers(provider, secret)
    note = ""
    try:
        status, data, text = await _get_json(models_url, headers)
    except httpx.TimeoutException:
        return _detect_payload(
            ok=False, provider=provider, base_url=canonical, models_url=models_url, endpoint=endpoint,
            error="زمان اتصال به فهرست مدل تمام شد.",
        )
    except httpx.HTTPError as exc:
        return _detect_payload(
            ok=False, provider=provider, base_url=canonical, models_url=models_url, endpoint=endpoint,
            error=redact(str(exc), secret) or "اتصال به فهرست مدل برقرار نشد.",
        )
    if provider == "gemini" and status in {401, 403, 404} and secret:
        native = "https://generativelanguage.googleapis.com/v1beta/models"
        native_headers = {"x-goog-api-key": secret, "Content-Type": "application/json"}
        try:
            native_status, native_data, native_text = await _get_json(native, native_headers)
        except httpx.HTTPError:
            native_status, native_data, native_text = status, data, text
        if native_status == 200:
            status, data, text = native_status, native_data, native_text
            models_url = native
            note = "فهرست از مسیر بومی جمنای آمد. ارسال همچنان از مسیر openai سازگار است."
    if provider in {"ollama", "ollama-local"} and status == 404:
        tags = "https://ollama.com/api/tags" if provider == "ollama" else "http://127.0.0.1:11434/api/tags"
        try:
            tag_status, tag_data, tag_text = await _get_json(tags, headers)
        except httpx.HTTPError:
            tag_status, tag_data, tag_text = status, data, text
        if tag_status == 200:
            status, data, text = tag_status, tag_data, tag_text
            models_url = tags
            note = "فهرست از مسیر بومی Ollama آمد. ارسال از لایه /v1 است."
    if status != 200:
        return _detect_payload(
            ok=False, provider=provider, base_url=canonical, models_url=models_url, endpoint=endpoint,
            error=_status_error(status, text, models_url, secret), note=note,
        )
    models, truncated = parse_provider_models(data)
    if not models:
        return _detect_payload(
            ok=False, provider=provider, base_url=canonical, models_url=models_url, endpoint=endpoint,
            error="فهرست مدل خالی بود. شناسه را دستی بنویس.", note=note,
        )
    return _detect_payload(
        ok=True, provider=provider, base_url=canonical, models_url=models_url, endpoint=endpoint,
        models=models, truncated=truncated, note=note,
    )
