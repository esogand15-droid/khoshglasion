import html

TELEGRAM_TEXT_LIMIT = 4096
TELEGRAM_CAPTION_LIMIT = 1024

def validate_length(text: str, is_caption: bool = False) -> tuple[bool, str | None]:
    limit = TELEGRAM_CAPTION_LIMIT if is_caption else TELEGRAM_TEXT_LIMIT
    if len(text) > limit:
        return False, f"Text exceeds limit {limit}: {len(text)} chars"
    if not text or not text.strip():
        return False, "Empty text"
    return True, None

def escape_html(text: str) -> str:
    return html.escape(text)

def validate_entities(text: str, entities: list | None) -> tuple[bool, str | None]:
    if not entities:
        return True, None
    for e in entities:
        offset = e.get("offset", 0) if isinstance(e, dict) else getattr(e, "offset", 0)
        length = e.get("length", 0) if isinstance(e, dict) else getattr(e, "length", 0)
        if offset < 0 or length <= 0 or offset + length > len(text):
            return False, f"Invalid entity offset={offset} length={length} text_len={len(text)}"
    return True, None
