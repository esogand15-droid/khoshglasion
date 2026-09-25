"""Add columns the running models expect, without wiping existing data.

Alembic's first revision created INTEGER chat ids. Telegram channel ids do not
fit in Postgres INTEGER, and every Railway redeploy used to throw the SQLite
file away. This sync is idempotent on both Postgres and SQLite.
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from backend.app.db.base import Base, get_engine

logger = logging.getLogger(__name__)


def _bool(connection: Connection, default: bool) -> str:
    if connection.dialect.name == "postgresql":
        return "BOOLEAN DEFAULT true" if default else "BOOLEAN DEFAULT false"
    return "INTEGER DEFAULT 1" if default else "INTEGER DEFAULT 0"


def _columns_for(connection: Connection) -> dict[str, dict[str, str]]:
    return {
        "admins": {
            "telegram_id": "BIGINT",
        },
        "channels": {
            "ai_rewrite": "BOOLEAN",
            "edit_delay_seconds": "INTEGER",
            "signature_text": "VARCHAR(64)",
            "signature_url": "VARCHAR(512)",
            "skip_keywords": "TEXT",
            "min_chars": "INTEGER DEFAULT 1",
            "preserve_buttons": _bool(connection, True),
            "notes": "TEXT",
            "posts_edited": "INTEGER DEFAULT 0",
            "last_error": "TEXT",
            "last_post_at": "TIMESTAMP",
            "can_edit": _bool(connection, True),
        },
        "message_logs": {
            "html_text": "TEXT",
            "ai_used": _bool(connection, False),
            "attempt_count": "INTEGER DEFAULT 0",
            "edit_method": "VARCHAR(32)",
            "meta": "TEXT",
            "update_id": "BIGINT",
            "updated_at": "TIMESTAMP",
        },
        "emoji_mappings": {
            "label": "VARCHAR(128)",
            "source": "VARCHAR(32)",
        },
    }


def _existing_columns(connection: Connection, table: str) -> set[str]:
    insp = inspect(connection)
    if table not in insp.get_table_names():
        return set()
    return {col["name"] for col in insp.get_columns(table)}


def _widen_postgres_ids(connection: Connection) -> None:
    if connection.dialect.name != "postgresql":
        return
    targets = (
        ("channels", "chat_id"),
        ("message_logs", "chat_id"),
        ("message_logs", "message_id"),
        ("webhook_events", "update_id"),
        ("admins", "telegram_id"),
    )
    for table, column in targets:
        row = connection.execute(
            text(
                """
                SELECT data_type FROM information_schema.columns
                WHERE table_name = :table AND column_name = :column
                """
            ),
            {"table": table, "column": column},
        ).fetchone()
        if row and row[0] == "integer":
            connection.execute(text(f'ALTER TABLE "{table}" ALTER COLUMN "{column}" TYPE BIGINT'))
            logger.info("Widened %s.%s to BIGINT", table, column)


def _dedupe_message_logs(connection: Connection) -> None:
    insp = inspect(connection)
    if "message_logs" not in insp.get_table_names():
        return
    indexes = {idx.get("name") for idx in insp.get_indexes("message_logs")}
    uniques = {u.get("name") for u in insp.get_unique_constraints("message_logs")}
    if "uq_message_chat_msg" in indexes or "uq_message_chat_msg" in uniques:
        return
    try:
        connection.execute(text(
            """
            DELETE FROM message_logs
            WHERE id IN (
                SELECT id FROM (
                    SELECT id, ROW_NUMBER() OVER (
                        PARTITION BY chat_id, message_id ORDER BY created_at DESC
                    ) AS rn
                    FROM message_logs
                ) ranked
                WHERE rn > 1
            )
            """
        ))
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_message_chat_msg ON message_logs (chat_id, message_id)"
        ))
    except Exception as exc:
        logger.warning("Could not enforce message uniqueness yet: %s", exc)


def sync_schema(connection: Connection) -> None:
    insp = inspect(connection)
    tables = set(insp.get_table_names())
    for table, columns in _columns_for(connection).items():
        if table not in tables:
            continue
        have = _existing_columns(connection, table)
        for name, ddl in columns.items():
            if name in have:
                continue
            connection.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {ddl}'))
            logger.info("Added column %s.%s", table, name)
    _widen_postgres_ids(connection)
    _dedupe_message_logs(connection)


async def ensure_schema() -> None:
    import backend.app.models  # noqa: F401
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(sync_schema)
