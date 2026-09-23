"""Normalize Railway / Heroku / Neon Postgres URLs for asyncpg + psycopg."""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse


def _split_query(url: str) -> tuple[str, dict[str, str]]:
    if "?" not in url:
        return url, {}
    base, query = url.split("?", 1)
    return base, dict(parse_qsl(query, keep_blank_values=True))


def _host_of(sqlalchemy_url: str) -> str:
    try:
        normalized = sqlalchemy_url
        for prefix in ("postgresql+asyncpg", "postgresql+psycopg", "postgresql+psycopg2"):
            if normalized.startswith(prefix):
                normalized = "postgresql" + normalized[len(prefix):]
                break
        return (urlparse(normalized).hostname or "").lower()
    except Exception:
        return ""


def _is_internal_host(host: str) -> bool:
    if not host:
        return False
    return host in {"localhost", "127.0.0.1", "db", "postgres"} or host.endswith(".railway.internal") or host.endswith(".internal")


def normalize_async_url(url: str | None) -> tuple[str, dict]:
    """Return (async SQLAlchemy URL, connect_args).

    Railway gives ``postgresql://`` or ``postgres://``. asyncpg does not
    understand ``sslmode``, so that flag is translated into connect_args.
    """
    raw = (url or "").strip()
    if not raw:
        raw = "sqlite+aiosqlite:///./data/khoshgelasion.db"

    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://"):]
    if raw.startswith("postgresql+psycopg2://"):
        raw = "postgresql+asyncpg://" + raw[len("postgresql+psycopg2://"):]
    elif raw.startswith("postgresql+psycopg://"):
        raw = "postgresql+asyncpg://" + raw[len("postgresql+psycopg://"):]
    elif raw.startswith("postgresql://"):
        raw = "postgresql+asyncpg://" + raw[len("postgresql://"):]

    base, query = _split_query(raw)
    connect_args: dict = {}
    if "asyncpg" in base:
        sslmode = (query.pop("sslmode", "") or query.pop("ssl", "")).lower()
        query.pop("channel_binding", None)
        host = _host_of(base)
        if sslmode in {"require", "verify-ca", "verify-full", "true", "1"} and not _is_internal_host(host):
            connect_args["ssl"] = True
        elif sslmode in {"disable", "allow", "prefer", "false", "0"} or _is_internal_host(host):
            connect_args["ssl"] = False
        if query:
            base = base + "?" + urlencode(query)
        return base, connect_args

    if query:
        base = base + "?" + urlencode(query)
    return base, connect_args


def normalize_sync_url(url: str | None) -> str:
    """Sync URL for Alembic. Uses psycopg v3, which understands sslmode."""
    raw = (url or "").strip()
    if not raw:
        raw = "sqlite:///./data/khoshgelasion.db"
    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://"):]
    if raw.startswith("postgresql+asyncpg://"):
        raw = "postgresql+psycopg://" + raw[len("postgresql+asyncpg://"):]
    elif raw.startswith("postgresql://"):
        raw = "postgresql+psycopg://" + raw[len("postgresql://"):]
    elif raw.startswith("sqlite+aiosqlite://"):
        raw = "sqlite://" + raw[len("sqlite+aiosqlite://"):]
    return raw


def driver_name(url: str | None) -> str:
    raw = (url or "").lower()
    if raw.startswith("postgres") or "asyncpg" in raw or "+psycopg" in raw:
        return "postgresql"
    if "sqlite" in raw:
        return "sqlite"
    return "other"


def is_external_database(url: str | None) -> bool:
    return driver_name(url) == "postgresql"
