from datetime import datetime, timezone

from backend.app.models.automation import PublishSlot
from backend.app.services.ai import parse_layout_token
from backend.app.services.autopost import (
    accept_draft,
    next_slot_time,
    normalize_source,
    slot_is_due,
    too_verbatim,
)


def test_source_link_is_a_public_username_only():
    assert normalize_source("https://t.me/Rotbeland1") == "Rotbeland1"
    assert normalize_source("@konkur_news") == "konkur_news"
    assert normalize_source("https://t.me/+AbCdEf") is None
    assert normalize_source("https://t.me/joinchat/AAAA") is None


def test_draft_keeps_numbers_and_rejects_a_verbatim_copy():
    source = "سازمان سنجش اعلام کرد ثبت‌نام از ۱۴۰۴/۰۷/۰۱ آغاز می‌شود و ظرفیت ۱۲۳۴۵ نفر است. " + ("جزئیات همان اطلاعیه رسمی است. " * 6)
    copied = source
    assert too_verbatim(source, copied)
    assert accept_draft(source, copied)[1] == "verbatim"
    original = "ثبت‌نام آزمون از ۱۴۰۴/۰۷/۰۱ شروع می‌شود و ظرفیت ۱۲۳۴۵ نفر اعلام شده است. جزئیات را همان منبع گفته."
    assert accept_draft(source, original)[0]
    dropped = "ثبت‌نام آزمون از اول مهر شروع می‌شود و ظرفیت اعلام شده است. جزئیات را همان منبع گفته."
    assert accept_draft(source, dropped)[1] == "dropped_numbers"


def test_slot_matches_tehran_hour_once():
    slot = PublishSlot(id="slot-1", hour=9, minute=0, enabled=True)
    morning = datetime(2026, 9, 25, 5, 32, tzinfo=timezone.utc)  # 09:02 Tehran
    assert slot_is_due(slot, morning, set())
    assert not slot_is_due(slot, morning, {"slot-1:2026-09-25"})
    later = datetime(2026, 9, 25, 6, 10, tzinfo=timezone.utc)
    assert not slot_is_due(slot, later, set())
    nxt = next_slot_time([slot], datetime(2026, 9, 25, 6, 0, tzinfo=timezone.utc))
    assert nxt is not None
    assert nxt.hour == 9


def test_layout_token_is_one_of_the_allowed_styles():
    assert parse_layout_token("scatter") == "scatter"
    assert parse_layout_token("list همین") == "list"
    assert parse_layout_token("یک توضیح بلند") is None
