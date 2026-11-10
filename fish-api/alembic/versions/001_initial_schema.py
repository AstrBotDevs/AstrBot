"""Initial fish-api schema.

Revision ID: 001_initial
Revises:
Create Date: 2026-03-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("paid", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "wallet_accounts",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("balance_yuan", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("arrears_yuan", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "bot_bindings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("adapter_id", sa.String(length=128), nullable=False),
        sa.Column("umo_prefix", sa.String(length=256), nullable=False),
        sa.Column("qq_appid", sa.String(length=64), nullable=True),
        sa.Column("bind_status", sa.String(length=24), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bot_bindings_user_id"), "bot_bindings", ["user_id"], unique=True)

    op.create_table(
        "topup_orders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("amount_yuan", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("pay_channel", sa.String(length=32), nullable=False),
        sa.Column("memo_code", sa.String(length=32), nullable=False),
        sa.Column("plan_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_topup_orders_user_id"), "topup_orders", ["user_id"], unique=False)

    op.create_table(
        "support_tickets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_support_tickets_user_id"), "support_tickets", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_support_tickets_user_id"), table_name="support_tickets")
    op.drop_table("support_tickets")
    op.drop_index(op.f("ix_topup_orders_user_id"), table_name="topup_orders")
    op.drop_table("topup_orders")
    op.drop_index(op.f("ix_bot_bindings_user_id"), table_name="bot_bindings")
    op.drop_table("bot_bindings")
    op.drop_table("wallet_accounts")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
