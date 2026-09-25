from backend.app.telegram.edit import edit_attempts
from backend.app.telegram.pipeline import premium_edit_plan
from backend.app.telegram.publisher import requires_premium_send
from backend.app.formatting.emoji import custom_emoji_span_valid


def test_custom_emoji_edit_does_not_fall_back_to_plain():
    html = '<tg-emoji emoji-id="555">⚡</tg-emoji>'
    attempts = edit_attempts("⚡" * 8, html, True)
    assert [item[0] for item in attempts] == ["bot_html"]


def test_plain_formatting_can_still_retry_without_emoji():
    attempts = edit_attempts("سلام", "<b>سلام</b>", True)
    assert [item[0] for item in attempts] == ["bot_html", "bot_plain"]


def test_premium_channel_edit_does_not_downgrade():
    assert premium_edit_plan(True, "auto", True) == "user"
    assert premium_edit_plan(True, "auto", False) == "refuse"
    assert premium_edit_plan(True, "bot", True) == "refuse"
    assert premium_edit_plan(False, "auto", True) == "bot"
    assert premium_edit_plan(True, "off", True) == "bot"


def test_premium_publish_is_not_stripped():
    entities = [{"type": "custom_emoji", "custom_emoji_id": "555"}]
    assert requires_premium_send(entities, None) is True
    assert requires_premium_send(None, '<tg-emoji emoji-id="555">⚡</tg-emoji>') is True
    assert requires_premium_send(None, "<b>سلام</b>") is False


def test_one_entity_cannot_cover_a_spark_row():
    assert custom_emoji_span_valid("⚡" * 8, 0, 8) is False
    assert custom_emoji_span_valid("⚡" * 8, 0, 1) is True
    assert custom_emoji_span_valid("⚡️", 0, 2) is True
    assert custom_emoji_span_valid("⚡️⚡️", 0, 2) is True
