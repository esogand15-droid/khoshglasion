import json

from backend.app.formatting.editor import analyze_post
from backend.app.formatting.emoji import EmojiMapping, find_emoji_spans
from backend.app.formatting.engine import format_message
from backend.app.formatting.rotation import apply_structure, choose_template, pick_avoiding_recent
from backend.app.formatting.styles import get_style


def test_locked_post_does_not_rotate():
    decision = analyze_post("رتبه ۱۲۳۴ در کارنامه ثبت شد و نباید عوض شود برای بررسی دقیق")
    choice = choose_template(
        decision,
        channel_style="premium",
        recent_structures=["classic", "airy"],
        recent_emoji_styles=["chrome"],
        emoji_enabled=True,
    )
    assert choice.structure_id == "locked"
    assert choice.emoji_style_id == "chrome"
    assert choice.style_id == "premium"
    assert choice.template_id.endswith(".locked")


def test_soft_post_avoids_the_last_three_structures():
    decision = analyze_post("برنامه " + ("این بخش را دقیق و آرام بخوان. " * 8))
    assert decision.strategy == "structure_only"
    choice = choose_template(
        decision,
        channel_style=None,
        recent_structures=["classic", "airy", "compact"],
        emoji_enabled=False,
    )
    assert choice.structure_id != "compact"
    assert choice.structure_id in {"classic", "airy"}
    assert choice.emoji_style_id == "off"


def test_structure_changes_rhythm_not_words():
    raw = "رتبه ۱۲۳۴ ماند\n\nگزینه عوض نشد"
    compact = apply_structure(raw, "compact")
    assert "۱۲۳۴" in compact
    assert "\n\n" not in compact
    airy = apply_structure("جمله اول ماند\nجمله دوم ماند", "airy")
    assert "جمله اول ماند" in airy and "جمله دوم ماند" in airy
    assert "\n\n" in airy
    listed = apply_structure("🔹 مورد اول\n🔹 مورد دوم", "airy")
    assert "\n\n" not in listed


def test_default_format_still_adds_footer():
    styled = format_message(
        "جمله اول ماند\nجمله دوم ماند",
        enable_emoji=False,
        header_enabled=False,
        style_config=get_style("minimal"),
        structure_id="airy",
    )
    assert "جمله اول ماند" in styled.text
    assert "structure:airy" in styled.applied_rules
    untouched = format_message("این یک تست است", enable_emoji=False, header_enabled=False)
    assert "رتبه لند" in untouched.text


def test_recent_emoji_id_is_tried_last():
    maps = [
        EmojiMapping("⭐", "111", enabled=True, priority=10),
        EmojiMapping("⭐", "222", enabled=True, priority=90),
    ]
    normal = find_emoji_spans("⭐ سلام", maps, "general", max_emoji=1)
    avoided = find_emoji_spans("⭐ سلام", maps, "general", max_emoji=1, avoid_ids={"222"})
    assert normal[0][3] == "222"
    assert avoided[0][3] == "111"


def test_pick_is_stable_when_only_one_choice():
    assert pick_avoiding_recent(("locked",), ["classic", "airy"]) == "locked"
