"""add backtest requests

Revision ID: f2a4c6d8e0b1
Revises: d9e8f7a6b5c4
Create Date: 2026-08-21 15:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f2a4c6d8e0b1"
down_revision: Union[str, Sequence[str], None] = "d9e8f7a6b5c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "backtests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("strategy_version_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "running",
                "completed",
                "failed",
                name="backtest_status",
            ),
            nullable=False,
        ),
        sa.Column(
            "configuration_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "backtest_configuration_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("market_data_reference", sa.String(length=500), nullable=True),
        sa.Column(
            "result_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["strategy_version_id"],
            ["strategy_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_backtests_requested_by_user_id"),
        "backtests",
        ["requested_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_backtests_status"),
        "backtests",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_backtests_strategy_version_id"),
        "backtests",
        ["strategy_version_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_backtests_strategy_version_id"), table_name="backtests")
    op.drop_index(op.f("ix_backtests_status"), table_name="backtests")
    op.drop_index(
        op.f("ix_backtests_requested_by_user_id"),
        table_name="backtests",
    )
    op.drop_table("backtests")
    postgresql.ENUM(name="backtest_status").drop(
        op.get_bind(),
        checkfirst=True,
    )
