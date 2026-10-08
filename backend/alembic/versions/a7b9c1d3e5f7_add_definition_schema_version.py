"""add definition_schema_version to strategy versions and backtests

Additive and non-destructive: a NOT NULL column with a constant server default of 1, so every
existing row is a V1 definition without any row rewrite and no strategy JSON is touched.

Revision ID: a7b9c1d3e5f7
Revises: c6d1e8f3a9b2
Create Date: 2026-10-08 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a7b9c1d3e5f7"
down_revision: Union[str, Sequence[str], None] = "c6d1e8f3a9b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("strategy_versions", "backtests"):
        op.add_column(
            table,
            sa.Column(
                "definition_schema_version",
                sa.Integer(),
                server_default=sa.text("1"),
                nullable=False,
            ),
        )


def downgrade() -> None:
    # Dropping the column loses the V1/V2 marker; downgrading with V2 rows present would
    # leave them to be misread as V1, so refuse rather than corrupt silently.
    bind = op.get_bind()
    for table in ("strategy_versions", "backtests"):
        stray = bind.execute(
            sa.text(f"SELECT 1 FROM {table} WHERE definition_schema_version <> 1 LIMIT 1")
        ).first()
        if stray is not None:
            raise RuntimeError(
                f"cannot downgrade: {table} holds non-V1 definitions that would be misread as V1"
            )
    for table in ("backtests", "strategy_versions"):
        op.drop_column(table, "definition_schema_version")
