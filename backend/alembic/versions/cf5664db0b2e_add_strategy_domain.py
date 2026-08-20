"""add strategy domain

Revision ID: cf5664db0b2e
Revises: 2179084457e1
Create Date: 2026-08-19 15:37:25.822566

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'cf5664db0b2e'
down_revision: Union[str, Sequence[str], None] = '2179084457e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "strategies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("creator_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("slug", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "published",
                "deployed",
                "archived",
                name="strategy_status",
            ),
            nullable=False,
        ),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("current_version_id", sa.Uuid(), nullable=True),
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
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["creator_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_strategies_creator_id"),
        "strategies",
        ["creator_id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_strategies_slug"),
        "strategies",
        ["slug"],
        unique=True,
    )

    op.create_index(
        op.f("ix_strategies_status"),
        "strategies",
        ["status"],
        unique=False,
    )

    op.create_table(
        "strategy_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "configuration",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "backtest_configuration",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["strategies.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_strategy_versions_strategy_id"),
        "strategy_versions",
        ["strategy_id"],
        unique=False,
    )

    # Add after both tables exist to resolve the circular FK dependency.
    op.create_foreign_key(
        "fk_strategies_current_version_id",
        "strategies",
        "strategy_versions",
        ["current_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_constraint(
        "fk_strategies_current_version_id",
        "strategies",
        type_="foreignkey",
    )

    op.drop_index(
        op.f("ix_strategy_versions_strategy_id"),
        table_name="strategy_versions",
    )

    op.drop_table("strategy_versions")

    op.drop_index(
        op.f("ix_strategies_status"),
        table_name="strategies",
    )

    op.drop_index(
        op.f("ix_strategies_slug"),
        table_name="strategies",
    )

    op.drop_index(
        op.f("ix_strategies_creator_id"),
        table_name="strategies",
    )

    op.drop_table("strategies")

    strategy_status = postgresql.ENUM(
        name="strategy_status",
    )
    strategy_status.drop(op.get_bind(), checkfirst=True)
