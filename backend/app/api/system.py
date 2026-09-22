from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.app.db.base import get_db
from backend.app.models.admin import Admin
from backend.app.security.deps import get_current_admin
from backend.app.core.config import get_settings
from backend.app.db.base import get_engine
from sqlalchemy import text

router = APIRouter(prefix="/api/system", tags=["system"])

@router.get("/health")
async def system_health(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    s = get_settings()
    # db check
    db_ok = False
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        db_ok = False
    # bot check
    from backend.app.telegram.bot import get_bot
    bot = get_bot()
    bot_ok = bot is not None and bool(s.bot_token)
    return {
        "database": "connected" if db_ok else "disconnected",
        "bot": "connected" if bot_ok else "not_configured",
        "webhook": s.webhook_url or "not_set",
        "dry_run": s.dry_run,
        "safe_mode": s.safe_mode,
        "kill_switch": s.kill_switch,
        "env": s.app_env,
    }

@router.get("/settings")
async def get_settings_api(admin=Depends(get_current_admin)):
    s = get_settings()
    return {
        "dry_run": s.dry_run,
        "safe_mode": s.safe_mode,
        "kill_switch": s.kill_switch,
        "webhook_url": s.webhook_url,
        "app_env": s.app_env,
    }

@router.get("/logs")
async def get_logs(limit: int = 100, admin=Depends(get_current_admin)):
    # return audit logs
    from backend.app.models.audit import AuditLog
    from backend.app.db.base import get_db
    # need db
    return {"note": "use /api/messages for processing logs"}

@router.get("/admins")
async def list_admins(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    res = await db.execute(select(Admin))
    items = res.scalars().all()
    return [{"id":a.id,"username":a.username,"role":a.role,"display_name":a.display_name,"created_at": a.created_at.isoformat() if a.created_at else None} for a in items]
