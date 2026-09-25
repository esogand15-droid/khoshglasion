from datetime import datetime, timedelta, timezone

from backend.app.content.pipeline import (
    choose_hashtags,
    content_hash,
    judge_value,
    should_auto_schedule,
    too_similar,
)
from backend.app.formatting.emoji import EmojiMapping
from backend.app.formatting.engine import format_message
from backend.app.formatting.richtext import plan_placements
from backend.app.services.autopost import accept_draft, normalize_source


def test_plan_spreads_list_without_covering_every_line():
    placed = plan_placements([0, 1, 2, 3, 4, 5], "list", 4)
    indexes = [index for index, _role in placed]
    assert indexes[0] == 0
    assert len(indexes) >= 2
    assert len(indexes) < 6
    assert indexes != [5]


def test_multiparagraph_post_gets_emoji_through_the_body():
    maps = [
        EmojiMapping("📢", "101", enabled=True, priority=90, category="announcement"),
        EmojiMapping("✨", "102", enabled=True, priority=70, category="general"),
        EmojiMapping("📌", "103", enabled=True, priority=60, category="general"),
    ]
    source = "\n".join([
        "اطلاعیه مهم ثبت نام",
        "مدارس هرمزگان این هفته کلاس حضوری ندارند و برنامه جایگزین اعلام شد.",
        "دانش‌آموزان باید برنامه هفتگی را از مدرسه خود بگیرند و چیزی را حدس نزنند.",
        "مهلت ارسال فرم تا پایان همین هفته است و بعد از آن ترتیب اثر داده نمی‌شود.",
        "جزئیات بیشتر در پیام مدرسه آمده است.",
        "https://example.com/notice",
        "#اطلاعیه",
    ])
    result = format_message(
        source,
        emoji_mappings=maps,
        enable_emoji=True,
        header_enabled=False,
        emoji_layout="list",
        category="announcement",
    )
    lines = [line for line in result.text.splitlines() if line.strip()]
    marked = [line for line in lines if line.startswith(("📢", "✨", "📌"))]
    assert len(marked) >= 2
    assert len(marked) < len(lines)
    assert "https://example.com/notice" in result.text
    assert "#اطلاعیه" in result.text
    assert "هرمزگان" in result.text
    assert not lines[-1].startswith(("📢", "✨", "📌")) or len(marked) > 1


def test_duplicate_hash_ignores_link_and_hashtag_noise():
    left = "سازمان سنجش مهلت ثبت نام را تا ۱۴۰۴/۰۶/۲۰ تمدید کرد و اطلاعیه جدید داد"
    right = left + "\nhttps://t.me/example/9\n#خبر"
    assert content_hash(left) == content_hash(right)


def test_low_value_and_stale_never_auto_schedule():
    short = judge_value("کوتاه")
    assert short["value"] == "LOW_VALUE"
    assert should_auto_schedule(short, True, False) is False
    stale = judge_value(
        "این یک یادداشت قدیمی درباره انتخاب رشته است و عدد تازه‌ای ندارد.",
        created_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    assert stale["value"] == "OUTDATED"
    assert should_auto_schedule(stale, True, False) is False


def test_similar_opening_is_rejected_and_hashtags_stay_official():
    first = "سازمان سنجش امروز مهلت جدید را اعلام کرد و جزئیات را منتشر نمود."
    second = "سازمان سنجش امروز مهلت جدید را اعلام کرد و فقط فعل آخر عوض شد."
    assert too_similar(first, [second]) is True
    tags = choose_hashtags("news", "اطلاعیه ثبت نام")
    assert tags[0] == "خبر"
    assert all(" " not in tag for tag in tags)


def test_private_invite_still_rejected_and_facts_stay():
    assert normalize_source("https://t.me/+AbCdEf") is None
    source = "مهلت ثبت نام تا ۱۴۰۴/۰۶/۲۰ تمدید شد و ظرفیت ۱۲۳۴ نفر اعلام گردید."
    accepted, reason = accept_draft(source, "مهلت ثبت نام تمدید شد و ظرفیت جدید اعلام گردید، بدون ذکر عدد قبلی.")
    assert accepted is None
    assert reason == "dropped_numbers"
