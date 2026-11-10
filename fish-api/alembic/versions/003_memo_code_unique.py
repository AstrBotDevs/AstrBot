"""Unique index on topup_orders.memo_code.

Revision ID: 003_memo_unique
Revises: 002_bind_status
Create Date: 2026-03-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "003_memo_unique"
down_revision: str | None = "002_bind_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("topup_orders") as batch_op:
        batch_op.create_index("ix_topup_orders_memo_code", ["memo_code"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("topup_orders") as batch_op:
        batch_op.drop_index("ix_topup_orders_memo_code")
