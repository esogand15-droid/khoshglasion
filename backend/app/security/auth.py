from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta, timezone
from backend.app.core.config import get_settings
import hashlib

# --- bcrypt 4.x compat: passlib expects bcrypt.__about__ ---
try:
    import bcrypt as _bcrypt
    if not hasattr(_bcrypt, "__about__"):
        import types
        _bcrypt.__about__ = types.SimpleNamespace(__version__=_bcrypt.__version__)
except ImportError:
    pass

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

def _truncate72(p: str) -> str:
    """Truncate to 72 bytes (bcrypt limit) safely on byte boundary."""
    b = p.encode("utf-8")
    if len(b) <= 72:
        return p
    # truncate on byte boundary then decode safely
    return b[:72].decode("utf-8", errors="ignore")

def hash_password(p: str) -> str:
    pw = _truncate72(p)
    return pwd_ctx.hash(pw)

def verify_password(plain: str, hashed: str) -> bool:
    pw = _truncate72(plain)
    # defensive: hashed may be corrupted
    try:
        return pwd_ctx.verify(pw, hashed)
    except Exception:
        return False

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
