CATEGORIES = [
    "announcement", "news", "consulting", "motivational", "planning",
    "resource", "book", "exam", "registration", "schedule", "school",
    "konkur", "major_choice", "rank", "discount", "ad", "qa", "general",
    "solution", "experience", "class_intro", "product", "occasion", "service",
]

PRIORITY: list[tuple[list[str], str]] = [
    (["پاسخ تشریحی", "پاسخنامه تشریحی", "گزینه صحیح"], "solution"),
    (["تجربه رتبه برتر", "از زبان رتبه"], "experience"),
    (["معرفی کلاس", "کلاس آنلاین"], "class_intro"),
    (["پکیج", "محصول آموزشی"], "product"),
    (["تبریک", "مناسبت", "عید"], "occasion"),
    (["رزرو مشاوره", "مشاوره خصوصی"], "service"),
]

RULES: list[tuple[list[str], str]] = [
    (["#فوری", "فوری", "اطلاعیه", "مهم", "اعلام", "تعطیل", "مجازی شد", "خبر فوری"], "announcement"),
    (["#خبر", "خبر", "طبق مصوبه", "تغییر یافت", "اعلام شد", "مصوبه", "سازمان سنجش"], "news"),
    (["منبع", "کتاب", "جزوه", "معرفی منبع", "منابع", "انتخاب منبع", "درسنامه"], "resource"),
    (["برنامه", "برنامه‌ریزی", "برنامه ریزی", "زمان‌بندی", "بودجه بندی", "بودجه‌بندی"], "planning"),
    (["انگیزشی", "تلاش", "مسیر", "انگیزه", "نقل قول", "ناامید", "شروع کن"], "motivational"),
    (["آزمون", "قلم‌چی", "قلم چی", "امتحان", "کنکور", "ماز", "گزینه دو", "گاج", "تست‌زنی", "تست زنی", "جمع‌بندی", "جمع بندی"], "exam"),
    (["ثبت‌نام", "ثبت نام", "نام‌نویسی"], "registration"),
    (["مدرسه", "مدارس", "آموزش و پرورش", "کلاس"], "school"),
    (["انتخاب رشته", "رشته", "کنکور سراسری"], "major_choice"),
    (["رتبه", "کارنامه", "تراز", "درصد"], "rank"),
    (["تخفیف", "٪", "درصد تخفیف", "حراج", "کد تخفیف"], "discount"),
    (["مشاوره", "چطور", "چگونه", "چرا", "آیا", "ویس"], "consulting"),
]


def detect_category(text: str | None) -> str:
    if not text:
        return "general"
    folded = text.lower()
    for keywords, category in PRIORITY:
        if any(keyword.lower() in folded for keyword in keywords):
            return category
    scores: dict[str, int] = {}
    for keywords, category in RULES:
        for keyword in keywords:
            if keyword.lower() in folded:
                scores[category] = scores.get(category, 0) + 1
    if not scores:
        return "general"
    return max(scores, key=lambda key: scores[key])
