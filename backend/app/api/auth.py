from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.db.base import get_db
from backend.app.schemas.auth import LoginRequest, LoginResponse
from backend.app.models.admin import Admin
from backend.app.security.auth import verify_password, create_token
from backend.app.security.deps import get_current_admin
from datetime import datetime, timezone

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Admin).where(Admin.username==payload.username))
    admin = res.scalar_one_or_none()
    if not admin or not verify_password(payload.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    admin.last_login_at = datetime.now(timezone.utc)
    await db.flush()
    token = create_token({"sub": admin.username, "role": admin.role})
    return LoginResponse(access_token=token, role=admin.role, username=admin.username)

@router.get("/me")
async def me(admin: Admin = Depends(get_current_admin)):
    return {"username": admin.username, "role": admin.role, "display_name": admin.display_name}
