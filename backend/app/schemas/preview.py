from typing import Optional

from pydantic import BaseModel


class PreviewRequest(BaseModel):
    text: str
    is_caption: bool = False
    style_slug: Optional[str] = None
    channel_id: Optional[str] = None
    enable_emoji: bool = True
    use_ai: bool = False


class PreviewResponse(BaseModel):
    original: str
    formatted: str
    html_formatted: Optional[str] = None
    changed: bool
    category: str
    style: str
    applied_rules: list[str]
    warnings: list[str]
