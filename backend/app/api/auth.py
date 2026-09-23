from datetime import datetime, timezone
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.base import get_db
from backend.app.models.admin import Admin
from backend.app.schemas.auth import LoginRequest, LoginResponse
from backend.app.security.auth import create_token, hash_password, verify_password
from backend.app.security.deps import get_current_admin
from backend.app.services.audit import write_audit

router = APIRouter(prefix="/api/auth", tags=["auth"])

_attempts: dict[str, list[float]] = {}


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


def _too_many(ip: str) -> bool:
    now = time.time()
    window = [stamp for stamp in _attempts.get(ip, []) if now - stamp < 600]
    _attempts[ip] = window
    if len(window) >= 8:
        return True
    window.append(now)
    return False


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    if _too_many(ip):
        raise HTTPException(status_code=429, detail="تلاش زیاد. چند دقیقه بعد دوباره وارد شو.")
    admin = (await db.execute(select(Admin).where(Admin.username == payload.username))).scalar_one_or_none()
    if not admin or not verify_password(payload.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="نام کاربری یا رمز اشتباه است")
    admin.last_login_at = datetime.now(timezone.utc)
    await write_audit(db, admin=admin, action="login", resource="auth", ip_address=ip)
    token = create_token({"sub": admin.username, "role": admin.role})
    return LoginResponse(access_token=token, role=admin.role, username=admin.username)


@router.get("/me")
async def me(admin: Admin = Depends(get_current_admin)):
    return {
        "username": admin.username,
        "role": admin.role,
        "display_name": admin.display_name,
        "telegram_id": admin.telegram_id,
    }


@router.post("/password")
async def change_password(payload: PasswordChange, request: Request, db: AsyncSession = Depends(get_db), admin: Admin = Depends(get_current_admin)):
    if not verify_password(payload.current_password, admin.password_hash):
        raise HTTPException(status_code=400, detail="رمز فعلی اشتباه است")
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="رمز جدید حداقل ۸ کاراکتر باشد")
    admin.password_hash = hash_password(payload.new_password)
    await write_audit(db, admin=admin, action="password_change", resource="auth", ip_address=request.client.host if request.client else None)
    return {"ok": True}
