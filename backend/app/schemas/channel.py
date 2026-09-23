from typing import Optional

from pydantic import BaseModel, Field


class ChannelCreate(BaseModel):
    chat_id: int
    username: Optional[str] = None
    title: Optional[str] = None
    enabled: bool = True
    auto_beautify: bool = True
    emoji_replacement: bool = True
    style_id: Optional[str] = None
    footer_text: Optional[str] = None
    header_enabled: bool = False
    processing_mode: str = "auto"
    ai_rewrite: Optional[bool] = None
    edit_delay_seconds: Optional[int] = Field(default=None, ge=0, le=60)
    signature_text: Optional[str] = None
    signature_url: Optional[str] = None
    skip_keywords: Optional[str] = None
    min_chars: int = 1
    preserve_buttons: bool = True
    notes: Optional[str] = None


class ChannelUpdate(BaseModel):
    username: Optional[str] = None
    title: Optional[str] = None
    enabled: Optional[bool] = None
    auto_beautify: Optional[bool] = None
    emoji_replacement: Optional[bool] = None
    style_id: Optional[str] = None
    footer_text: Optional[str] = None
    header_enabled: Optional[bool] = None
    processing_mode: Optional[str] = None
    ai_rewrite: Optional[bool] = None
    edit_delay_seconds: Optional[int] = Field(default=None, ge=0, le=60)
    signature_text: Optional[str] = None
    signature_url: Optional[str] = None
    skip_keywords: Optional[str] = None
    min_chars: Optional[int] = None
    preserve_buttons: Optional[bool] = None
    notes: Optional[str] = None
    can_edit: Optional[bool] = None
