import re
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
from app.strategy_definition.errors import StrategyDefinitionError
from app.strategy_definition.runtime.errors import RuntimeSetupError
from app.strategy_definition.versioning import load_definition_for_version


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


_SLUG_MAX_LENGTH = 180
_SLUG_MIN_LENGTH = 3
_SLUG_SUFFIX_RESERVE = 12
_SLUG_CREATE_ATTEMPTS = 5


def slugify_strategy_name(name: str) -> str:
    """Normalize a strategy name to the marketplace slug format."""
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    base = base[: _SLUG_MAX_LENGTH - _SLUG_SUFFIX_RESERVE].strip("-")
    if len(base) < _SLUG_MIN_LENGTH:
        base = f"{base}-strategy" if base else "strategy"
    return base


async def generate_unique_slug(session: AsyncSession, name: str) -> str:
    """Return base, base-2, base-3, ... - the first slug not yet in use."""
    base = slugify_strategy_name(name)
    # base only contains [a-z0-9-], so it is safe to use in a LIKE prefix.
    result = await session.execute(
        select(Strategy.slug).where(
            (Strategy.slug == base) | Strategy.slug.like(f"{base}-%")
        )
    )
    taken = set(result.scalars().all())
    if base not in taken:
        return base
    suffix = 2
    while f"{base}-{suffix}" in taken:
        suffix += 1
    return f"{base}-{suffix}"


async def create_strategy(
    session: AsyncSession,
    creator_id: uuid.UUID,
    data: StrategyCreateRequest,
) -> Strategy:
    explicit_slug = data.slug is not None
    attempts = 1 if explicit_slug else _SLUG_CREATE_ATTEMPTS

    for _ in range(attempts):
        slug = data.slug if explicit_slug else await generate_unique_slug(
            session, data.name
        )
        strategy = Strategy(
            creator_id=creator_id,
            name=data.name,
            slug=slug,
            description=data.description,
        )

        try:
            # Savepoint so a lost uniqueness race can be retried with a new slug.
            async with session.begin_nested():
                session.add(strategy)
                await session.flush()
        except IntegrityError:
            continue

        await session.refresh(strategy)
        return strategy

    raise ValueError(
        "Strategy slug is already in use"
        if explicit_slug
        else "Could not create the strategy right now. Please try again."
    )


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
    if strategy.status is not StrategyStatus.DRAFT:
        raise StrategyConflict(
            "Only an unused draft strategy can be deleted; archive historical strategies"
        )
    await session.delete(strategy)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise StrategyConflict(
            "Strategy with historical records cannot be deleted"
        ) from exc


V1_SCHEMA_VERSION = 1
V2_SCHEMA_VERSION = 2


async def create_strategy_version(
    session: AsyncSession,
    strategy: Strategy,
    data: StrategyVersionCreateRequest,
) -> StrategyVersion:
    """The public (V1) creation flow: always persists ``definition_schema_version = 1``.

    A configuration carrying a V2 envelope is refused rather than stored as V1, where its
    fields would be silently ignored. V2 versions are created with ``create_strategy_version_v2``.
    """
    if "schema" in data.configuration or "schema_version" in data.configuration:
        raise StrategyVersionValidationError(
            "V2 strategy definitions are not accepted by this endpoint"
        )
    return await _create_version(
        session,
        strategy,
        data.instrument_id,
        data.configuration,
        data.backtest_configuration,
        V1_SCHEMA_VERSION,
    )


async def create_strategy_version_v2(
    session: AsyncSession,
    strategy: Strategy,
    *,
    instrument_id: uuid.UUID,
    configuration: dict,
    backtest_configuration: dict,
) -> StrategyVersion:
    """Internal entry point (no public API yet): persist a V2 definition as version 2.

    The document must pass schema and semantic validation before it is stored. Runtime
    capabilities are checked when a backtest executes, not here, so a valid definition that
    needs a future capability can still be saved.
    """
    try:
        load_definition_for_version(
            V2_SCHEMA_VERSION,
            configuration,
            backtest_configuration,
            check_runtime_capabilities=False,
        )
    except (StrategyDefinitionError, RuntimeSetupError) as exc:
        raise StrategyVersionValidationError(f"Invalid V2 definition: {exc}") from exc
    return await _create_version(
        session,
        strategy,
        instrument_id,
        configuration,
        backtest_configuration,
        V2_SCHEMA_VERSION,
    )


async def _create_version(
    session: AsyncSession,
    strategy: Strategy,
    instrument_id: uuid.UUID,
    configuration: dict,
    backtest_configuration: dict,
    definition_schema_version: int,
) -> StrategyVersion:
    instrument = await session.scalar(
        select(Instrument)
        .join(Exchange)
        .where(Instrument.id == instrument_id)
        .options(selectinload(Instrument.exchange))
    )
    if instrument is None:
        raise StrategyVersionValidationError("Instrument not found")
    if not instrument.is_active:
        raise StrategyVersionValidationError("Instrument is inactive")
    if not instrument.exchange.is_active:
        raise StrategyVersionValidationError("Instrument Exchange is inactive")

    legacy_identity = configuration.get("instrument")
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
        definition_schema_version=definition_schema_version,
        configuration=configuration,
        backtest_configuration=backtest_configuration,
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
