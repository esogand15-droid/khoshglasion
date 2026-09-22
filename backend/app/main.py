from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
import logging
import json
from pathlib import Path

from backend.app.core.config import get_settings
from backend.app.logging_config.setup import setup_logging
from backend.app.db.base import Base, get_engine, get_db
from backend.app.api.auth import router as auth_router
from backend.app.api.channels import router as channels_router
from backend.app.api.emojis import router as emojis_router
from backend.app.api.styles import router as styles_router
from backend.app.api.messages import router as messages_router
from backend.app.api.preview import router as preview_router
from backend.app.api.dashboard import router as dashboard_router
from backend.app.api.system import router as system_router

settings = get_settings()
setup_logging(settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title="Khoshgelasion Bot", version="1.0.0", description="Telegram Channel Content Beautifier")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth_router)
app.include_router(channels_router)
app.include_router(emojis_router)
app.include_router(styles_router)
app.include_router(messages_router)
app.include_router(preview_router)
app.include_router(dashboard_router)
app.include_router(system_router)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "khoshgelasion"}

@app.get("/ready")
async def ready():
    # check DB
    try:
        from sqlalchemy import text
        from backend.app.db.base import get_session_factory
        factory = get_session_factory()
        async with factory() as s:
            await s.execute(text("SELECT 1"))
        return {"status": "ready", "db": "connected"}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "not_ready", "error": str(e)})

@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    # verify secret
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if settings.webhook_secret and secret != settings.webhook_secret:
        # allow if no secret configured, but if configured must match
        # For flexibility during dev, don't block if secret header missing but webhook_secret empty
        if settings.webhook_secret:
            raise HTTPException(status_code=403, detail="Invalid webhook secret")

    try:
        data = await request.json()
    except:
        return {"ok": False, "error": "invalid json"}

    # Handle channel_post
    update_id = data.get("update_id")
    channel_post = data.get("channel_post")
    edited_post = data.get("edited_channel_post")

    # Avoid loops: if edited_channel_post from bot itself, ignore
    target = channel_post or edited_post
    if edited_post and not channel_post:
        # This is an edit event — ignore to prevent loops
        logger.info(f"Ignoring edited_channel_post update_id={update_id}")
        return {"ok": True, "skipped": "edited_channel_post"}

    if not target:
        return {"ok": True, "skipped": "no_channel_post"}

    chat = target.get("chat", {})
    chat_id = chat.get("id")
    message_id = target.get("message_id")
    text = target.get("text")
    caption = target.get("caption")
    has_media = any(k in target for k in ["photo","video","animation","document","audio","voice"])
    media_type = None
    for k in ["photo","video","animation","document","audio","voice","sticker","poll"]:
        if k in target:
            media_type = k
            break
    # Skip non-editable
    if media_type in ["poll","sticker","location","contact"]:
        return {"ok": True, "skipped": f"non_editable_{media_type}"}

    # Process via pipeline
    from backend.app.db.base import get_session_factory
    from backend.app.telegram.pipeline import process_channel_post
    factory = get_session_factory()
    async with factory() as db:
        try:
            result = await process_channel_post(db, chat_id, message_id, text, caption, has_media, media_type)
            await db.commit()
            status = result.get("status")
            reason = result.get("reason", "")
            if status == "skipped":
                logger.info(f"Skipped chat={chat_id} msg={message_id} reason={reason} category={result.get('category')}")
            else:
                logger.info(f"Processed chat={chat_id} msg={message_id} result={status}")
            return {"ok": True, "result": result}
        except Exception as e:
            await db.rollback()
            logger.exception(f"Pipeline error chat={chat_id} msg={message_id}: {e}")
            return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

# Serve frontend static if exists
FRONTEND_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")
    # SPA fallback: serve index.html for any non-API non-telegram route
    from fastapi.responses import FileResponse as _FileResponse
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Don't intercept API / health / telegram routes
        if full_path.startswith(("api/", "telegram/", "health", "ready", "docs", "openapi.json", "redoc")):
            from fastapi import HTTPException as _HTTPException
            raise _HTTPException(status_code=404, detail="Not Found")
        index = FRONTEND_DIST / "index.html"
        if index.exists():
            return _FileResponse(index)
        from fastapi import HTTPException as _HTTPException2
        raise _HTTPException2(status_code=404, detail="Not Found")
else:
    @app.get("/")
    async def root_hint():
        return {"service": "khoshgelasion", "status": "ok", "hint": "Frontend not built. See /health and /docs", "docs": "/docs", "health": "/health"}

@app.on_event("startup")
async def on_startup():
    # Create tables via SQLAlchemy (SQLite: create_all, Postgres: also works)
    try:
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("DB tables ensured")
        # Seed admin if not exists
        from sqlalchemy import select
        from backend.app.models.admin import Admin
        from backend.app.security.auth import hash_password
        from backend.app.db.base import get_session_factory
        factory = get_session_factory()
        async with factory() as db:
            res = await db.execute(select(Admin).where(Admin.username=="admin"))
            if not res.scalar_one_or_none():
                # read admin_secret fresh (env may vary in Railway)
                secret = settings.admin_secret or "admin"
                admin = Admin(username="admin", password_hash=hash_password(secret), role="OWNER", display_name="Owner")
                db.add(admin)
                await db.commit()
                logger.info("Seeded admin user: admin")
            # Seed default emoji mappings if empty — rich premium pack
            from backend.app.models.emoji import EmojiMapping
            import json as _json
            from pathlib import Path as _Path
            er = await db.execute(select(EmojiMapping))
            if not er.scalars().first():
                # Try loading from JSON file, fallback to inline
                seed_path = _Path(__file__).parent / "data" / "premium_emoji_seed.json"
                if seed_path.exists():
                    try:
                        raw = _json.loads(seed_path.read_text(encoding="utf-8"))
                        count = 0
                        for item in raw:
                            db.add(EmojiMapping(
                                unicode_emoji=item["unicode_emoji"],
                                custom_emoji_id=str(item["custom_emoji_id"]),
                                category=item.get("category"),
                                priority=item.get("priority", 50),
                            ))
                            count += 1
                        await db.commit()
                        logger.info(f"Seeded {count} premium emojis from JSON")
                    except Exception as e:
                        logger.warning(f"Seed JSON failed {e}, using inline fallback")
                        raise
                else:
                    defaults = [
                        ("📢","5310129635848103696", "announcement"),
                        ("📚","5456140674028019486", "resource"),
                        ("🎯","5451732530048800190", "planning"),
                        ("📌","5413336461646094579", "consulting"),
                        ("🔥","5449629821362409862", "announcement"),
                        ("⭐","5431578537190158965", "motivational"),
                        ("⚡","5406936294728482210", "important"),
                        ("🎓","5454101630987654321", "education"),
                        ("📝","5454182070156793209", "exam"),
                        ("💡","5445284980978621388", "consulting"),
                        ("✅","5310129635848103696", "general"),
                        ("🎉","5454134413361802894", "general"),
                        ("🚀","5454321011540384215", "motivational"),
                        ("💪","5454124503608197814", "motivational"),
                        ("🏆","5454316894426412050", "rank"),
                        ("📅","5454193892721233456", "schedule"),
                        ("⏰","5445261246604338265", "schedule"),
                        ("❤️","5449554904909562107", "motivational"),
                        ("🔔","5445284980978621399", "announcement"),
                        ("🌟","5431578537190158977", "general"),
                        ("💎","5454154641799943274", "discount"),
                        ("🎁","5454154641799943275", "discount"),
                        ("✨","5431578537190158988", "general"),
                    ]
                    for uni, cid, cat in defaults:
                        db.add(EmojiMapping(unicode_emoji=uni, custom_emoji_id=cid, category=cat, priority=50))
                    await db.commit()
                    logger.info("Seeded default emojis (inline)")
    except Exception as e:
        logger.warning(f"Startup DB init failed: {e}")

    # Set webhook if configured
    if settings.bot_token and settings.webhook_url:
        try:
            from backend.app.telegram.bot import get_bot
            bot = get_bot()
            if bot:
                await bot.set_webhook(url=settings.webhook_url, secret_token=settings.webhook_secret or None, drop_pending_updates=True)
                logger.info(f"Webhook set: {settings.webhook_url}")
        except Exception as e:
            logger.warning(f"Set webhook failed: {e}")
