import httpx
import logging
import hashlib
import json
from typing import Optional, Dict, List
from backend.app.core.config import get_settings

logger = logging.getLogger(__name__)

# Track recent outputs for anti-repetition
_recent_hashes: List[str] = []
_MAX_HISTORY = 50

def _content_hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:12]

def _is_repetitive(text: str) -> bool:
    h = _content_hash(text)
    return h in _recent_hashes

def _record_output(text: str):
    h = _content_hash(text)
    _recent_hashes.append(h)
    if len(_recent_hashes) > _MAX_HISTORY:
        _recent_hashes.pop(0)

# Category-specific prompt templates for Konkuri style
CATEGORY_PROMPTS = {
    "announcement": """شما کپشن‌نویس حرفه‌ای کانال تلگرام «رتبه لند» (مشاوره کنکور) هستید.
متن زیر یک «اطلاعیه مهم» است. آن را بازنویسی کنید با:
- تیتر جذاب با ایموجی ⚡📢
- لحن رسمی اما صمیمی و معتبر
- ساختار: تیتر → متن اصلی → نکات کلیدی → دعوت به اقدام
- ایموجی‌های پرمیوم طبیعی در متن (نه در انتهای همه جملات)
- فوتر استاندارد کانال در آخر اضافه می‌شود (نیازی به اضافه کردن ندارید)
- از تکرار عبارات کلیشه‌ای خودداری کنید
- حداکثر ۳-۴ پاراگراف، خوانا و اسکن‌پذیر

متن اصلی:
{text}""",

    "exam": """شما کپشن‌نویس کانال «رتبه لند» هستید. متن زیر درباره «آزمون/کنکور/نمونه سوال» است.
بازنویسی با سبک:
- تیتر تخصصی 🎯📝
- نکات طلایی/نکته کلیدی با بولت‌پوینت‌های جذاب
- لحن مشجع،減壓‌کننده، و راهبردی
- مثال یا نکته عملی حتما داشته باشد
- ساختار: تیتر → نکته اصلی → جزئیات/نکات → تمرین پیشنهادی → فوتر
- ایموجی‌های تخصصی (📝✏️🎯📊💡) در جایگاه‌های درست
- جلوگیری از لحن خشک اداری

متن اصلی:
{text}""",

    "resource": """شما کپشن‌نویس کانال «رتبه لند» هستید. متن زیر «معرفی منبع/کتاب/جزوه» است.
بازنویسی جذاب با:
- تیتر: 📚 معرفی منبع + نام منبع
- چرا این منبع خوبه؟ (۳ دلیل قانع‌کننده)
- برای چه کسی مناسبه؟ (هدف/سطح)
- نکته خرید/دسترسی/قیمت اگر هست
- مقایسه کوتاه با رقبا اگر relevants
- لحن مشاوره‌دهنده دوست‌داشتنی، نه فروشنده
- ایموجی‌های کتاب/دانش/پیشرفت

متن اصلی:
{text}""",

    "motivational": """شما کپشن‌نویس کانال «رتبه لند» هستید. متن زیر «انگیزشی/حماسی» است.
بازنویسی با روح کنکوری واقعی:
- تیتر قدرتمند ✨💪🔥
- داستان کوتاه/چالش واقعی/نقل قولNZ
- نکته عملی برای فردا صبح
- لحن: هم‌دل، قوی، واقعی (نه کلیشه‌های اینستاگرامی)
- پایان‌بند با اقدام کوچک قابل انجام
- ایموجی‌های انرژی/رشد/پیروزی در لحظه‌های کلیدی

متن اصلی:
{text}""",

    "consulting": """شما کپشن‌نویس کانال «رتبه لند» هستید. متن زیر درباره «مشاوره/برنامه‌ریزی/راهنمایی» است.
بازنویسی مشاوره‌گرانه:
- تیتر: 🎓 مشاوره تخصصی + موضوع
- تحلیل مسئله از نگاه دانش‌آموز
- ۳ راهکار عملی قدم‌به‌قدم
- نکته طلایی از تجربه مشاوران رتبه لند
- CTA طبیعی برای رزرو مشاوره
- لحن متخصص، مهربان، قابل اعتماد

متن اصلی:
{text}""",

    "news": """شما کپشن‌نویس کانال «رتبه لند» هستید. متن زیر «خبر/اعلامیه رسمی/تغییرات کنکور» است.
بازنویسی خبری حرفه‌ای:
- تیتر خبری 📰⚡
- خلاصه خبر در ۱ خط (Lead)
- جزئیات مهم: چی، کی، کی اثر می‌گذارد، چه باید کرد
- تحلیل تأثیر روی داوطلبان
- اقدام فوری اگر لازم است
- لحن خبری، دقیق، بی‌طرف اما حامی دانش‌آموز

متن اصلی:
{text}""",

    "planning": """شما کپشن‌نویس کانال «رتبه لند» هستید. متن زیر «برنامه‌ریزی/تقویم/استراتژی مطالعه» است.
بازنویسی استراتژیک:
- تیتر: 🗓️ برنامه/استراتژی + بازه زمانی
- اصل کلیدی برنامه‌ریزی
- تقسیم‌بندی هفته/ماه (البته خلاصه)
- تکنیک مطالعه پیشنهادی
- پرریه‌های رایج و راه‌حل
- قالب قابل ذخیره/اسکرین‌شات

متن اصلی:
{text}""",

    "rank": """شما کپشن‌نویس کانال «رتبه لند» هستید. متن زیر درباره «رتبه/نتیجه/موفقیت/آمار» است.
بازنویسی با تمرکز بر امید و راهکار:
- تیتر: 🏆 رتبه/موفقیت + عدد/آمار کلیدی
- تحلیل چی باعث این نتیجه شده
- الگوی قابل تکرار برای دیگران
- نکته manj کتبی/غیرکتبی
- پیام امید برای کسانی که هنوز نرسیده‌اند
- لحن تحسین‌کننده اما واقع‌بینانه

متن اصلی:
{text}""",

    "discount": """شما کپشن‌نویس کانال «رتبه لند» هستید. متن زیر «تخفیف/کمپین/فرصت ویژه» است.
بازنویسی بدون حس فروشی:
- تیتر: 🎁 فرصت ویژه / تخفیف + نام خدمت
- ارزش واقعی برای دانش‌آموز (نه قیمت)
- چرا الان؟ (دلیل منطقی)
- جزئیات شفاف: چه می‌گیرید، تا کی، چطور
- مقایسه با قیمت واقعی
- CTA با حس اکسیژن‌دهی، نه فشار

متن اصلی:
{text}""",

    "general": """شما کپشن‌نویس کانال «رتبه لند» (مشاوره کنکور) هستید.
متن زیر را برای پست کانال بازنویسی کنید:
- تیتر جذاب با ایموجی مرتبط
- ساختار منظم: مقدمه → بدنه اصلی → جمع‌بندی/عملی
- لحن: صمیمی، تخصصی، مشجع، غیرکلیشه‌ای
- ایموجی‌های پرمیوم در جاهای استراتژیک (تیتر، نکات کلیدی، انتقالات)
- فوتر استاندارد در آخر جداگانه اضافه می‌شود
- جلوگیری از تکرار الگوهای قبلی
- حداکثر ۴۰۰۰ کاراکتر، قابل اسکن

متن اصلی:
{text}""",
}

def _build_prompt(text: str, category: str, previous_context: str = "") -> str:
    """Build intelligent prompt based on category and context."""
    template = CATEGORY_PROMPTS.get(category, CATEGORY_PROMPTS["general"])
    prompt = template.format(text=text)
    
    # Anti-repetition guidance
    if _recent_hashes:
        prompt += "\n\n⚠️ مهم: از الگوهای تکراری در پست‌های قبلی خودداری کنید. تنوع در تیترها، واژگان، و ساختار جملات ایجاد کنید."
    
    # Add context if available
    if previous_context:
        prompt += f"\n\n📝 بافت قبلی (برای انسجام): {previous_context[:200]}"
    
    return prompt

async def enhance_with_ai(text: str, category: str = "general", previous_context: str = "") -> Optional[str]:
    """
    Intelligently enhance/rewrite content for Konkuri channel.
    Returns enhanced text or None if AI fails/disabled.
    """
    s = get_settings()
    if not s.ai_enabled or not s.ai_base_url or not s.ai_model or not s.ai_api_key:
        return None
    
    # Build smart prompt
    prompt = _build_prompt(text, category, previous_context)
    
    headers = {
        "Authorization": f"Bearer {s.ai_api_key}",
        "Content-Type": "application/json",
    }
    
    # OpenAI-compatible payload with optimized params
    payload = {
        "model": s.ai_model,
        "messages": [
            {"role": "system", "content": "You are the expert content writer for 'RankLand' (رتبه لند) - Iran's premier Konkur counseling Telegram channel. Rewrite content in professional, engaging, emoji-rich Konkuri style. Never use clichés. Vary structure and vocabulary every time. Output ONLY the enhanced Persian text, no explanations."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.85,  # Higher for creativity/variation
        "top_p": 0.95,
        "max_tokens": 2500,
        "presence_penalty": 0.3,  # Discourage repetition
        "frequency_penalty": 0.3,
    }
    
    url = s.ai_base_url.rstrip("/") + "/v1/chat/completions"
    
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            
            if content and len(content) > 20:
                # Anti-repetition check
                if _is_repetitive(content):
                    logger.warning("AI output detected as repetitive, trying once more with higher temperature...")
                    payload["temperature"] = 0.95
                    resp2 = await client.post(url, json=payload, headers=headers)
                    resp2.raise_for_status()
                    data2 = resp2.json()
                    content = data2.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                
                _record_output(content)
                logger.info(f"AI enhanced: category={category}, len={len(content)}, tokens≈{len(content)//3}")
                return content
            else:
                logger.warning("AI returned empty/short content")
    except httpx.HTTPStatusError as e:
        logger.error(f"AI API error {e.response.status_code}: {e.response.text[:200]}")
    except httpx.TimeoutException:
        logger.error("AI request timeout (45s)")
    except Exception as e:
        logger.error(f"AI call failed: {type(e).__name__}: {e}")
    return None

async def test_ai_connection() -> dict:
    """Test AI connection with a simple prompt."""
    s = get_settings()
    if not s.ai_enabled or not s.ai_base_url or not s.ai_model or not s.ai_api_key:
        return {"ok": False, "error": "AI not configured"}
    
    headers = {
        "Authorization": f"Bearer {s.ai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": s.ai_model,
        "messages": [{"role": "user", "content": "سلام، تست اتصال"}],
        "max_tokens": 10,
    }
    url = s.ai_base_url.rstrip("/") + "/v1/chat/completions"
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                return {"ok": True, "model": s.ai_model}
            return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

async def enhance_preview(text: str, category: str = "general") -> dict:
    """For preview panel - returns both original and enhanced."""
    enhanced = await enhance_with_ai(text, category)
    return {
        "original": text,
        "enhanced": enhanced,
        "category": category,
        "ai_used": enhanced is not None,
    }

