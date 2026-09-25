"""Ordered AI models. The first live model answers; the rest are fallback.

API keys stay in the runtime store. Public views and backups without
secrets only see a mask.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from backend.app.services.ai_provider import detect_provider, resolve_chat_completions_url


@dataclass
class AIModel:
    id: str
    label: str
    base_url: str
    model: str
    api_key: str
    enabled: bool = True

    @property
    def provider(self) -> str:
        return detect_provider(self.base_url)

    @property
    def ready(self) -> bool:
        return bool(self.enabled and self.base_url and self.model and self.api_key)

    @property
    def endpoint(self) -> str:
        try:
            return resolve_chat_completions_url(self.base_url) if self.base_url else ""
        except ValueError:
            return ""


def _mask(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) > 10:
        return secret[:4] + "…" + secret[-4:]
    return "••••"


def _keep_key(raw: str | None) -> bool:
    text = (raw or "").strip()
    return bool(text) and text != "••••" and "…" not in text and "..." not in text


def parse_models(raw) -> list[dict]:
    if not raw:
        return []
    if isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        try:
            items = json.loads(raw)
        except (TypeError, ValueError):
            return []
    if not isinstance(items, list):
        return []
    out = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        out.append({
            "id": str(item.get("id") or f"m{index + 1}")[:40],
            "label": str(item.get("label") or "")[:64],
            "base_url": str(item.get("base_url") or "").strip()[:300],
            "model": str(item.get("model") or "").strip()[:160],
            "api_key": str(item.get("api_key") or ""),
            "enabled": bool(item.get("enabled", True)),
        })
    return out[:8]


def as_models(raw) -> list[AIModel]:
    return [
        AIModel(
            id=item["id"],
            label=item["label"],
            base_url=item["base_url"],
            model=item["model"],
            api_key=item["api_key"],
            enabled=item["enabled"],
        )
        for item in parse_models(raw)
    ]


def configured_models(runtime) -> list[AIModel]:
    stored = as_models(getattr(runtime, "ai_models", None))
    if stored:
        return [item for item in stored if item.ready]
    base = str(getattr(runtime, "ai_base_url", "") or "").strip()
    model = str(getattr(runtime, "ai_model", "") or "").strip()
    key = str(getattr(runtime, "ai_api_key", "") or "")
    if base and model and key:
        return [AIModel(id="legacy", label="", base_url=base, model=model, api_key=key, enabled=True)]
    return []


def public_models(runtime) -> list[dict]:
    stored = as_models(getattr(runtime, "ai_models", None))
    if not stored and (getattr(runtime, "ai_base_url", "") or getattr(runtime, "ai_model", "") or getattr(runtime, "ai_api_key", "")):
        stored = [AIModel(
            id="legacy",
            label="",
            base_url=str(getattr(runtime, "ai_base_url", "") or ""),
            model=str(getattr(runtime, "ai_model", "") or ""),
            api_key=str(getattr(runtime, "ai_api_key", "") or ""),
            enabled=True,
        )]
    return [
        {
            "id": item.id,
            "label": item.label,
            "base_url": item.base_url,
            "model": item.model,
            "enabled": item.enabled,
            "provider": item.provider,
            "endpoint": item.endpoint,
            "api_key_set": bool(item.api_key),
            "api_key_masked": _mask(item.api_key),
        }
        for item in stored
    ]


def merge_models(incoming, stored, legacy_key: str = "") -> list[dict]:
    previous = {item.id: item for item in as_models(stored)}
    if legacy_key and "legacy" not in previous:
        previous["legacy"] = AIModel(id="legacy", label="", base_url="", model="", api_key=legacy_key)
    merged = []
    seen = set()
    for index, item in enumerate(list(incoming or [])[:8]):
        data = item if isinstance(item, dict) else item.model_dump()
        mid = str(data.get("id") or f"m{index + 1}")[:40]
        if mid in seen:
            continue
        seen.add(mid)
        old = previous.get(mid)
        key = str(data.get("api_key") or "")
        if not _keep_key(key):
            key = old.api_key if old else ""
        merged.append({
            "id": mid,
            "label": str(data.get("label") or "")[:64],
            "base_url": str(data.get("base_url") or "").strip()[:300],
            "model": str(data.get("model") or "").strip()[:160],
            "api_key": key,
            "enabled": bool(data.get("enabled", True)),
        })
    return merged


def redact_models_json(raw: str | None) -> str:
    cleaned = []
    for item in parse_models(raw):
        item["api_key"] = ""
        cleaned.append(item)
    return json.dumps(cleaned, ensure_ascii=False)
