import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.instrument import Exchange, Instrument
from app.models.strategy import Strategy, StrategyStatus, StrategyVersion
from app.schemas.strategy import (
    StrategyCreateRequest,
    StrategyUpdateRequest,
    StrategyVersionCreateRequest,
)
from app.instrument_identity import SYNTHETIC_EQUITY_ID, SYNTHETIC_EQUITY_SYMBOLS


ALLOWED_LIFECYCLE_TRANSITIONS = {
    StrategyStatus.DRAFT: {
        StrategyStatus.PUBLISHED,
        StrategyStatus.ARCHIVED,
    },
    StrategyStatus.PUBLISHED: {
        StrategyStatus.DEPLOYED,
        StrategyStatus.ARCHIVED,
    },
    StrategyStatus.DEPLOYED: {StrategyStatus.ARCHIVED},
    StrategyStatus.ARCHIVED: set(),
}


class StrategyConflict(Exception):
    pass


class StrategyVersionValidationError(Exception):
    pass


async def create_strategy(
    session: AsyncSession,
    creator_id: uuid.UUID,
    data: StrategyCreateRequest,
) -> Strategy:
    strategy = Strategy(
        creator_id=creator_id,
        name=data.name,
        slug=data.slug,
        description=data.description,
    )

    session.add(strategy)

    try:
        await session.flush()
        await session.refresh(strategy)
    except IntegrityError:
        await session.rollback()
        raise ValueError("Strategy slug is already in use")

    return strategy


async def get_strategies_for_creator(
    session: AsyncSession,
    creator_id: uuid.UUID,
) -> list[Strategy]:
    result = await session.execute(
        select(Strategy)
        .where(Strategy.creator_id == creator_id)
        .order_by(Strategy.created_at.desc())
    )

    return list(result.scalars().all())


async def get_strategy(
    session: AsyncSession,
    strategy_id: uuid.UUID,
    creator_id: uuid.UUID,
) -> Strategy | None:
    result = await session.execute(
        select(Strategy).where(
            Strategy.id == strategy_id,
            Strategy.creator_id == creator_id,
        )
    )

    return result.scalar_one_or_none()


async def update_strategy(
    session: AsyncSession,
    strategy: Strategy,
    data: StrategyUpdateRequest,
) -> Strategy:
    updates = data.model_dump(exclude_unset=True)

    for field, value in updates.items():
        setattr(strategy, field, value)

    try:
        await session.flush()
        await session.refresh(strategy)
    except IntegrityError:
        await session.rollback()
        raise ValueError("Strategy slug is already in use")

    return strategy


async def delete_strategy(
    session: AsyncSession,
    strategy: Strategy,
) -> None:
    from app.models.allocation import AllocationIntent
    from app.models.execution import ExecutionIntent

    strategy = await _lock_strategy(session, strategy)
    protected_history = await session.scalar(
        select(AllocationIntent.id)
        .where(AllocationIntent.strategy_id == strategy.id)
        .limit(1)
    )
    if protected_history is None:
        protected_history = await session.scalar(
            select(ExecutionIntent.id)
            .where(ExecutionIntent.strategy_id == strategy.id)
            .limit(1)
        )
    if protected_history is not None:
        raise StrategyConflict(
            "Strategy with allocation or execution history cannot be deleted"
        )
    await session.delete(strategy)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise StrategyConflict(
            "Strategy with allocation or execution history cannot be deleted"
        ) from exc


async def create_strategy_version(
    session: AsyncSession,
    strategy: Strategy,
    data: StrategyVersionCreateRequest,
) -> StrategyVersion:
    instrument = await session.scalar(
        select(Instrument)
        .join(Exchange)
        .where(Instrument.id == data.instrument_id)
        .options(selectinload(Instrument.exchange))
    )
    if instrument is None:
        raise StrategyVersionValidationError("Instrument not found")
    if not instrument.is_active:
        raise StrategyVersionValidationError("Instrument is inactive")
    if not instrument.exchange.is_active:
        raise StrategyVersionValidationError("Instrument Exchange is inactive")

    legacy_identity = data.configuration.get("instrument")
    if legacy_identity is not None:
        matching_symbols = {
            instrument.canonical_symbol.casefold(),
            instrument.exchange_symbol.casefold(),
        }
        if instrument.id == SYNTHETIC_EQUITY_ID:
            matching_symbols.update(symbol.casefold() for symbol in SYNTHETIC_EQUITY_SYMBOLS)
        if not isinstance(legacy_identity, str) or legacy_identity.casefold() not in matching_symbols:
            raise StrategyVersionValidationError(
                "configuration.instrument conflicts with instrument_id"
            )

    # Lock the parent row so normal API requests allocate one version number at
    # a time for a strategy. The database constraint remains the final guard.
    await session.execute(
        select(Strategy)
        .where(Strategy.id == strategy.id)
        .with_for_update()
    )

    result = await session.execute(
        select(func.coalesce(func.max(StrategyVersion.version_number), 0)).where(
            StrategyVersion.strategy_id == strategy.id
        )
    )
    version_number = result.scalar_one() + 1

    version = StrategyVersion(
        strategy_id=strategy.id,
        instrument_id=instrument.id,
        version_number=version_number,
        configuration=data.configuration,
        backtest_configuration=data.backtest_configuration,
    )
    version.instrument = instrument
    session.add(version)

    try:
        await session.flush()
        await session.refresh(version)
        version.instrument = instrument
    except IntegrityError:
        await session.rollback()
        raise ValueError("Strategy version number is already in use")

    return version


async def get_strategy_versions(
    session: AsyncSession,
    strategy_id: uuid.UUID,
) -> list[StrategyVersion]:
    result = await session.execute(
        select(StrategyVersion)
        .options(selectinload(StrategyVersion.instrument).selectinload(Instrument.exchange))
        .where(StrategyVersion.strategy_id == strategy_id)
        .order_by(StrategyVersion.version_number.asc())
    )

    return list(result.scalars().all())


async def get_strategy_version(
    session: AsyncSession,
    strategy_id: uuid.UUID,
    version_id: uuid.UUID,
) -> StrategyVersion | None:
    result = await session.execute(
        select(StrategyVersion).options(
            selectinload(StrategyVersion.instrument).selectinload(Instrument.exchange)
        ).where(
            StrategyVersion.id == version_id,
            StrategyVersion.strategy_id == strategy_id,
        )
    )

    return result.scalar_one_or_none()


def _require_transition(
    strategy: Strategy,
    target_status: StrategyStatus,
) -> None:
    if target_status not in ALLOWED_LIFECYCLE_TRANSITIONS[strategy.status]:
        raise ValueError(
            "Invalid strategy lifecycle transition: "
            f"{strategy.status.value} -> {target_status.value}"
        )


async def publish_strategy(
    session: AsyncSession,
    strategy: Strategy,
) -> Strategy:
    strategy = await _lock_strategy(session, strategy)
    _require_transition(strategy, StrategyStatus.PUBLISHED)

    latest_version_result = await session.execute(
        select(StrategyVersion)
        .where(StrategyVersion.strategy_id == strategy.id)
        .order_by(StrategyVersion.version_number.desc())
        .limit(1)
    )
    latest_version = latest_version_result.scalar_one_or_none()

    if latest_version is None:
        raise ValueError("A strategy version is required before publishing")

    strategy.status = StrategyStatus.PUBLISHED
    strategy.current_version_id = latest_version.id
    strategy.is_public = True
    strategy.published_at = datetime.now(timezone.utc)

    await session.flush()
    await session.refresh(strategy)
    return strategy


async def deploy_strategy(
    session: AsyncSession,
    strategy: Strategy,
) -> Strategy:
    strategy = await _lock_strategy(session, strategy)
    _require_transition(strategy, StrategyStatus.DEPLOYED)

    strategy.status = StrategyStatus.DEPLOYED
    strategy.deployed_at = datetime.now(timezone.utc)

    await session.flush()
    await session.refresh(strategy)
    return strategy


async def archive_strategy(
    session: AsyncSession,
    strategy: Strategy,
) -> Strategy:
    strategy = await _lock_strategy(session, strategy)
    _require_transition(strategy, StrategyStatus.ARCHIVED)

    strategy.status = StrategyStatus.ARCHIVED
    strategy.is_public = False

    await session.flush()
    await session.refresh(strategy)
    return strategy


async def _lock_strategy(session: AsyncSession, strategy: Strategy) -> Strategy:
    result = await session.execute(
        select(Strategy)
        .where(Strategy.id == strategy.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()
