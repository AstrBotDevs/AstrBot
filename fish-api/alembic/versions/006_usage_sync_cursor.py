"""Track last provider_stats id billed per binding.

Revision ID: 006_usage_sync_cursor
Revises: 005_bot_channel
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "006_usage_sync_cursor"
down_revision: str | None = "005_bot_channel"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("bot_bindings") as batch_op:
        batch_op.add_column(
            sa.Column(
                "usage_synced_stat_id",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("bot_bindings") as batch_op:
        batch_op.drop_column("usage_synced_stat_id")
