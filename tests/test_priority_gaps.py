from backend.app.formatting.engine import format_message
from backend.app.formatting.styles import get_style
from backend.app.formatting.textutil import utf16_len
from backend.app.logging_config.setup import redact_secrets


def _plain(text: str, entities: list[dict]):
    return format_message(
        text,
        entities=entities,
        enable_emoji=False,
        header_enabled=False,
        style_config=get_style("minimal"),
    )


def test_pre_spoiler_and_expandable_quote_survive():
    code = _plain("print(1)", [{"type": "pre", "offset": 0, "length": utf16_len("print(1)"), "language": "python"}])
    assert '<pre><code class="language-python">print(1)</code></pre>' in (code.html_text or "")
    assert any(item.get("language") == "python" for item in (code.entities or []))
    hidden = _plain("جواب ۲", [{"type": "spoiler", "offset": 0, "length": utf16_len("جواب")}])
    assert "<tg-spoiler>جواب</tg-spoiler>" in (hidden.html_text or "")
    quote = _plain("نکته مهم", [{"type": "expandable_blockquote", "offset": 0, "length": utf16_len("نکته مهم")}])
    assert "<blockquote expandable>نکته مهم</blockquote>" in (quote.html_text or "")
    struck = _plain("قدیمی", [{"type": "strikethrough", "offset": 0, "length": utf16_len("قدیمی")}])
    assert "<s>قدیمی</s>" in (struck.html_text or "")


def test_invalid_code_language_is_not_injected():
    messy = _plain("print(1)", [{"type": "pre", "offset": 0, "length": 8, "language": "py\"><script>"}])
    html = messy.html_text or ""
    assert "<script>" not in html
    assert "<pre>print(1)</pre>" in html


def test_log_redacts_provider_and_bot_secrets():
    raw = "failed nvapi-abcdefghijklmnopqrstuvwxyz token 123456789:AAHbotTokenExampleValueXXXX"
    cleaned = redact_secrets(raw)
    assert "nvapi-" not in cleaned
    assert "AAHbotToken" not in cleaned
    assert "***" in cleaned
    assert redact_secrets("ordinary text") == "ordinary text"
