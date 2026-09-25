import re

from backend.app.formatting.emoji import EmojiMapping, emoji_graphemes
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


def test_custom_emoji_divider_becomes_a_full_premium_row():
    text = "عنوان\n⚡\nعضویت در کانال مشاوره رتبه لند\n@Rotbeland_support"
    offset = utf16_len("عنوان\n")
    entities = [{"type": "custom_emoji", "offset": offset, "length": utf16_len("⚡"), "custom_emoji_id": "555"}]
    result = format_message(text, entities=entities, enable_emoji=True, header_enabled=False)
    html = result.html_text or ""
    assert html.count('emoji-id="555"') == 10
    assert 'emoji-id="555">⚡⚡' not in html
    sparks = [item for item in result.entities or [] if item.get("custom_emoji_id") == "555"]
    assert sparks and all(item["length"] == 1 for item in sparks)


def test_library_divider_used_when_post_has_no_rule():
    maps = [EmojiMapping("⚡", "777", enabled=True, category="divider", priority=90)]
    text, html, _entities, spans, rules = prepare_post(
        "فقط یک جمله کوتاه برای تست",
        mappings=maps,
        enable_emoji=True,
        add_footer=False,
    )
    assert "add_divider_emoji" in rules
    assert sum(1 for item in spans if item[2] == "777") == 10
    assert "⚡" * 10 in text
    assert html and html.count("777") == 10
    assert 'emoji-id="777">⚡⚡' not in html


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
    assert result.text.count("⚡") == 7
    assert (result.html_text or "").count('emoji-id="555"') == 7
    assert 'emoji-id="555">⚡⚡' not in (result.html_text or "")
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


def test_short_post_gets_one_gold_line_not_two():
    maps = [EmojiMapping("⚡", "777", enabled=True, category="divider", priority=90)]
    result = format_message("تست", emoji_mappings=maps, enable_emoji=True, header_enabled=False)
    gold = [line.strip() for line in result.text.splitlines() if line.strip() and set(line.strip()) <= {"⚡"}]
    assert gold == ["⚡" * 10]
    assert result.html_text and result.html_text.count("777") == 10
    assert 'emoji-id="777">⚡⚡' not in result.html_text


def test_existing_double_gold_line_collapses():
    text = "تست\n\n⚡\n⚡"
    first = text.index("⚡")
    second = text.index("⚡", first + 1)
    entities = [
        {"type": "custom_emoji", "offset": utf16_len(text[:first]), "length": utf16_len("⚡"), "custom_emoji_id": "777"},
        {"type": "custom_emoji", "offset": utf16_len(text[:second]), "length": utf16_len("⚡"), "custom_emoji_id": "777"},
    ]
    result = format_message(
        text,
        entities=entities,
        emoji_mappings=[EmojiMapping("⚡", "777", enabled=True, category="divider", priority=90)],
        enable_emoji=True,
        header_enabled=False,
    )
    gold = [line.strip() for line in result.text.splitlines() if line.strip() and set(line.strip()) <= {"⚡"}]
    assert gold == ["⚡" * 10]
    assert result.html_text and result.html_text.count("777") == 10


def test_plain_post_gets_a_body_emoji_not_only_footer():
    maps = [EmojiMapping("📢", "42", enabled=True, priority=80)]
    result = format_message(
        "اطلاعیه مهم\nمدارس هرمزگان این هفته مجازی شد",
        emoji_mappings=maps,
        enable_emoji=True,
        header_enabled=False,
        emoji_layout="title",
    )
    assert result.text.startswith("📢 ")
    assert result.html_text and 'emoji-id="42"' in result.html_text
    assert result.text.count("📢") == 1


def test_lightning_row_does_not_survive_beside_a_gold_line():
    maps = [EmojiMapping("⚡", "777", enabled=True, category="divider", priority=90)]
    result = format_message(
        "عنوان خبر\n⚡⚡⚡⚡⚡⚡⚡✨",
        emoji_mappings=maps,
        enable_emoji=True,
        header_enabled=False,
    )
    assert "✨" not in result.text
    assert [line.strip() for line in result.text.splitlines() if "⚡" in line] == ["⚡" * 8]
    assert (result.html_text or "").count("777") == 8
    assert 'emoji-id="777">⚡⚡' not in (result.html_text or "")


def test_plain_divider_is_one_line():
    result = format_message("سلام وقت بخیر دوستان", enable_emoji=False, header_enabled=False)
    rules = [line for line in result.text.splitlines() if line.strip() and set(line.strip()) <= set("━─▬")]
    assert len(rules) == 1


def test_plain_post_still_gets_membership_link():
    result = format_message("این یک تست است", enable_emoji=False, header_enabled=False)
    assert "رتبه لند" in result.text
    assert "━━━━" in result.text
    assert result.html_text and "https://t.me/Rotbeland1" in result.html_text
    marks = parse_telegram_entities("🏆 سلام", [{"type": "bold", "offset": 3, "length": 4}])
    assert marks[0].type == "bold"


def test_spark_row_is_separate_graphemes():
    assert [item[2] for item in emoji_graphemes("⚡" * 4)] == ["⚡"] * 4
    assert [item[2] for item in emoji_graphemes("⚡️" * 3)] == ["⚡️"] * 3
    assert utf16_len("⚡️") == 2


def test_long_custom_emoji_on_gold_line_is_split():
    bolts = "⚡" * 8
    text = f"عنوان\n{bolts}"
    entities = [{
        "type": "custom_emoji",
        "offset": utf16_len("عنوان\n"),
        "length": utf16_len(bolts),
        "custom_emoji_id": "555",
    }]
    result = format_message(
        text,
        entities=entities,
        emoji_mappings=[EmojiMapping("⚡", "555", enabled=True, category="divider", priority=90)],
        enable_emoji=True,
        header_enabled=False,
    )
    html = result.html_text or ""
    sparks = [item for item in result.entities or [] if item.get("custom_emoji_id") == "555"]
    assert len(sparks) == 8
    assert all(item["length"] == utf16_len("⚡") for item in sparks)
    assert html.count('emoji-id="555"') == 8
    assert not re.search(r'<tg-emoji emoji-id="555">⚡⚡', html)


def test_whole_post_emoji_become_premium_not_only_footer():
    maps = [
        EmojiMapping("⚡", "555", enabled=True, category="divider", priority=90),
        EmojiMapping("🏆", "42", enabled=True, priority=80),
        EmojiMapping("🔥", "43", enabled=True, priority=70),
    ]
    result = format_message(
        "🏆 عنوان خبر\nجزئیات 🔥 اینجاست\n⚡⚡⚡⚡⚡",
        emoji_mappings=maps,
        enable_emoji=True,
        header_enabled=False,
    )
    html = result.html_text or ""
    assert "عنوان خبر" in result.text
    assert "جزئیات" in result.text
    assert "🏆" in result.text
    assert "🔥" in result.text
    assert 'emoji-id="42"' in html
    assert 'emoji-id="43"' in html
    assert html.count('emoji-id="555"') == 5
    assert 'emoji-id="555">⚡⚡' not in html


def test_unmapped_body_emoji_is_not_left_as_unicode():
    maps = [EmojiMapping("📢", "9", enabled=True, priority=80)]
    result = format_message("🏆 خبر مهم", emoji_mappings=maps, enable_emoji=True, header_enabled=False)
    assert "🏆" not in result.text
    assert "📢" in result.text
    assert 'emoji-id="9"' in (result.html_text or "")


def test_exam_option_emoji_is_not_rewritten():
    maps = [EmojiMapping("📢", "9", enabled=True, priority=80)]
    result = format_message(
        "سوال آزمون\n1) گزینه ✅ درست",
        emoji_mappings=maps,
        enable_emoji=True,
        header_enabled=False,
    )
    assert "1) گزینه ✅ درست" in result.text


def test_link_survives_emoji_replacement():
    text = "جزئیات 🏆 اینجا"
    start = text.index("اینجا")
    entities = [{
        "type": "text_link",
        "offset": utf16_len(text[:start]),
        "length": utf16_len("اینجا"),
        "url": "https://t.me/Rotbeland1",
    }]
    result = format_message(
        text,
        entities=entities,
        emoji_mappings=[EmojiMapping("🏆", "42", enabled=True, priority=80)],
        enable_emoji=True,
        header_enabled=False,
    )
    assert "اینجا" in result.text
    assert "https://t.me/Rotbeland1" in (result.html_text or "")
    assert 'emoji-id="42"' in (result.html_text or "")
