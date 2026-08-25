"""add backtest market data provenance

Revision ID: c3f6a9b2d5e8
Revises: b2e5f8a1c4d7
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c3f6a9b2d5e8"
down_revision: Union[str, Sequence[str], None] = "b2e5f8a1c4d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("backtests", sa.Column("instrument_id", sa.Uuid(), nullable=True))
    op.add_column(
        "backtests",
        sa.Column(
            "instrument_snapshot",
            postgresql.JSONB(none_as_null=True),
            nullable=True,
        ),
    )
    op.add_column("backtests", sa.Column("market_data_provider", sa.String(100), nullable=True))
    op.add_column("backtests", sa.Column("dataset_reference", sa.String(500), nullable=True))
    op.add_column("backtests", sa.Column("timeframe", sa.String(50), nullable=True))
    op.add_column("backtests", sa.Column("range_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column("backtests", sa.Column("range_end", sa.DateTime(timezone=True), nullable=True))
    op.add_column("backtests", sa.Column("adjustment_policy", sa.String(50), nullable=True))
    op.add_column("backtests", sa.Column("data_fetched_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "backtests",
        sa.Column(
            "market_data_provenance",
            postgresql.JSONB(none_as_null=True),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ix_backtests_instrument_id"),
        "backtests",
        ["instrument_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_backtests_instrument_id_instruments",
        "backtests",
        "instruments",
        ["instrument_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_backtests_instrument_snapshot_object",
        "backtests",
        "instrument_snapshot IS NULL OR jsonb_typeof(instrument_snapshot) = 'object'",
    )
    op.create_check_constraint(
        "ck_backtests_instrument_snapshot_size",
        "backtests",
        "instrument_snapshot IS NULL OR octet_length(instrument_snapshot::text) <= 4096",
    )
    op.create_check_constraint(
        "ck_backtests_market_data_provenance_object",
        "backtests",
        "market_data_provenance IS NULL OR jsonb_typeof(market_data_provenance) = 'object'",
    )
    op.create_check_constraint(
        "ck_backtests_market_data_provenance_size",
        "backtests",
        "market_data_provenance IS NULL OR octet_length(market_data_provenance::text) <= 8192",
    )


def downgrade() -> None:
    op.drop_constraint("ck_backtests_market_data_provenance_size", "backtests", type_="check")
    op.drop_constraint("ck_backtests_market_data_provenance_object", "backtests", type_="check")
    op.drop_constraint("ck_backtests_instrument_snapshot_size", "backtests", type_="check")
    op.drop_constraint("ck_backtests_instrument_snapshot_object", "backtests", type_="check")
    op.drop_constraint("fk_backtests_instrument_id_instruments", "backtests", type_="foreignkey")
    op.drop_index(op.f("ix_backtests_instrument_id"), table_name="backtests")
    for column in (
        "market_data_provenance",
        "data_fetched_at",
        "adjustment_policy",
        "range_end",
        "range_start",
        "timeframe",
        "dataset_reference",
        "market_data_provider",
        "instrument_snapshot",
        "instrument_id",
    ):
        op.drop_column("backtests", column)
