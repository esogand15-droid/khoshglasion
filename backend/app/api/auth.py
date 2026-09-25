from datetime import datetime, timezone
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.base import get_db
from backend.app.models.admin import Admin
from backend.app.schemas.auth import LoginRequest, LoginResponse
from backend.app.security.auth import hash_password, issue_token, verify_password
from backend.app.security.deps import get_current_admin
from backend.app.services.audit import write_audit

router = APIRouter(prefix="/api/auth", tags=["auth"])

_attempts: dict[str, list[float]] = {}
_global_failures: list[float] = []
_WINDOW = 600
_USER_LIMIT = 8
_GLOBAL_LIMIT = 40
_GLOBAL_WINDOW = 60


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


def _login_key(username: str) -> str:
    return (username or "").strip().lower()[:64] or "unknown"


def login_is_blocked(username: str) -> bool:
    """Limit by username, not proxy IP. Railway presents every user as one address."""
    now = time.time()
    global_window = [stamp for stamp in _global_failures if now - stamp < _GLOBAL_WINDOW]
    _global_failures[:] = global_window
    if len(global_window) >= _GLOBAL_LIMIT:
        return True
    key = _login_key(username)
    window = [stamp for stamp in _attempts.get(key, []) if now - stamp < _WINDOW]
    if window:
        _attempts[key] = window
    elif key in _attempts:
        _attempts.pop(key, None)
    if len(_attempts) > 500:
        oldest = sorted(_attempts, key=lambda item: _attempts[item][-1] if _attempts[item] else 0)[:200]
        for item in oldest:
            _attempts.pop(item, None)
    return len(window) >= _USER_LIMIT


def note_login_failure(username: str) -> None:
    now = time.time()
    _attempts.setdefault(_login_key(username), []).append(now)
    _global_failures.append(now)


def clear_login_failures(username: str) -> None:
    _attempts.pop(_login_key(username), None)


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    if login_is_blocked(payload.username):
        raise HTTPException(status_code=429, detail="تلاش زیاد. چند دقیقه بعد دوباره وارد شو.")
    admin = (await db.execute(select(Admin).where(Admin.username == payload.username))).scalar_one_or_none()
    if not admin or not verify_password(payload.password, admin.password_hash):
        note_login_failure(payload.username)
        raise HTTPException(status_code=401, detail="نام کاربری یا رمز اشتباه است")
    clear_login_failures(payload.username)
    admin.last_login_at = datetime.now(timezone.utc)
    await write_audit(db, admin=admin, action="login", resource="auth", ip_address=ip)
    token = issue_token(admin)
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
    admin.token_version = int(admin.token_version or 0) + 1
    await write_audit(db, admin=admin, action="password_change", resource="auth", ip_address=request.client.host if request.client else None)
    return {"ok": True, "access_token": issue_token(admin)}
