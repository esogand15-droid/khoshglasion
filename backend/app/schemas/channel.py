from pydantic import BaseModel
from typing import Optional

class ChannelCreate(BaseModel):
    chat_id: int
    username: Optional[str]=None
    title: Optional[str]=None
    enabled: bool=True
    auto_beautify: bool=True
    emoji_replacement: bool=True
    style_id: Optional[str]=None
    footer_text: Optional[str]=None
    header_enabled: bool=True
    processing_mode: str="auto"

class ChannelUpdate(BaseModel):
    username: Optional[str]=None
    title: Optional[str]=None
    enabled: Optional[bool]=None
    auto_beautify: Optional[bool]=None
    emoji_replacement: Optional[bool]=None
    style_id: Optional[str]=None
    footer_text: Optional[str]=None
    header_enabled: Optional[bool]=None
    processing_mode: Optional[str]=None

class ChannelOut(ChannelCreate):
    id: str
    class Config:
        from_attributes=True
