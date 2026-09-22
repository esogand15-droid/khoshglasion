import asyncio
import logging
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter, TelegramForbiddenError, TelegramNetworkError
from backend.app.telegram.bot import get_bot

logger = logging.getLogger(__name__)

async def edit_telegram_message(chat_id: int, message_id: int, text: str, html_text: str | None, is_caption: bool, max_retries: int = 3) -> dict:
    bot = get_bot()
    if not bot:
        return {"ok": False, "error": "bot not configured"}
    attempt = 0
    while attempt <= max_retries:
        try:
            if is_caption:
                # edit caption
                if html_text:
                    await bot.edit_message_caption(chat_id=chat_id, message_id=message_id, caption=html_text, parse_mode="HTML")
                else:
                    await bot.edit_message_caption(chat_id=chat_id, message_id=message_id, caption=text)
            else:
                if html_text:
                    await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=html_text, parse_mode="HTML")
                else:
                    await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text)
            return {"ok": True}
        except TelegramRetryAfter as e:
            wait = getattr(e, "retry_after", 2)
            logger.warning(f"Rate limited, retry after {wait}s")
            await asyncio.sleep(wait)
            attempt += 1
        except TelegramBadRequest as e:
            msg = str(e)
            # Message not modified, too old, or not editable
            if "message is not modified" in msg.lower():
                return {"ok": True, "warning": "not_modified"}
            if "message to edit not found" in msg.lower() or "message can't be edited" in msg.lower():
                return {"ok": False, "error": f"not_editable: {msg}"}
            logger.error(f"BadRequest edit: {msg}")
            return {"ok": False, "error": msg}
        except TelegramForbiddenError as e:
            return {"ok": False, "error": f"forbidden: {e}"}
        except TelegramNetworkError as e:
            logger.warning(f"Network error attempt {attempt}: {e}")
            await asyncio.sleep(2 ** attempt)
            attempt += 1
        except Exception as e:
            logger.exception(f"Unexpected edit error: {e}")
            return {"ok": False, "error": str(e)}
    return {"ok": False, "error": "max_retries_exceeded"}
