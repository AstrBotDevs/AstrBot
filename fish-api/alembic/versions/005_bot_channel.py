"""Add bot_bindings.channel for QQ / WeChat.

Revision ID: 005_bot_channel
Revises: 004_user_role
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005_bot_channel"
down_revision: str | None = "004_user_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("bot_bindings") as batch_op:
        batch_op.add_column(
            sa.Column(
                "channel",
                sa.String(length=16),
                nullable=False,
                server_default="qq",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("bot_bindings") as batch_op:
        batch_op.drop_column("channel")
