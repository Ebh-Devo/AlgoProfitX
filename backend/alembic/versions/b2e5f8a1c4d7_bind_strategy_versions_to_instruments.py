"""bind strategy versions to instruments

Revision ID: b2e5f8a1c4d7
Revises: a1d4e7f9b2c6
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from app.db.migration_support import SYNTHETIC_STRATEGY_VERSION_BACKFILL_SQL


revision: str = "b2e5f8a1c4d7"
down_revision: Union[str, Sequence[str], None] = "a1d4e7f9b2c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column(
        "strategy_versions",
        sa.Column("instrument_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        op.f("ix_strategy_versions_instrument_id"),
        "strategy_versions",
        ["instrument_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_strategy_versions_instrument_id_instruments",
        "strategy_versions",
        "instruments",
        ["instrument_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # Preserve immutable JSON and map only the stable synthetic fixture when
    # its canonical Instrument has already been bootstrapped.
    op.execute(SYNTHETIC_STRATEGY_VERSION_BACKFILL_SQL)


def downgrade() -> None:
    op.drop_constraint(
        "fk_strategy_versions_instrument_id_instruments",
        "strategy_versions",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_strategy_versions_instrument_id"),
        table_name="strategy_versions",
    )
    op.drop_column("strategy_versions", "instrument_id")
