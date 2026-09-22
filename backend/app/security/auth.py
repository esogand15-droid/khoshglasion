from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta, timezone
from backend.app.core.config import get_settings

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(p: str) -> str:
    return pwd_ctx.hash(p)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)

def create_token(data: dict, expires_minutes: int | None = None) -> str:
    s = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes or s.jwt_expire_minutes)
    to_encode = {**data, "exp": exp}
    return jwt.encode(to_encode, s.jwt_secret, algorithm="HS256")

def decode_token(token: str) -> dict | None:
    s = get_settings()
    try:
        return jwt.decode(token, s.jwt_secret, algorithms=["HS256"])
    except Exception:
        return None
