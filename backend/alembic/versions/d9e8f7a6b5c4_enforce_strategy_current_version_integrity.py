"""enforce strategy current version integrity

Revision ID: d9e8f7a6b5c4
Revises: c8d7e6f5a4b3
Create Date: 2026-08-21 09:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


revision: str = "d9e8f7a6b5c4"
down_revision: Union[str, Sequence[str], None] = "c8d7e6f5a4b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_strategy_versions_strategy_id_id",
        "strategy_versions",
        ["strategy_id", "id"],
    )
    op.drop_constraint(
        "fk_strategies_current_version_id",
        "strategies",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_strategies_current_version_same_strategy",
        "strategies",
        "strategy_versions",
        ["id", "current_version_id"],
        ["strategy_id", "id"],
        ondelete="SET NULL (current_version_id)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_strategies_current_version_same_strategy",
        "strategies",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_strategies_current_version_id",
        "strategies",
        "strategy_versions",
        ["current_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint(
        "uq_strategy_versions_strategy_id_id",
        "strategy_versions",
        type_="unique",
    )
