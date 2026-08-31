import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class BacktestStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Backtest(Base):
    __tablename__ = "backtests"
    __table_args__ = (
        CheckConstraint(
            "instrument_snapshot IS NULL OR jsonb_typeof(instrument_snapshot) = 'object'",
            name="ck_backtests_instrument_snapshot_object",
        ),
        CheckConstraint(
            "instrument_snapshot IS NULL OR octet_length(instrument_snapshot::text) <= 4096",
            name="ck_backtests_instrument_snapshot_size",
        ),
        CheckConstraint(
            "market_data_provenance IS NULL OR jsonb_typeof(market_data_provenance) = 'object'",
            name="ck_backtests_market_data_provenance_object",
        ),
        CheckConstraint(
            "market_data_provenance IS NULL OR octet_length(market_data_provenance::text) <= 8192",
            name="ck_backtests_market_data_provenance_size",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    strategy_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    instrument_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("instruments.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    instrument_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=True),
        nullable=True,
    )

    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    status: Mapped[BacktestStatus] = mapped_column(
        Enum(
            BacktestStatus,
            name="backtest_status",
            values_callable=lambda enum_class: [
                member.value for member in enum_class
            ],
        ),
        default=BacktestStatus.QUEUED,
        nullable=False,
        index=True,
    )

    configuration_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )

    backtest_configuration_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )

    market_data_reference: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    market_data_provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    market_data_dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("market_data_datasets.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    dataset_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    timeframe: Mapped[str | None] = mapped_column(String(50), nullable=True)
    range_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    range_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    adjustment_policy: Mapped[str | None] = mapped_column(String(50), nullable=True)
    data_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    market_data_provenance: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=True),
        nullable=True,
    )

    result_summary: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
