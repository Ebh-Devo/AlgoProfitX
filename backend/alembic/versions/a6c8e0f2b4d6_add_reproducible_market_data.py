"""add reproducible market data datasets

Revision ID: a6c8e0f2b4d6
Revises: e5a1b2c3d4f6
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a6c8e0f2b4d6"
down_revision = "e5a1b2c3d4f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    status = postgresql.ENUM("ready", "failed", name="market_data_dataset_status", create_type=False)
    status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "market_data_datasets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_key", sa.String(64), nullable=False),
        sa.Column("instrument_id", sa.Uuid(), nullable=False),
        sa.Column("provider_code", sa.String(50), nullable=False),
        sa.Column("provider_mapping_id", sa.Uuid(), nullable=True),
        sa.Column("timeframe", sa.String(20), nullable=False),
        sa.Column("adjustment_policy", sa.String(50), nullable=False),
        sa.Column("requested_start", sa.Date(), nullable=False), sa.Column("requested_end", sa.Date(), nullable=False),
        sa.Column("actual_start", sa.Date(), nullable=False), sa.Column("actual_end", sa.Date(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False), sa.Column("candle_count", sa.Integer(), nullable=False),
        sa.Column("raw_checksum", sa.String(64), nullable=True), sa.Column("normalized_checksum", sa.String(64), nullable=False),
        sa.Column("status", status, nullable=False), sa.Column("provenance", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("candle_count >= 0", name="ck_market_data_datasets_candle_count"),
        sa.CheckConstraint("octet_length(provenance::text) <= 16384", name="ck_market_data_datasets_provenance_size"),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["provider_mapping_id"], ["instrument_vendor_mappings.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("dataset_key", name="uq_market_data_datasets_key"),
    )
    op.create_index("ix_market_data_datasets_instrument_id", "market_data_datasets", ["instrument_id"])
    op.create_index("ix_market_data_datasets_provider_code", "market_data_datasets", ["provider_code"])
    op.create_index("ix_market_data_datasets_provider_mapping_id", "market_data_datasets", ["provider_mapping_id"])
    op.create_table(
        "market_data_candles",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False), sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(20, 8), nullable=False), sa.Column("high", sa.Numeric(20, 8), nullable=False),
        sa.Column("low", sa.Numeric(20, 8), nullable=False), sa.Column("close", sa.Numeric(20, 8), nullable=False),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.CheckConstraint("open > 0 AND high > 0 AND low > 0 AND close > 0", name="ck_market_data_candles_positive_prices"),
        sa.CheckConstraint("high >= open AND high >= close AND high >= low AND low <= open AND low <= close", name="ck_market_data_candles_ohlc"),
        sa.CheckConstraint("volume IS NULL OR volume >= 0", name="ck_market_data_candles_volume"),
        sa.ForeignKeyConstraint(["dataset_id"], ["market_data_datasets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("dataset_id", "session_date", name="uq_market_data_candles_dataset_session"),
    )
    op.create_index("ix_market_data_candles_dataset_id", "market_data_candles", ["dataset_id"])
    op.add_column("backtests", sa.Column("market_data_dataset_id", sa.Uuid(), nullable=True))
    op.add_column("backtests", sa.Column("error_code", sa.String(100), nullable=True))
    op.create_index("ix_backtests_market_data_dataset_id", "backtests", ["market_data_dataset_id"])
    op.create_foreign_key("fk_backtests_market_data_dataset", "backtests", "market_data_datasets", ["market_data_dataset_id"], ["id"], ondelete="RESTRICT")


def downgrade() -> None:
    op.drop_constraint("fk_backtests_market_data_dataset", "backtests", type_="foreignkey")
    op.drop_index("ix_backtests_market_data_dataset_id", table_name="backtests")
    op.drop_column("backtests", "error_code"); op.drop_column("backtests", "market_data_dataset_id")
    op.drop_index("ix_market_data_candles_dataset_id", table_name="market_data_candles"); op.drop_table("market_data_candles")
    op.drop_index("ix_market_data_datasets_provider_mapping_id", table_name="market_data_datasets")
    op.drop_index("ix_market_data_datasets_provider_code", table_name="market_data_datasets")
    op.drop_index("ix_market_data_datasets_instrument_id", table_name="market_data_datasets")
    op.drop_table("market_data_datasets")
    postgresql.ENUM(name="market_data_dataset_status").drop(op.get_bind(), checkfirst=True)
