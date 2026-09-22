import httpx
import logging
from typing import Optional
from backend.app.core.config import get_settings

logger = logging.getLogger(__name__)

async def enhance_with_ai(text: str, category: str = "general") -> Optional[str]:
    """
    Call external AI API to enhance/rewrite content.
    Returns enhanced text or None if AI fails/disabled.
    """
    s = get_settings()
    if not s.ai_enabled or not s.ai_base_url or not s.ai_model or not s.ai_api_key:
        return None
    
    prompt = s.ai_prompt_template.format(text=text)
    
    headers = {
        "Authorization": f"Bearer {s.ai_api_key}",
        "Content-Type": "application/json",
    }
    
    # OpenAI-compatible payload
    payload = {
        "model": s.ai_model,
        "messages": [
            {"role": "system", "content": "You are a Telegram channel content editor for Iranian university entrance exam (konkur) counseling. Rewrite content preserving meaning, add appropriate emojis, structure with header/footer, professional friendly tone."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 2000,
    }
    
    url = s.ai_base_url.rstrip("/") + "/v1/chat/completions"
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            if content:
                logger.info(f"AI enhanced text for category={category}, len={len(content)}")
                return content
    except httpx.HTTPStatusError as e:
        logger.error(f"AI API error {e.response.status_code}: {e.response.text}")
    except Exception as e:
        logger.error(f"AI call failed: {e}")
    return None

async def test_ai_connection() -> dict:
    """Test AI connection with a simple prompt."""
    s = get_settings()
    if not s.ai_enabled or not s.ai_base_url or not s.ai_model or not s.ai_api_key:
        return {"ok": False, "error": "AI not configured"}
    
    headers = {
        "Authorization": f"Bearer {s.ai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": s.ai_model,
        "messages": [{"role": "user", "content": "سلام، تست اتصال"}],
        "max_tokens": 10,
    }
    url = s.ai_base_url.rstrip("/") + "/v1/chat/completions"
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                return {"ok": True, "model": s.ai_model}
            return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

