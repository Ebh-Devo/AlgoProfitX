import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class InstrumentType(str, enum.Enum):
    EQUITY = "equity"
    INDEX = "index"


class Exchange(Base):
    __tablename__ = "exchanges"
    __table_args__ = (
        CheckConstraint("code ~ '^[A-Z0-9_]{2,20}$'", name="ck_exchanges_code_format"),
        CheckConstraint("country_code ~ '^[A-Z]{2}$'", name="ck_exchanges_country_code_format"),
        CheckConstraint("default_currency ~ '^[A-Z]{3}$'", name="ck_exchanges_currency_format"),
        CheckConstraint("length(timezone) > 0", name="ck_exchanges_timezone_present"),
        CheckConstraint("length(calendar_code) > 0", name="ck_exchanges_calendar_code_present"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    timezone: Mapped[str] = mapped_column(String(100), nullable=False)
    default_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    calendar_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    instruments: Mapped[list["Instrument"]] = relationship(
        back_populates="exchange", passive_deletes=True
    )


class Instrument(Base):
    __tablename__ = "instruments"
    __table_args__ = (
        UniqueConstraint("exchange_id", "exchange_symbol", name="uq_instruments_exchange_symbol"),
        CheckConstraint("quote_currency ~ '^[A-Z]{3}$'", name="ck_instruments_currency_format"),
        CheckConstraint("tick_size IS NULL OR tick_size > 0", name="ck_instruments_positive_tick_size"),
        CheckConstraint("lot_size IS NULL OR lot_size > 0", name="ck_instruments_positive_lot_size"),
        CheckConstraint(
            "NOT is_tradeable OR (tick_size IS NOT NULL AND lot_size IS NOT NULL)",
            name="ck_instruments_tradeable_metadata",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    exchange_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exchanges.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    canonical_symbol: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    exchange_symbol: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    instrument_type: Mapped[InstrumentType] = mapped_column(
        Enum(InstrumentType, name="instrument_type", values_callable=lambda enum_class: [item.value for item in enum_class]),
        nullable=False,
        index=True,
    )
    quote_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    tick_size: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    lot_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_tradeable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    isin: Mapped[str | None] = mapped_column(String(12), nullable=True, unique=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    exchange: Mapped[Exchange] = relationship(back_populates="instruments")
    vendor_mappings: Mapped[list["InstrumentVendorMapping"]] = relationship(
        back_populates="instrument", passive_deletes=True
    )


class InstrumentVendorMapping(Base):
    __tablename__ = "instrument_vendor_mappings"
    __table_args__ = (
        UniqueConstraint("provider_code", "vendor_instrument_id", name="uq_vendor_mapping_provider_identifier"),
        CheckConstraint("provider_code ~ '^[a-z0-9][a-z0-9_-]{1,49}$'", name="ck_vendor_mapping_provider_code_format"),
        CheckConstraint("length(vendor_instrument_id) > 0", name="ck_vendor_mapping_identifier_present"),
        CheckConstraint("valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from", name="ck_vendor_mapping_validity_range"),
        CheckConstraint("jsonb_typeof(metadata) = 'object'", name="ck_vendor_mapping_metadata_object"),
        CheckConstraint("octet_length(metadata::text) <= 4096", name="ck_vendor_mapping_metadata_size"),
        Index(
            "uq_vendor_mapping_active_instrument_provider",
            "instrument_id",
            "provider_code",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    provider_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    vendor_instrument_id: Mapped[str] = mapped_column(String(255), nullable=False)
    vendor_symbol: Mapped[str | None] = mapped_column(String(150), nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    provider_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    instrument: Mapped[Instrument] = relationship(back_populates="vendor_mappings")
