"""add allocation intents

Revision ID: a4c7e9b2d1f0
Revises: f2a4c6d8e0b1
Create Date: 2026-08-21 16:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a4c7e9b2d1f0"
down_revision: Union[str, Sequence[str], None] = "f2a4c6d8e0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "allocation_intents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("investor_user_id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.Uuid(), nullable=False),
        sa.Column("strategy_version_id", sa.Uuid(), nullable=False),
        sa.Column("notional_amount", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", name="allocation_status"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
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
            name="fk_allocation_intents_strategy_version_same_strategy",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "notional_amount > 0",
            name="ck_allocation_intents_positive_notional_amount",
        ),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="ck_allocation_intents_currency_format",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_allocation_intents_investor_user_id"),
        "allocation_intents",
        ["investor_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_allocation_intents_strategy_id"),
        "allocation_intents",
        ["strategy_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_allocation_intents_status"),
        "allocation_intents",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_allocation_intents_status"), table_name="allocation_intents")
    op.drop_index(
        op.f("ix_allocation_intents_strategy_id"), table_name="allocation_intents"
    )
    op.drop_index(
        op.f("ix_allocation_intents_investor_user_id"),
        table_name="allocation_intents",
    )
    op.drop_table("allocation_intents")
    postgresql.ENUM(name="allocation_status").drop(op.get_bind(), checkfirst=True)
