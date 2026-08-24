import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    select,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, column_property, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base
from app.models.strategy import Strategy, StrategyVersion


class ExecutionStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ExecutionIntent(Base):
    __tablename__ = "execution_intents"
    __table_args__ = (
        CheckConstraint(
            "notional_amount_snapshot > 0",
            name="ck_execution_intents_positive_notional_amount_snapshot",
        ),
        CheckConstraint(
            "currency_snapshot ~ '^[A-Z]{3}$'",
            name="ck_execution_intents_currency_snapshot_format",
        ),
        CheckConstraint(
            "mode = 'paper'",
            name="ck_execution_intents_paper_mode",
        ),
        CheckConstraint(
            "(instrument_id IS NULL) = (instrument_snapshot IS NULL)",
            name="ck_execution_intents_instrument_identity_pair",
        ),
        CheckConstraint(
            "instrument_snapshot IS NULL OR jsonb_typeof(instrument_snapshot) = 'object'",
            name="ck_execution_intents_instrument_snapshot_object",
        ),
        CheckConstraint(
            "instrument_snapshot IS NULL OR octet_length(instrument_snapshot::text) <= 4096",
            name="ck_execution_intents_instrument_snapshot_size",
        ),
        ForeignKeyConstraint(
            ["strategy_id", "strategy_version_id"],
            ["strategy_versions.strategy_id", "strategy_versions.id"],
            name="fk_execution_intents_strategy_version_same_strategy",
            ondelete="CASCADE",
        ),
        Index(
            "uq_execution_intents_active_allocation",
            "allocation_intent_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'running')"),
        ),
        Index(
            "uq_execution_intents_investor_idempotency_key",
            "investor_user_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    allocation_intent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("allocation_intents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    investor_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    strategy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    strategy_version_id: Mapped[uuid.UUID] = mapped_column(nullable=False)

    instrument_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=True, index=True
    )

    instrument_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )

    strategy_name: Mapped[str] = column_property(
        select(Strategy.name).where(Strategy.id == strategy_id).scalar_subquery()
    )
    strategy_version_number: Mapped[int] = column_property(
        select(StrategyVersion.version_number)
        .where(StrategyVersion.id == strategy_version_id)
        .scalar_subquery()
    )

    notional_amount_snapshot: Mapped[Decimal] = mapped_column(
        Numeric(18, 8),
        nullable=False,
    )

    currency_snapshot: Mapped[str] = mapped_column(String(3), nullable=False)

    mode: Mapped[str] = mapped_column(String(20), default="paper", nullable=False)

    status: Mapped[ExecutionStatus] = mapped_column(
        Enum(
            ExecutionStatus,
            name="execution_status",
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        default=ExecutionStatus.PENDING,
        nullable=False,
        index=True,
    )

    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(String(500))
    paper_result_summary: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
