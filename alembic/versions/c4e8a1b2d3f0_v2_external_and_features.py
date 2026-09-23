"""v2 external db and panel features

Revision ID: c4e8a1b2d3f0
Revises: 729c935148a2
Create Date: 2026-09-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4e8a1b2d3f0"
down_revision: Union[str, None] = "729c935148a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return set()
    return {col["name"] for col in insp.get_columns(table)}


def _add(table: str, column: sa.Column) -> None:
    if column.name not in _columns(table):
        op.add_column(table, column)


def upgrade() -> None:
    bind = op.get_bind()
    bool_true = sa.true() if bind.dialect.name == "postgresql" else sa.text("1")
    bool_false = sa.false() if bind.dialect.name == "postgresql" else sa.text("0")

    _add("admins", sa.Column("telegram_id", sa.BigInteger(), nullable=True))
    _add("channels", sa.Column("ai_rewrite", sa.Boolean(), nullable=True))
    _add("channels", sa.Column("edit_delay_seconds", sa.Integer(), nullable=True))
    _add("channels", sa.Column("signature_text", sa.String(length=64), nullable=True))
    _add("channels", sa.Column("signature_url", sa.String(length=512), nullable=True))
    _add("channels", sa.Column("skip_keywords", sa.Text(), nullable=True))
    _add("channels", sa.Column("min_chars", sa.Integer(), nullable=True, server_default="1"))
    _add("channels", sa.Column("preserve_buttons", sa.Boolean(), nullable=True, server_default=bool_true))
    _add("channels", sa.Column("notes", sa.Text(), nullable=True))
    _add("channels", sa.Column("posts_edited", sa.Integer(), nullable=True, server_default="0"))
    _add("channels", sa.Column("last_error", sa.Text(), nullable=True))
    _add("channels", sa.Column("last_post_at", sa.DateTime(timezone=True), nullable=True))
    _add("channels", sa.Column("can_edit", sa.Boolean(), nullable=True, server_default=bool_true))
    _add("message_logs", sa.Column("html_text", sa.Text(), nullable=True))
    _add("message_logs", sa.Column("ai_used", sa.Boolean(), nullable=True, server_default=bool_false))
    _add("message_logs", sa.Column("attempt_count", sa.Integer(), nullable=True, server_default="0"))
    _add("message_logs", sa.Column("edit_method", sa.String(length=32), nullable=True))
    _add("message_logs", sa.Column("meta", sa.Text(), nullable=True))
    _add("message_logs", sa.Column("update_id", sa.BigInteger(), nullable=True))
    _add("message_logs", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    _add("emoji_mappings", sa.Column("label", sa.String(length=128), nullable=True))
    _add("emoji_mappings", sa.Column("source", sa.String(length=32), nullable=True))

    if bind.dialect.name == "postgresql":
        for table, column in (
            ("channels", "chat_id"),
            ("message_logs", "chat_id"),
            ("message_logs", "message_id"),
            ("webhook_events", "update_id"),
        ):
            row = bind.execute(sa.text(
                "SELECT data_type FROM information_schema.columns WHERE table_name=:t AND column_name=:c"
            ), {"t": table, "c": column}).fetchone()
            if row and row[0] == "integer":
                op.execute(sa.text(f'ALTER TABLE "{table}" ALTER COLUMN "{column}" TYPE BIGINT'))


def downgrade() -> None:
    pass
