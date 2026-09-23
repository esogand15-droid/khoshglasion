from backend.app.formatting.category import detect_category
from backend.app.formatting.styles import style_is_enabled

def test_announcement():
    assert detect_category("#فوری فعالیت مدارس مجازی شد") == "announcement"

def test_news():
    assert detect_category("#خبر طبق مصوبه جدید") == "news"

def test_resource():
    assert detect_category("هر کتابی که معروفه انتخاب منبع") == "resource"

def test_general():
    assert detect_category("سلام وقت بخیر") == "general"


def test_disabled_custom_style_is_not_applied():
    assert style_is_enabled({"footer": "x", "enabled": False}) is False
    assert style_is_enabled("{\"enabled\": true}") is True
    assert style_is_enabled(None) is True


def test_exam_ad_qa_and_lesson():
    assert detect_category("این یک تست زیست است") == "exam"
    assert detect_category("تبلیغ همکاری با آموزشگاه") == "ad"
    assert detect_category("پرسش و پاسخ این هفته") == "qa"
    assert detect_category("نکته آموزشی فصل اول") == "lesson"
