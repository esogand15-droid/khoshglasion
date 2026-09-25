from contextlib import asynccontextmanager
import asyncio
import hmac
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.automation import router as automation_router
from backend.app.api.auth import router as auth_router
from backend.app.api.channels import router as channels_router
from backend.app.api.dashboard import router as dashboard_router
from backend.app.api.emojis import router as emojis_router
from backend.app.api.messages import router as messages_router
from backend.app.api.preview import router as preview_router
from backend.app.api.styles import router as styles_router
from backend.app.api.system import router as system_router
from backend.app.core.config import get_settings
from backend.app.core.secrets import peek, refresh_secrets, resolved_webhook_url
from backend.app.db.bootstrap import bootstrap
from backend.app.logging_config.setup import setup_logging
from backend.app.telegram.bot import close_bot, get_bot
from backend.app.telegram.dispatch import process_update_safely, spawn
from backend.app.telegram.user_editor import close_user_client

settings = get_settings()
setup_logging(settings.log_level)
logger = logging.getLogger(__name__)

ALLOWED_UPDATES = [
    "channel_post",
    "edited_channel_post",
    "message",
    "edited_message",
    "my_chat_member",
    "callback_query",
]


async def setup_webhook() -> None:
    bot = get_bot()
    url = resolved_webhook_url()
    if not bot or not url:
        logger.warning("Webhook skipped: bot token or public URL is missing")
        return
    secret = peek("webhook_secret") or None
    try:
        await bot.set_webhook(
            url=url,
            secret_token=secret,
            drop_pending_updates=settings.drop_pending_updates,
            allowed_updates=ALLOWED_UPDATES,
        )
        logger.info("Webhook set: %s", url)
    except Exception as exc:
        logger.warning("Set webhook failed: %s", exc)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        await bootstrap()
    except Exception:
        logger.exception("Startup bootstrap failed")
    try:
        from backend.app.db.base import get_session_factory

        async with get_session_factory()() as session:
            await refresh_secrets(session)
    except Exception:
        logger.exception("Panel secret load failed")
    await setup_webhook()
    stop_automation = asyncio.Event()
    from backend.app.services.automation_runner import automation_loop
    automation_task = asyncio.create_task(automation_loop(stop_automation))
    yield
    stop_automation.set()
    automation_task.cancel()
    from backend.app.telegram.session_login import close_pending_login
    await close_pending_login()
    await close_user_client()
    await close_bot()


app = FastAPI(
    title="Khoshgelasion",
    version=settings.app_version,
    description="رتبه‌لند channel beautifier",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",")] if settings.cors_origins != "*" else ["*"],
    allow_credentials=settings.cors_origins != "*",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(automation_router)
app.include_router(channels_router)
app.include_router(emojis_router)
app.include_router(styles_router)
app.include_router(messages_router)
app.include_router(preview_router)
app.include_router(dashboard_router)
app.include_router(system_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "khoshgelasion", "version": settings.app_version}


@app.get("/ready")
async def ready():
    try:
        from sqlalchemy import text
        from backend.app.db.base import get_session_factory

        async with get_session_factory()() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as exc:
        return JSONResponse(status_code=503, content={"status": "not_ready", "error": str(exc)})


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    expected = peek("webhook_secret")
    if expected:
        provided = request.headers.get("X-Telegram-Bot-Api-Secret-Token") or ""
        if not hmac.compare_digest(provided, expected):
            raise HTTPException(status_code=403, detail="Invalid webhook secret")
    try:
        data = await request.json()
    except Exception:
        return {"ok": True, "skipped": "invalid_json"}
    if not isinstance(data, dict):
        return {"ok": True, "skipped": "invalid_payload"}
    # Ack Telegram immediately. Editing, AI and retries happen in the background
    # so a slow model cannot make Telegram retry the same post.
    spawn(process_update_safely(data))
    return {"ok": True}


FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND_DIST.exists():
    assets = FRONTEND_DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith(("api/", "telegram/", "health", "ready", "docs", "openapi.json", "redoc")):
            raise HTTPException(status_code=404, detail="Not Found")
        index = FRONTEND_DIST / "index.html"
        if index.exists():
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="Not Found")
else:
    @app.get("/")
    async def root_hint():
        return {
            "service": "khoshgelasion",
            "status": "ok",
            "hint": "Frontend is not built yet.",
            "docs": "/docs",
            "health": "/health",
        }
