from backend.app.formatting.engine import format_message
from backend.app.formatting.emoji import EmojiMapping

def test_no_change_detection():
    r = format_message("سلام", enable_emoji=False)
    # footer will be added so changed True unless minimal
    assert r.category in ["general","consulting","announcement","news","resource"]

def test_footer_added():
    r = format_message("این یک تست است", enable_emoji=False)
    assert r.changed is True
    assert "━━━━" in r.text or "رتبه لند" in r.text

def test_bullet_normalization():
    r = format_message("• مورد اول\n• مورد دوم", enable_emoji=False)
    assert "🔹" in r.text

def test_spacing():
    r = format_message("سلام\n\n\n\nدنیا", enable_emoji=False)
    assert "\n\n\n" not in r.text

def test_emoji_mapping():
    maps = [EmojiMapping(unicode_emoji="📢", custom_emoji_id="1234567890123456789", enabled=True, contexts=None, priority=50)]
    r = format_message("📢 اطلاعیه مهم", emoji_mappings=maps, enable_emoji=True)
    assert r.html_text is not None
    assert "tg-emoji" in r.html_text

def test_caption_limit():
    long_text = "a" * 1025
    r = format_message(long_text, is_caption=True, enable_emoji=False)
    assert len(r.text) <= 1024
    assert r.changed is True

def test_hash_idempotent():
    r1 = format_message("متن یکسان", enable_emoji=False)
    r2 = format_message("متن یکسان", enable_emoji=False)
    assert r1.text == r2.text
