import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    CheckConstraint,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Numeric,
    select,
    String,
)
from sqlalchemy.orm import Mapped, column_property, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base
from app.models.strategy import Strategy, StrategyVersion


class AllocationStatus(str, enum.Enum):
    ACTIVE = "active"


class AllocationIntent(Base):
    __tablename__ = "allocation_intents"
    __table_args__ = (
        CheckConstraint(
            "notional_amount > 0",
            name="ck_allocation_intents_positive_notional_amount",
        ),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="ck_allocation_intents_currency_format",
        ),
        ForeignKeyConstraint(
            ["strategy_id", "strategy_version_id"],
            ["strategy_versions.strategy_id", "strategy_versions.id"],
            name="fk_allocation_intents_strategy_version_same_strategy",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
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

    strategy_name: Mapped[str] = column_property(
        select(Strategy.name).where(Strategy.id == strategy_id).scalar_subquery()
    )
    strategy_version_number: Mapped[int] = column_property(
        select(StrategyVersion.version_number)
        .where(StrategyVersion.id == strategy_version_id)
        .scalar_subquery()
    )

    notional_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 8),
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    status: Mapped[AllocationStatus] = mapped_column(
        Enum(
            AllocationStatus,
            name="allocation_status",
            values_callable=lambda enum_class: [
                member.value for member in enum_class
            ],
        ),
        default=AllocationStatus.ACTIVE,
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
