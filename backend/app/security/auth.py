from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta, timezone
from backend.app.core.config import get_settings

# Workaround: bcrypt 4.x breaks passlib - we handle via direct bcrypt or sha256 fallback
try:
    import bcrypt as _bcrypt
    _has_bcrypt = True
    # monkey-patch for passlib compat
    if not hasattr(_bcrypt, "__about__"):
        import types
        _bcrypt.__about__ = types.SimpleNamespace(__version__=_bcrypt.__version__)
except ImportError:
    _has_bcrypt = False

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(p: str) -> str:
    # bcrypt max 72 bytes
    pw = p[:72] if len(p.encode("utf-8")) > 72 else p
    return pwd_ctx.hash(pw)

def verify_password(plain: str, hashed: str) -> bool:
    pw = plain[:72] if len(plain.encode("utf-8")) > 72 else plain
    return pwd_ctx.verify(pw, hashed)

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
