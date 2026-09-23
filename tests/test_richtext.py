from backend.app.formatting.emoji import EmojiMapping
from backend.app.formatting.engine import format_message
from backend.app.formatting.richtext import parse_telegram_entities, prepare_post
from backend.app.formatting.textutil import utf16_len
from backend.app.services.ai import accept_ai_output


def test_utf16_quote_survives_emoji_prefix():
    text = "🏆 سلام\nرضایت از دکتر"
    offset = utf16_len("🏆 سلام\n")
    entities = [{"type": "blockquote", "offset": offset, "length": utf16_len("رضایت از دکتر")}]
    result = format_message(text, entities=entities, enable_emoji=False, header_enabled=False)
    assert "<blockquote>رضایت از دکتر</blockquote>" in (result.html_text or "")
    assert "preserve_quote" in result.applied_rules


def test_footer_is_not_duplicated_and_mention_stays_ltr():
    text = (
        "واسه همینه میگیم رتبه لند جای بچه های خاص و رتبه برتره\n"
        "رضایت از دکتر امیرحسین معلمی\n"
        "⚡⚡⚡⚡⚡⚡⚡\n"
        "عضویت در کانال مشاوره رتبه لند\n"
        "رزرو مشاوره خصوصی:\n"
        "@Rotbeland_support\n"
        "━━━━━━━━\n"
        "مشاوره تخصصی کنکور\n"
        "عضویت در کانال مشاوره رتبه لند\n"
        "رزرو مشاوره خصوصی: @Rotbeland_support"
    )
    result = format_message(text, enable_emoji=False, header_enabled=False)
    assert result.text.count("عضویت در کانال") == 1
    assert "Rotbeland_support@" not in result.text
    assert "\u200e@Rotbeland_support" in result.text
    assert "⚡⚡" not in result.text
    assert "https://t.me/Rotbeland1" in (result.html_text or "")


def test_custom_emoji_divider_is_not_replaced_with_lightning_row():
    text = "عنوان\n⚡\nعضویت در کانال مشاوره رتبه لند\n@Rotbeland_support"
    offset = utf16_len("عنوان\n")
    entities = [{"type": "custom_emoji", "offset": offset, "length": utf16_len("⚡"), "custom_emoji_id": "555"}]
    result = format_message(text, entities=entities, enable_emoji=True, header_enabled=False)
    assert 'emoji-id="555"' in (result.html_text or "")
    assert "⚡⚡" not in result.text


def test_library_divider_used_when_post_has_no_rule():
    maps = [EmojiMapping("⚡", "777", enabled=True, category="divider", priority=90)]
    text, html, _entities, spans, rules = prepare_post(
        "فقط یک جمله کوتاه برای تست",
        mappings=maps,
        enable_emoji=True,
        add_footer=False,
    )
    assert "add_divider_emoji" in rules
    assert any(item[2] == "777" for item in spans)
    assert "⚡⚡⚡" not in text
    assert html and "777" in html


def test_quote_loss_rejects_ai_output():
    accepted, reason = accept_ai_output(
        "متن «رضایت از دکتر» باید بماند و عدد ۱۲۳۴ هم هست",
        "متن بازنویسی شد بدون نقل‌قول و ۱۲۳۴",
        500,
        required=["رضایت از دکتر"],
    )
    assert accepted is None
    assert reason == "dropped_quote"


def test_captured_divider_replaces_lightning_row():
    maps = [EmojiMapping("⚡", "555", enabled=True, category="divider", priority=90)]
    result = format_message(
        "عنوان تست\n⚡⚡⚡⚡⚡⚡⚡\nعضویت در کانال مشاوره رتبه لند\n@Rotbeland_support",
        emoji_mappings=maps,
        enable_emoji=True,
        header_enabled=False,
    )
    assert "⚡⚡" not in result.text
    assert result.text.count("⚡") == 1
    assert 'emoji-id="555"' in (result.html_text or "")
    assert result.text.count("عضویت در کانال") == 1


def test_footer_role_emoji_is_applied_to_existing_line():
    maps = [EmojiMapping("🌴", "888", enabled=True, category="membership", priority=80)]
    result = format_message(
        "عنوان تست\nعضویت در کانال مشاوره رتبه لند\n@Rotbeland_support",
        emoji_mappings=maps,
        enable_emoji=True,
        header_enabled=False,
    )
    assert "🌴" in result.text
    assert 'emoji-id="888"' in (result.html_text or "")


def test_plain_post_still_gets_membership_link():
    result = format_message("این یک تست است", enable_emoji=False, header_enabled=False)
    assert "رتبه لند" in result.text
    assert "━━━━" in result.text
    assert result.html_text and "https://t.me/Rotbeland1" in result.html_text
    marks = parse_telegram_entities("🏆 سلام", [{"type": "bold", "offset": 3, "length": 4}])
    assert marks[0].type == "bold"
