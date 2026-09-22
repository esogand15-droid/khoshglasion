from backend.app.formatting.category import detect_category

def test_announcement():
    assert detect_category("#فوری فعالیت مدارس مجازی شد") == "announcement"

def test_news():
    assert detect_category("#خبر طبق مصوبه جدید") == "news"

def test_resource():
    assert detect_category("هر کتابی که معروفه انتخاب منبع") == "resource"

def test_general():
    assert detect_category("سلام وقت بخیر") == "general"
