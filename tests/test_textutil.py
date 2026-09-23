from backend.app.formatting.engine import format_message
from backend.app.formatting.emoji import EmojiMapping
from backend.app.formatting.textutil import (
    clean_ai_output,
    missing_long_numbers,
    missing_protected_tokens,
    restore_protected_tokens,
)
from backend.app.services.ai import accept_ai_output


def test_clean_ai_output_strips_fence_and_label():
    raw = "```text\nمتن نهایی:\nسلام کنکور\n```"
    assert clean_ai_output(raw) == "سلام کنکور"


def test_protected_tokens_are_restored():
    original = "جزوه را از https://example.com/a بگیر و به @Rotbeland_support بگو #کنکور"
    output = "جزوه آماده است."
    missing = missing_protected_tokens(original, output)
    restored = restore_protected_tokens(output, missing)
    assert "https://example.com/a" in restored
    assert "@Rotbeland_support" in restored
    assert "#کنکور" in restored


def test_ai_output_rejects_dropped_numbers():
    accepted, reason = accept_ai_output("تراز ۱۴۵۰۰ ثبت شد", "تراز خوبی بود", 1000)
    assert accepted is None
    assert reason == "dropped_numbers"


def test_html_escapes_text_and_keeps_premium_emoji():
    maps = [EmojiMapping(unicode_emoji="📢", custom_emoji_id="5424818078833715060", enabled=True)]
    result = format_message("سلام <b> & 📢", emoji_mappings=maps, enable_emoji=True, header_enabled=False)
    assert result.html_text is not None
    assert "<tg-emoji" in result.html_text
    assert "&lt;b&gt;" in result.html_text
    assert "&amp;" in result.html_text
    assert "<b>" not in result.html_text.replace("<tg-emoji", "")


def test_caption_over_limit_is_trimmed_not_rejected():
    result = format_message("a" * 1025, is_caption=True, enable_emoji=False)
    assert len(result.text) <= 1024
    assert result.changed is True


def test_missing_numbers_accepts_persian_digits():
    assert missing_long_numbers("کد 14500", "کد ۱۴۵۰۰") == []
