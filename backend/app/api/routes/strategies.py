import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.abuse import RateLimitRule, abuse_controller
from app.core.config import AppEnvironment, get_settings
from app.core.dependencies import require_creator
from app.db.session import get_session
from app.models.strategy import Strategy, StrategyStatus
from app.models.user import User
from app.instrument_identity import SYNTHETIC_EQUITY_ID, SYNTHETIC_EQUITY_SYMBOLS
from app.persistence.catalyst import CatalystPersistenceClient, CatalystStrategyRepository
from app.persistence.strategy import (
    DuplicateStrategySlug,
    ExchangeSnapshotRecord,
    InstrumentSnapshotRecord,
)
from app.schemas.backtest import (
    BacktestAnalyticsResponse,
    BacktestCreateRequest,
    BacktestResponse,
)
from app.services.analytics import (
    BacktestAnalyticsConflict,
    BacktestAnalyticsDataError,
    build_backtest_analytics,
)
from app.schemas.strategy import (
    StrategyCreateRequest,
    StrategyResponse,
    StrategyUpdateRequest,
    StrategyVersionCreateRequest,
    StrategyVersionResponse,
)
from app.services.strategy import (
    StrategyConflict,
    StrategyVersionValidationError,
    archive_strategy,
    create_strategy_version,
    create_strategy,
    delete_strategy,
    deploy_strategy,
    get_strategies_for_creator,
    get_strategy,
    get_strategy_version,
    get_strategy_versions,
    publish_strategy,
    update_strategy,
)
from app.services.backtest import (
    BacktestExecutionConflict,
    create_backtest,
    execute_backtest,
    get_backtest,
    get_backtests_for_strategy_version,
)
from app.services.instrument import get_instrument


router = APIRouter(
    prefix="/strategies",
    tags=["Strategies"],
)


def _uses_catalyst_strategies() -> bool:
    return get_settings().app_env is AppEnvironment.DEVELOPMENT


def _catalyst_repository(request: Request) -> CatalystStrategyRepository:
    return CatalystStrategyRepository(CatalystPersistenceClient(request=request))


async def _validated_instrument_snapshot(
    session: AsyncSession, data: StrategyVersionCreateRequest
) -> InstrumentSnapshotRecord:
    instrument = await get_instrument(session, data.instrument_id)
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
            matching_symbols.update(
                symbol.casefold() for symbol in SYNTHETIC_EQUITY_SYMBOLS
            )
        if (
            not isinstance(legacy_identity, str)
            or legacy_identity.casefold() not in matching_symbols
        ):
            raise StrategyVersionValidationError(
                "configuration.instrument conflicts with instrument_id"
            )
    exchange = instrument.exchange
    return InstrumentSnapshotRecord(
        id=instrument.id,
        exchange=ExchangeSnapshotRecord(
            id=exchange.id,
            code=exchange.code,
            name=exchange.name,
            country_code=exchange.country_code,
            timezone=exchange.timezone,
            default_currency=exchange.default_currency,
            calendar_code=exchange.calendar_code,
            is_active=exchange.is_active,
        ),
        canonical_symbol=instrument.canonical_symbol,
        exchange_symbol=instrument.exchange_symbol,
        name=instrument.name,
        instrument_type=instrument.instrument_type,
        quote_currency=instrument.quote_currency,
        tick_size=instrument.tick_size,
        lot_size=instrument.lot_size,
        is_tradeable=instrument.is_tradeable,
        isin=instrument.isin,
        is_synthetic=instrument.is_synthetic,
        is_active=instrument.is_active,
        created_at=instrument.created_at,
        updated_at=instrument.updated_at,
    )


@router.post(
    "",
    response_model=StrategyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create(
    data: StrategyCreateRequest,
    request: Request,
    current_user: Annotated[
        User,
        Depends(require_creator),
    ],
    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],
):
    try:
        if _uses_catalyst_strategies():
            strategy = await _catalyst_repository(request).create_strategy(
                creator_id=current_user.id,
                name=data.name,
                slug=data.slug,
                description=data.description,
            )
        else:
            strategy = await create_strategy(
                session=session,
                creator_id=current_user.id,
                data=data,
            )
            await session.commit()

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    return strategy


@router.get(
    "",
    response_model=list[StrategyResponse],
)
async def list_my_strategies(
    request: Request,
    current_user: Annotated[
        User,
        Depends(require_creator),
    ],
    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],
):
    if _uses_catalyst_strategies():
        return await _catalyst_repository(request).list_strategies(current_user.id)
    return await get_strategies_for_creator(
        session=session,
        creator_id=current_user.id,
    )


@router.post(
    "/{strategy_id}/versions",
    response_model=StrategyVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_version(
    strategy_id: uuid.UUID,
    data: StrategyVersionCreateRequest,
    request: Request,
    current_user: Annotated[User, Depends(require_creator)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    if _uses_catalyst_strategies():
        repository = _catalyst_repository(request)
        strategy = await repository.get_strategy(
            strategy_id=strategy_id, creator_id=current_user.id
        )
        if strategy is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy not found",
            )
        try:
            instrument = await _validated_instrument_snapshot(session, data)
            return await repository.create_version(
                strategy_id=strategy_id,
                creator_id=current_user.id,
                instrument=instrument,
                configuration=data.configuration,
                backtest_configuration=data.backtest_configuration,
            )
        except StrategyVersionValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            )

    strategy = await get_strategy(
        session=session,
        strategy_id=strategy_id,
        creator_id=current_user.id,
    )

    if strategy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )

    try:
        version = await create_strategy_version(
            session=session,
            strategy=strategy,
            data=data,
        )
        await session.commit()
    except StrategyVersionValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    return version


@router.get(
    "/{strategy_id}/versions",
    response_model=list[StrategyVersionResponse],
)
async def list_versions(
    strategy_id: uuid.UUID,
    request: Request,
    current_user: Annotated[User, Depends(require_creator)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    if _uses_catalyst_strategies():
        repository = _catalyst_repository(request)
        strategy = await repository.get_strategy(
            strategy_id=strategy_id, creator_id=current_user.id
        )
        if strategy is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy not found",
            )
        return await repository.list_versions(
            strategy_id=strategy_id, creator_id=current_user.id
        )

    strategy = await get_strategy(
        session=session,
        strategy_id=strategy_id,
        creator_id=current_user.id,
    )

    if strategy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )

    return await get_strategy_versions(session=session, strategy_id=strategy.id)


@router.get(
    "/{strategy_id}/versions/{version_id}",
    response_model=StrategyVersionResponse,
)
async def get_version(
    strategy_id: uuid.UUID,
    version_id: uuid.UUID,
    request: Request,
    current_user: Annotated[User, Depends(require_creator)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    if _uses_catalyst_strategies():
        repository = _catalyst_repository(request)
        strategy = await repository.get_strategy(
            strategy_id=strategy_id, creator_id=current_user.id
        )
        if strategy is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy not found",
            )
        version = await repository.get_version(
            strategy_id=strategy_id,
            version_id=version_id,
            creator_id=current_user.id,
        )
        if version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy version not found",
            )
        return version

    strategy = await get_strategy(
        session=session,
        strategy_id=strategy_id,
        creator_id=current_user.id,
    )

    if strategy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )

    version = await get_strategy_version(
        session=session,
        strategy_id=strategy.id,
        version_id=version_id,
    )

    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy version not found",
        )

    return version


async def _get_owned_strategy_version(
    session: AsyncSession,
    strategy_id: uuid.UUID,
    version_id: uuid.UUID,
    creator_id: uuid.UUID,
):
    strategy = await get_strategy(
        session=session,
        strategy_id=strategy_id,
        creator_id=creator_id,
    )
    if strategy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )

    version = await get_strategy_version(
        session=session,
        strategy_id=strategy.id,
        version_id=version_id,
    )
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy version not found",
        )

    return version


@router.post(
    "/{strategy_id}/versions/{version_id}/backtests",
    response_model=BacktestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_backtest_request(
    strategy_id: uuid.UUID,
    version_id: uuid.UUID,
    data: BacktestCreateRequest,
    current_user: Annotated[User, Depends(require_creator)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    settings = get_settings()
    user_key = str(current_user.id)
    await abuse_controller.enforce(
        (
            RateLimitRule(
                "backtest_burst_user",
                user_key,
                settings.backtest_burst_limit,
                settings.backtest_burst_window_seconds,
            ),
            RateLimitRule(
                "backtest_sustained_user",
                user_key,
                settings.backtest_sustained_limit,
                settings.backtest_sustained_window_seconds,
            ),
        ),
        settings.abuse_protection_enabled,
    )
    version = await _get_owned_strategy_version(
        session=session,
        strategy_id=strategy_id,
        version_id=version_id,
        creator_id=current_user.id,
    )
    backtest = await create_backtest(
        session=session,
        strategy_version=version,
        requested_by_user_id=current_user.id,
        data=data,
    )
    await session.commit()
    return backtest


@router.get(
    "/{strategy_id}/versions/{version_id}/backtests",
    response_model=list[BacktestResponse],
)
async def list_backtest_requests(
    strategy_id: uuid.UUID,
    version_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_creator)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    version = await _get_owned_strategy_version(
        session=session,
        strategy_id=strategy_id,
        version_id=version_id,
        creator_id=current_user.id,
    )
    return await get_backtests_for_strategy_version(
        session=session,
        strategy_version_id=version.id,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{strategy_id}/versions/{version_id}/backtests/{backtest_id}",
    response_model=BacktestResponse,
)
async def get_backtest_request(
    strategy_id: uuid.UUID,
    version_id: uuid.UUID,
    backtest_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_creator)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    version = await _get_owned_strategy_version(
        session=session,
        strategy_id=strategy_id,
        version_id=version_id,
        creator_id=current_user.id,
    )
    backtest = await get_backtest(
        session=session,
        strategy_version_id=version.id,
        backtest_id=backtest_id,
    )
    if backtest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest not found",
        )
    return backtest


@router.post(
    "/{strategy_id}/versions/{version_id}/backtests/{backtest_id}/execute",
    response_model=BacktestResponse,
)
async def execute_backtest_request(
    strategy_id: uuid.UUID,
    version_id: uuid.UUID,
    backtest_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_creator)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    settings = get_settings()
    if settings.backtest_execution_mode == "disabled":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Backtest execution is temporarily unavailable",
        )
    user_key = str(current_user.id)
    await abuse_controller.enforce(
        (
            RateLimitRule(
                "backtest_burst_user",
                user_key,
                settings.backtest_burst_limit,
                settings.backtest_burst_window_seconds,
            ),
            RateLimitRule(
                "backtest_sustained_user",
                user_key,
                settings.backtest_sustained_limit,
                settings.backtest_sustained_window_seconds,
            ),
        ),
        settings.abuse_protection_enabled,
    )
    version = await _get_owned_strategy_version(
        session=session,
        strategy_id=strategy_id,
        version_id=version_id,
        creator_id=current_user.id,
    )
    backtest = await get_backtest(
        session=session,
        strategy_version_id=version.id,
        backtest_id=backtest_id,
    )
    if backtest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest not found",
        )

    async with abuse_controller.concurrency.slot(
        "backtest_execution_user",
        user_key,
        settings.backtest_max_concurrency_per_user,
    ):
        try:
            if settings.backtest_execution_mode == "worker":
                return backtest
            return await execute_backtest(session, backtest.id)
        except BacktestExecutionConflict as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            )


@router.get(
    "/{strategy_id}/versions/{version_id}/backtests/{backtest_id}/analytics",
    response_model=BacktestAnalyticsResponse,
)
async def get_backtest_analytics(
    strategy_id: uuid.UUID,
    version_id: uuid.UUID,
    backtest_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_creator)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    version = await _get_owned_strategy_version(
        session=session,
        strategy_id=strategy_id,
        version_id=version_id,
        creator_id=current_user.id,
    )
    backtest = await get_backtest(
        session=session,
        strategy_version_id=version.id,
        backtest_id=backtest_id,
    )
    if backtest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest not found",
        )

    try:
        return build_backtest_analytics(backtest)
    except (BacktestAnalyticsConflict, BacktestAnalyticsDataError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )


@router.post(
    "/{strategy_id}/publish",
    response_model=StrategyResponse,
)
async def publish(
    strategy_id: uuid.UUID,
    request: Request,
    current_user: Annotated[User, Depends(require_creator)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    if _uses_catalyst_strategies():
        try:
            strategy = await _catalyst_repository(request).transition_strategy(
                strategy_id=strategy_id,
                creator_id=current_user.id,
                target=StrategyStatus.PUBLISHED,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=str(exc)
            )
        if strategy is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found"
            )
        return strategy

    strategy = await get_strategy(
        session=session,
        strategy_id=strategy_id,
        creator_id=current_user.id,
    )

    if strategy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )

    try:
        strategy = await publish_strategy(session=session, strategy=strategy)
        await session.commit()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    return strategy


@router.post(
    "/{strategy_id}/deploy",
    response_model=StrategyResponse,
)
async def deploy(
    strategy_id: uuid.UUID,
    request: Request,
    current_user: Annotated[User, Depends(require_creator)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    if _uses_catalyst_strategies():
        try:
            strategy = await _catalyst_repository(request).transition_strategy(
                strategy_id=strategy_id,
                creator_id=current_user.id,
                target=StrategyStatus.DEPLOYED,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=str(exc)
            )
        if strategy is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found"
            )
        return strategy

    strategy = await get_strategy(
        session=session,
        strategy_id=strategy_id,
        creator_id=current_user.id,
    )

    if strategy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )

    try:
        strategy = await deploy_strategy(session=session, strategy=strategy)
        await session.commit()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    return strategy


@router.post(
    "/{strategy_id}/archive",
    response_model=StrategyResponse,
)
async def archive(
    strategy_id: uuid.UUID,
    request: Request,
    current_user: Annotated[User, Depends(require_creator)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    if _uses_catalyst_strategies():
        try:
            strategy = await _catalyst_repository(request).transition_strategy(
                strategy_id=strategy_id,
                creator_id=current_user.id,
                target=StrategyStatus.ARCHIVED,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=str(exc)
            )
        if strategy is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found"
            )
        return strategy

    strategy = await get_strategy(
        session=session,
        strategy_id=strategy_id,
        creator_id=current_user.id,
    )

    if strategy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )

    try:
        strategy = await archive_strategy(session=session, strategy=strategy)
        await session.commit()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    return strategy


@router.get(
    "/{strategy_id}",
    response_model=StrategyResponse,
)
async def get_my_strategy(
    strategy_id: uuid.UUID,
    request: Request,
    current_user: Annotated[
        User,
        Depends(require_creator),
    ],
    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],
):
    if _uses_catalyst_strategies():
        strategy = await _catalyst_repository(request).get_strategy(
            strategy_id=strategy_id, creator_id=current_user.id
        )
        if strategy is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found"
            )
        return strategy

    strategy = await get_strategy(
        session=session,
        strategy_id=strategy_id,
        creator_id=current_user.id,
    )

    if strategy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )

    return strategy


@router.patch(
    "/{strategy_id}",
    response_model=StrategyResponse,
)
async def update_my_strategy(
    strategy_id: uuid.UUID,
    data: StrategyUpdateRequest,
    request: Request,
    current_user: Annotated[
        User,
        Depends(require_creator),
    ],
    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],
):
    if _uses_catalyst_strategies():
        try:
            strategy = await _catalyst_repository(request).update_strategy(
                strategy_id=strategy_id,
                creator_id=current_user.id,
                updates=data.model_dump(exclude_unset=True),
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=str(exc)
            )
        if strategy is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found"
            )
        return strategy

    strategy = await get_strategy(
        session=session,
        strategy_id=strategy_id,
        creator_id=current_user.id,
    )

    if strategy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )

    try:
        strategy = await update_strategy(
            session=session,
            strategy=strategy,
            data=data,
        )

        await session.commit()

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    return strategy


@router.delete(
    "/{strategy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_my_strategy(
    strategy_id: uuid.UUID,
    request: Request,
    current_user: Annotated[
        User,
        Depends(require_creator),
    ],
    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],
):
    if _uses_catalyst_strategies():
        try:
            deleted = await _catalyst_repository(request).delete_strategy(
                strategy_id=strategy_id, creator_id=current_user.id
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=str(exc)
            )
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found"
            )
        return None

    strategy = await get_strategy(
        session=session,
        strategy_id=strategy_id,
        creator_id=current_user.id,
    )

    if strategy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )

    try:
        await delete_strategy(
            session=session,
            strategy=strategy,
        )
        await session.commit()
    except StrategyConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
