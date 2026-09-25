from pydantic import BaseModel
from typing import Optional

class EmojiCreate(BaseModel):
    unicode_emoji: str
    custom_emoji_id: str
    enabled: bool=True
    category: Optional[str]=None
    contexts: Optional[list[str]]=None
    priority: int=50

class EmojiUpdate(BaseModel):
    unicode_emoji: Optional[str]=None
    custom_emoji_id: Optional[str]=None
    enabled: Optional[bool]=None
    category: Optional[str]=None
    contexts: Optional[list[str]]=None
    priority: Optional[int]=None

class EmojiOut(BaseModel):
    id: str
    unicode_emoji: str
    custom_emoji_id: str
    enabled: bool
    category: Optional[str]=None
    contexts: Optional[str]=None
    priority: int
    usage_count: int
    class Config:
        from_attributes=True
