from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.app.db.base import get_db
from backend.app.models.admin import Admin
from backend.app.security.deps import get_current_admin
from backend.app.core.config import get_settings
from backend.app.db.base import get_engine
from backend.app.services.ai import test_ai_connection, enhance_with_ai
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



@router.get("/ai/config")
async def get_ai_config(admin=Depends(get_current_admin)):
    s = get_settings()
    return {
        "enabled": s.ai_enabled,
        "base_url": s.ai_base_url,
        "model": s.ai_model,
        "api_key_set": bool(s.ai_api_key),
        "prompt_template": s.ai_prompt_template,
    }

@router.post("/ai/config")
async def update_ai_config(
    enabled: bool = False,
    base_url: str = "",
    model: str = "",
    api_key: str = "",
    prompt_template: str = "",
    admin=Depends(get_current_admin)
):
    from backend.app.db.base import get_async_session
    from backend.app.models.system import SystemSetting
    from sqlalchemy import select
    from backend.app.core.config import get_settings
    
    s = get_settings()
    settings_map = {
        "ai_enabled": str(enabled).lower(),
        "ai_base_url": base_url,
        "ai_model": model,
        "ai_api_key": api_key,
        "ai_prompt_template": prompt_template or s.ai_prompt_template,
    }
    
    async for session in get_async_session():
        for k, v in settings_map.items():
            res = await session.execute(select(SystemSetting).where(SystemSetting.key == k))
            row = res.scalar_one_or_none()
            if row:
                row.value = v
            else:
                session.add(SystemSetting(key=k, value=v, description=f"AI setting: {k}"))
        await session.commit()
    
    return {"ok": True, "message": "AI config updated. Restart may be required for some settings."}

@router.post("/ai/test")
async def test_ai(admin=Depends(get_current_admin)):
    result = await test_ai_connection()
    return result

@router.post("/ai/enhance")
async def enhance_text(text: str, category: str = "general", admin=Depends(get_current_admin)):
    """Test AI enhancement on a sample text."""
    result = await enhance_with_ai(text, category)
    return {"enhanced": result, "original": text}


@router.get("/admins")
async def list_admins(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    res = await db.execute(select(Admin))
    items = res.scalars().all()
    return [{"id":a.id,"username":a.username,"role":a.role,"display_name":a.display_name,"created_at": a.created_at.isoformat() if a.created_at else None} for a in items]
