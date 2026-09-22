# خوشگلاسیون — Khoshgelasion Bot ✨

> «هر پست، یکم خوشگل‌تر» — ربات هوشمند زیباسازی محتوای کانال تلگرام برای مشاوره کنکور

ربات به‌عنوان ادمین کانال، هر پست جدید را دریافت کرده، بدون تغییر معنایی، آن را مرتب و برندشده می‌کند، ایموجی‌ها را به Custom Emoji تبدیل می‌کند و همان پیام را Edit می‌کند. پنل مدیریتی شیشه‌ای (Glassmorphism) دارد.

---

## ویژگی‌ها

- دریافت `channel_post` via Webhook (FastAPI) — Polling فقط برای dev
- تشخیص نوع پیام (text / photo+caption / video+caption / ...) و Skip هوشمند برای Poll/Sticker
- موتور Formatting مستقل: فاصله‌گذاری، نرمال‌سازی بولت‌ها، Divider و Footer برند
- موتور Emoji با `custom_emoji_id` و `<tg-emoji>` — context-aware
- تشخیص دستهٔ محتوا (اطلاعیه/خبر/منبع/انگیزشی/…)
- Idempotency با hash — جلوگیری از حلقهٔ ادیت
- Dry Run و Kill Switch
- Retry با backoff برای 429
- داشبورد RTL شیشه‌ای: آمار، کانال‌ها، پیام‌ها، ایموجی، استایل، پیش‌نمایش زنده، سلامت سیستم

---

## معماری

```
Telegram Channel → Bot API → POST /telegram/webhook → FastAPI
  → validate channel allowlist → idempotency check
  → detect category → format engine → emoji engine
  → validate limits → editMessageText / editMessageCaption
  → save MessageLog
                    ↕
              PostgreSQL (prod) / SQLite (dev)
              SQLAlchemy 2 async + Alembic
                    ↕
              React + Vite + Tailwind Dashboard
```

---

## شروع سریع (Local)

```bash
cp .env.example .env
# BOT_TOKEN را از @BotFather بگیر و در .env بگذار

pip install -r backend/requirements.txt

# DB (SQLite برای dev کافی است)
DATABASE_URL=sqlite+aiosqlite:///./khoshgelasion.db alembic upgrade head

uvicorn backend.app.main:app --reload --port 8000
# Frontend (اختیاری)
cd frontend && npm install && npm run dev
```

پنل: http://localhost:8000  (اگر frontend build شده باشد) یا http://localhost:5173
ورود: `admin` / مقدار `ADMIN_SECRET` در .env

### Polling برای تست بدون Webhook

```bash
python -m backend.app.bot.polling  # اگر اسکریپت polling اضافه کردی
```
یا از `ngrok` برای Webhook لوکال استفاده کن.

---

## متغیرهای محیطی

| نام | توضیح |
|---|---|
| `BOT_TOKEN` | توکن از @BotFather |
| `BOT_USERNAME` | یوزرنیم بات |
| `DATABASE_URL` | `postgresql+asyncpg://...` یا `sqlite+aiosqlite:///...` |
| `WEBHOOK_URL` | `https://domain/telegram/webhook` |
| `WEBHOOK_SECRET` | رشتهٔ تصادفی ≥32 کاراکتر |
| `ADMIN_SECRET` | رمز ادمین اولیه |
| `SESSION_SECRET` / `JWT_SECRET` | کلید JWT |
| `DRY_RUN` | `true` → هیچ پیامی واقعاً ادیت نمی‌شود |
| `KILL_SWITCH` | `true` → پردازش کاملاً متوقف |
| `MAX_CONCURRENT_PROCESSING` | همزمانی (پیش‌فرض 5) |

---

## راه‌اندازی تلگرام

1. @BotFather → `/newbot` → توکن بگیر
2. `.env` را پر کن و Deploy کن
3. `WEBHOOK_URL` را تنظیم کن — در startup خودکار `setWebhook` می‌شود
4. ربات را به کانال به‌عنوان **Admin** اضافه کن (مجوز *Edit messages*)
5. در پنل → کانال‌ها → `Chat ID` کانال را اضافه کن (از لاگ webhook یا @userinfobot)
6. در **Dry Run** تست کن، سپس غیرفعال کن
7. در **پیش‌نمایش زنده** متن‌های مختلف را تست کن
8. در **کتابخانه ایموجی** Custom Emoji IDها را وارد کن

برای گرفتن `custom_emoji_id`: یک custom emoji در تلگرام بفرست و از `getCustomEmojiStickers` یا لاگ بات ID را استخراج کن.

---

## محدودیت‌های تلگرام

- متن: 4096 کاراکتر، کپشن: 1024
- Poll / Sticker / Location / Contact قابل Edit نیست — Skip می‌شود
- پیام‌های خیلی قدیمی ممکن است قابل Edit نباشند
- Custom Emoji فقط با ID معتبر نمایش داده می‌شود
- Rate limit با backoff مدیریت می‌شود

---

## استقرار Railway

- `Dockerfile` آماده است — Railway خودکار build می‌کند
- `railway.toml` شامل healthcheck است
- متغیرها را در Railway Variables تنظیم کن
- `DATABASE_URL` توسط Postgres addon خودکار پر می‌شود (اگر `postgresql+asyncpg` باشد)
- `alembic upgrade head` در `CMD` خودکار اجرا می‌شود

---

## تست

```bash
pytest tests/ -v
```

---

## لایسنس

MIT
