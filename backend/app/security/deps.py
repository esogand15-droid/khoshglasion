from fastapi import Depends, HTTPException, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.db.base import get_db
from backend.app.security.auth import decode_token
from backend.app.models.admin import Admin

async def get_current_admin(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Admin:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ",1)[1]
    payload = decode_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    username = payload["sub"]
    res = await db.execute(select(Admin).where(Admin.username==username))
    admin = res.scalar_one_or_none()
    if not admin:
        raise HTTPException(status_code=401, detail="Admin not found")
    return admin

def require_role(*roles):
    async def checker(admin: Admin = Depends(get_current_admin)):
        if admin.role not in roles:
            raise HTTPException(status_code=403, detail="Forbidden")
        return admin
    return checker
