from backend.app.db.url import is_external_database, normalize_async_url, normalize_sync_url


def test_railway_postgres_url_becomes_asyncpg():
    url, args = normalize_async_url("postgres://user:pass@postgres.railway.internal:5432/railway")
    assert url.startswith("postgresql+asyncpg://")
    assert "railway.internal" in url
    assert args.get("ssl") is False


def test_public_sslmode_is_not_left_in_async_url():
    url, args = normalize_async_url("postgresql://user:pass@db.example.com:5432/app?sslmode=require")
    assert "sslmode" not in url
    assert args.get("ssl") is True


def test_sync_url_uses_psycopg():
    assert normalize_sync_url("postgresql+asyncpg://u:p@h/db").startswith("postgresql+psycopg://")
    assert normalize_sync_url("sqlite+aiosqlite:///./data/x.db").startswith("sqlite:///")


def test_sqlite_is_not_external():
    assert is_external_database("sqlite+aiosqlite:///./data/khoshgelasion.db") is False
    assert is_external_database("postgresql://u:p@h/db") is True
