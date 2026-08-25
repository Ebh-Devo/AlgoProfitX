"""add market instrument foundation

Revision ID: a1d4e7f9b2c6
Revises: f4b2c9d7e1a3
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a1d4e7f9b2c6"
down_revision: Union[str, Sequence[str], None] = "f4b2c9d7e1a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    instrument_type = postgresql.ENUM(
        "equity", "index", name="instrument_type", create_type=False
    )
    instrument_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "exchanges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("timezone", sa.String(length=100), nullable=False),
        sa.Column("default_currency", sa.String(length=3), nullable=False),
        sa.Column("calendar_code", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("code ~ '^[A-Z0-9_]{2,20}$'", name="ck_exchanges_code_format"),
        sa.CheckConstraint("country_code ~ '^[A-Z]{2}$'", name="ck_exchanges_country_code_format"),
        sa.CheckConstraint("default_currency ~ '^[A-Z]{3}$'", name="ck_exchanges_currency_format"),
        sa.CheckConstraint("length(timezone) > 0", name="ck_exchanges_timezone_present"),
        sa.CheckConstraint("length(calendar_code) > 0", name="ck_exchanges_calendar_code_present"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("calendar_code"),
    )
    op.create_index(op.f("ix_exchanges_code"), "exchanges", ["code"], unique=True)
    op.create_index(op.f("ix_exchanges_is_active"), "exchanges", ["is_active"], unique=False)

    op.create_table(
        "instruments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("exchange_id", sa.Uuid(), nullable=False),
        sa.Column("canonical_symbol", sa.String(length=100), nullable=False),
        sa.Column("exchange_symbol", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("instrument_type", instrument_type, nullable=False),
        sa.Column("quote_currency", sa.String(length=3), nullable=False),
        sa.Column("tick_size", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("lot_size", sa.Integer(), nullable=True),
        sa.Column("is_tradeable", sa.Boolean(), nullable=False),
        sa.Column("isin", sa.String(length=12), nullable=True),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("quote_currency ~ '^[A-Z]{3}$'", name="ck_instruments_currency_format"),
        sa.CheckConstraint("tick_size IS NULL OR tick_size > 0", name="ck_instruments_positive_tick_size"),
        sa.CheckConstraint("lot_size IS NULL OR lot_size > 0", name="ck_instruments_positive_lot_size"),
        sa.CheckConstraint(
            "NOT is_tradeable OR (tick_size IS NOT NULL AND lot_size IS NOT NULL)",
            name="ck_instruments_tradeable_metadata",
        ),
        sa.ForeignKeyConstraint(["exchange_id"], ["exchanges.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exchange_id", "exchange_symbol", name="uq_instruments_exchange_symbol"),
        sa.UniqueConstraint("isin"),
    )
    op.create_index(op.f("ix_instruments_canonical_symbol"), "instruments", ["canonical_symbol"], unique=True)
    op.create_index(op.f("ix_instruments_exchange_id"), "instruments", ["exchange_id"], unique=False)
    op.create_index(op.f("ix_instruments_instrument_type"), "instruments", ["instrument_type"], unique=False)
    op.create_index(op.f("ix_instruments_is_active"), "instruments", ["is_active"], unique=False)
    op.create_index(op.f("ix_instruments_is_tradeable"), "instruments", ["is_tradeable"], unique=False)

    op.create_table(
        "instrument_vendor_mappings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("instrument_id", sa.Uuid(), nullable=False),
        sa.Column("provider_code", sa.String(length=50), nullable=False),
        sa.Column("vendor_instrument_id", sa.String(length=255), nullable=False),
        sa.Column("vendor_symbol", sa.String(length=150), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("provider_code ~ '^[a-z0-9][a-z0-9_-]{1,49}$'", name="ck_vendor_mapping_provider_code_format"),
        sa.CheckConstraint("length(vendor_instrument_id) > 0", name="ck_vendor_mapping_identifier_present"),
        sa.CheckConstraint("valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from", name="ck_vendor_mapping_validity_range"),
        sa.CheckConstraint("jsonb_typeof(metadata) = 'object'", name="ck_vendor_mapping_metadata_object"),
        sa.CheckConstraint("octet_length(metadata::text) <= 4096", name="ck_vendor_mapping_metadata_size"),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_code", "vendor_instrument_id", name="uq_vendor_mapping_provider_identifier"),
    )
    op.create_index(op.f("ix_instrument_vendor_mappings_instrument_id"), "instrument_vendor_mappings", ["instrument_id"], unique=False)
    op.create_index(op.f("ix_instrument_vendor_mappings_is_active"), "instrument_vendor_mappings", ["is_active"], unique=False)
    op.create_index(op.f("ix_instrument_vendor_mappings_provider_code"), "instrument_vendor_mappings", ["provider_code"], unique=False)
    op.create_index(
        "uq_vendor_mapping_active_instrument_provider",
        "instrument_vendor_mappings",
        ["instrument_id", "provider_code"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index("uq_vendor_mapping_active_instrument_provider", table_name="instrument_vendor_mappings")
    op.drop_index(op.f("ix_instrument_vendor_mappings_provider_code"), table_name="instrument_vendor_mappings")
    op.drop_index(op.f("ix_instrument_vendor_mappings_is_active"), table_name="instrument_vendor_mappings")
    op.drop_index(op.f("ix_instrument_vendor_mappings_instrument_id"), table_name="instrument_vendor_mappings")
    op.drop_table("instrument_vendor_mappings")
    op.drop_index(op.f("ix_instruments_is_tradeable"), table_name="instruments")
    op.drop_index(op.f("ix_instruments_is_active"), table_name="instruments")
    op.drop_index(op.f("ix_instruments_instrument_type"), table_name="instruments")
    op.drop_index(op.f("ix_instruments_exchange_id"), table_name="instruments")
    op.drop_index(op.f("ix_instruments_canonical_symbol"), table_name="instruments")
    op.drop_table("instruments")
    op.drop_index(op.f("ix_exchanges_is_active"), table_name="exchanges")
    op.drop_index(op.f("ix_exchanges_code"), table_name="exchanges")
    op.drop_table("exchanges")
    postgresql.ENUM(name="instrument_type").drop(op.get_bind(), checkfirst=True)
