"""add execution intents

Revision ID: b7d3f9e1c2a4
Revises: a4c7e9b2d1f0
Create Date: 2026-08-21 17:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b7d3f9e1c2a4"
down_revision: Union[str, Sequence[str], None] = "a4c7e9b2d1f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "execution_intents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("allocation_intent_id", sa.Uuid(), nullable=False),
        sa.Column("investor_user_id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.Uuid(), nullable=False),
        sa.Column("strategy_version_id", sa.Uuid(), nullable=False),
        sa.Column(
            "notional_amount_snapshot", sa.Numeric(precision=18, scale=8), nullable=False
        ),
        sa.Column("currency_snapshot", sa.String(length=3), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "running", "completed", "failed", name="execution_status"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.CheckConstraint(
            "notional_amount_snapshot > 0",
            name="ck_execution_intents_positive_notional_amount_snapshot",
        ),
        sa.CheckConstraint(
            "currency_snapshot ~ '^[A-Z]{3}$'",
            name="ck_execution_intents_currency_snapshot_format",
        ),
        sa.CheckConstraint("mode = 'paper'", name="ck_execution_intents_paper_mode"),
        sa.ForeignKeyConstraint(
            ["allocation_intent_id"], ["allocation_intents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["investor_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["strategy_id"], ["strategies.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["strategy_id", "strategy_version_id"],
            ["strategy_versions.strategy_id", "strategy_versions.id"],
            name="fk_execution_intents_strategy_version_same_strategy",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_execution_intents_allocation_intent_id"),
        "execution_intents",
        ["allocation_intent_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_execution_intents_investor_user_id"),
        "execution_intents",
        ["investor_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_execution_intents_strategy_id"),
        "execution_intents",
        ["strategy_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_execution_intents_status"),
        "execution_intents",
        ["status"],
        unique=False,
    )
    op.create_index(
        "uq_execution_intents_active_allocation",
        "execution_intents",
        ["allocation_intent_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )
    op.create_index(
        "uq_execution_intents_investor_idempotency_key",
        "execution_intents",
        ["investor_user_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_execution_intents_investor_idempotency_key", table_name="execution_intents")
    op.drop_index("uq_execution_intents_active_allocation", table_name="execution_intents")
    op.drop_index(op.f("ix_execution_intents_status"), table_name="execution_intents")
    op.drop_index(op.f("ix_execution_intents_strategy_id"), table_name="execution_intents")
    op.drop_index(
        op.f("ix_execution_intents_investor_user_id"), table_name="execution_intents"
    )
    op.drop_index(
        op.f("ix_execution_intents_allocation_intent_id"), table_name="execution_intents"
    )
    op.drop_table("execution_intents")
    postgresql.ENUM(name="execution_status").drop(op.get_bind(), checkfirst=True)
