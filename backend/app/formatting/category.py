import re

CATEGORIES = [
    "announcement","news","consulting","motivational","planning",
    "resource","book","exam","registration","schedule","school",
    "konkur","major_choice","rank","discount","ad","qa","general"
]

# Rule-based detection: keywords -> category
RULES: list[tuple[list[str], str]] = [
    (["#فوری","فوری","اطلاعیه","مهم","اعلام","تعطیل","مجازی شد","خبر فوری"], "announcement"),
    (["#خبر","خبر","طبق مصوبه","تغییر یافت","اعلام شد","مصوبه"], "news"),
    (["منبع","کتاب","جزوه","معرفی منبع","منابع","انتخاب منبع"], "resource"),
    (["برنامه","برنامه‌ریزی","برنامه ریزی","زمان‌بندی"], "planning"),
    (["انگیزشی","تلاش","مسیر","انگیزه","نقل قول","زیبا خواهد بود"], "motivational"),
    (["آزمون","قلم‌چی","قلم چی","امتحان","کنکور","آزمون "], "exam"),
    (["ثبت‌نام","ثبت نام","نام‌نویسی"], "registration"),
    (["مدرسه","مدارس","آموزش و پرورش","کلاس"], "school"),
    (["انتخاب رشته","رشته","کنکور سراسری"], "major_choice"),
    (["رتبه","کارنامه","تراز","درصد"], "rank"),
    (["تخفیف","٪","درصد تخفیف","حراج"], "discount"),
    (["مشاوره","چطور","چگونه","چرا","آیا"], "consulting"),
]

def detect_category(text: str | None) -> str:
    if not text:
        return "general"
    t = text.lower()
    scores: dict[str,int] = {}
    for keywords, cat in RULES:
        for kw in keywords:
            if kw.lower() in t:
                scores[cat] = scores.get(cat, 0) + 1
    if not scores:
        # fallback: if has voice/waveform hint words
        if "ویس" in t or "گوش بده" in t:
            return "consulting"
        return "general"
    return max(scores, key=lambda k: scores[k])
