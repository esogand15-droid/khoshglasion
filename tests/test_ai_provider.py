import asyncio
from types import SimpleNamespace

from backend.app.services.ai import test_ai_connection as run_ai_health
from backend.app.services.ai_provider import (
    build_payload,
    detect_provider,
    extract_message_text,
    resolve_chat_completions_url,
)


def test_nvidia_base_is_not_double_versioned():
    url = resolve_chat_completions_url("https://integrate.api.nvidia.com/v1")
    assert url == "https://integrate.api.nvidia.com/v1/chat/completions"
    assert "/v1/v1/" not in url


def test_host_only_and_full_endpoint():
    assert resolve_chat_completions_url("https://api.openai.com") == "https://api.openai.com/v1/chat/completions"
    assert resolve_chat_completions_url("https://openrouter.ai/api/v1/") == "https://openrouter.ai/api/v1/chat/completions"
    assert resolve_chat_completions_url("https://integrate.api.nvidia.com/v1/chat/completions") == "https://integrate.api.nvidia.com/v1/chat/completions"


def test_provider_detection_and_nvidia_payload():
    assert detect_provider("https://integrate.api.nvidia.com/v1") == "nvidia"
    payload = build_payload("nvidia", "openai/gpt-oss-20b", [{"role": "user", "content": "سلام"}], temperature=1, max_tokens=4096)
    assert "presence_penalty" not in payload
    assert payload["model"] == "openai/gpt-oss-20b"
    assert payload["stream"] is False


def test_reasoning_content_is_accepted():
    text, reason = extract_message_text({
        "choices": [{"finish_reason": "stop", "message": {"content": None, "reasoning_content": "سلام"}}]
    })
    assert text == "سلام"
    assert reason == "stop"


def test_health_check_posts_resolved_nvidia_url_and_hides_key():
    seen = {}

    class Response:
        status_code = 404
        text = "404 page not found nvapi-secret-key"
        request = None

        def json(self):
            return {}

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None, headers=None):
            seen["url"] = url
            seen["headers"] = headers
            return Response()

    runtime = SimpleNamespace(
        ai_ready=True,
        ai_base_url="https://integrate.api.nvidia.com/v1",
        ai_model="openai/gpt-oss-20b",
        ai_api_key="nvapi-secret-key",
        ai_max_tokens=1800,
        ai_temperature=0.7,
    )
    import backend.app.services.ai as ai_module
    original = ai_module.httpx.AsyncClient
    ai_module.httpx.AsyncClient = Client
    try:
        result = asyncio.run(run_ai_health(runtime))
    finally:
        ai_module.httpx.AsyncClient = original
    assert seen["url"] == "https://integrate.api.nvidia.com/v1/chat/completions"
    assert result["ok"] is False
    assert result["provider"] == "nvidia"
    assert "nvapi-secret-key" not in result["error"]
    assert "404" in result["error"]
