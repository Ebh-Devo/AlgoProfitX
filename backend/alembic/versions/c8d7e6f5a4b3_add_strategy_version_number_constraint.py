"""add strategy version number constraint

Revision ID: c8d7e6f5a4b3
Revises: cf5664db0b2e
Create Date: 2026-08-20 19:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


revision: str = "c8d7e6f5a4b3"
down_revision: Union[str, Sequence[str], None] = "cf5664db0b2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_strategy_versions_strategy_id_version_number",
        "strategy_versions",
        ["strategy_id", "version_number"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_strategy_versions_strategy_id_version_number",
        "strategy_versions",
        type_="unique",
    )
