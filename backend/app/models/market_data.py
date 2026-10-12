import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.domain.enums import MarketDataDatasetStatus


class MarketDataDataset(Base):
    __tablename__ = "market_data_datasets"
    __table_args__ = (
        UniqueConstraint("dataset_key", name="uq_market_data_datasets_key"),
        CheckConstraint("candle_count >= 0", name="ck_market_data_datasets_candle_count"),
        CheckConstraint("octet_length(provenance::text) <= 16384", name="ck_market_data_datasets_provenance_size"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    dataset_key: Mapped[str] = mapped_column(String(64), nullable=False)
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=False, index=True)
    provider_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    provider_mapping_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("instrument_vendor_mappings.id", ondelete="RESTRICT"), nullable=True, index=True)
    timeframe: Mapped[str] = mapped_column(String(20), nullable=False)
    adjustment_policy: Mapped[str] = mapped_column(String(50), nullable=False)
    requested_start: Mapped[date] = mapped_column(Date, nullable=False)
    requested_end: Mapped[date] = mapped_column(Date, nullable=False)
    actual_start: Mapped[date] = mapped_column(Date, nullable=False)
    actual_end: Mapped[date] = mapped_column(Date, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    candle_count: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    normalized_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[MarketDataDatasetStatus] = mapped_column(Enum(MarketDataDatasetStatus, name="market_data_dataset_status", values_callable=lambda cls: [x.value for x in cls]), nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    candles: Mapped[list["MarketDataCandle"]] = relationship(back_populates="dataset", order_by="MarketDataCandle.session_date", cascade="all, delete-orphan")


class MarketDataCandle(Base):
    __tablename__ = "market_data_candles"
    __table_args__ = (
        UniqueConstraint("dataset_id", "session_date", name="uq_market_data_candles_dataset_session"),
        CheckConstraint("open > 0 AND high > 0 AND low > 0 AND close > 0", name="ck_market_data_candles_positive_prices"),
        CheckConstraint("high >= open AND high >= close AND high >= low AND low <= open AND low <= close", name="ck_market_data_candles_ohlc"),
        CheckConstraint("volume IS NULL OR volume >= 0", name="ck_market_data_candles_volume"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("market_data_datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dataset: Mapped[MarketDataDataset] = relationship(back_populates="candles")
