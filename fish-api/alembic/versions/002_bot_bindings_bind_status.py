"""Add bot_bindings.bind_status for DBs created before the column existed.

Revision ID: 002_bind_status
Revises: 001_initial
Create Date: 2026-03-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "002_bind_status"
down_revision: str | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "bot_bindings" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("bot_bindings")}
    if "bind_status" in columns:
        return
    with op.batch_alter_table("bot_bindings") as batch_op:
        batch_op.add_column(
            sa.Column(
                "bind_status",
                sa.String(length=24),
                nullable=False,
                server_default="pending",
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "bot_bindings" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("bot_bindings")}
    if "bind_status" not in columns:
        return
    with op.batch_alter_table("bot_bindings") as batch_op:
        batch_op.drop_column("bind_status")
