import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_creator
from app.db.session import get_session
from app.models.strategy import Strategy
from app.models.user import User
from app.schemas.backtest import BacktestCreateRequest, BacktestResponse
from app.schemas.strategy import (
    StrategyCreateRequest,
    StrategyResponse,
    StrategyUpdateRequest,
    StrategyVersionCreateRequest,
    StrategyVersionResponse,
)
from app.services.strategy import (
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
    create_backtest,
    get_backtest,
    get_backtests_for_strategy_version,
)


router = APIRouter(
    prefix="/strategies",
    tags=["Strategies"],
)


@router.post(
    "",
    response_model=StrategyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create(
    data: StrategyCreateRequest,
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
    current_user: Annotated[
        User,
        Depends(require_creator),
    ],
    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],
):
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
    current_user: Annotated[User, Depends(require_creator)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
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
    current_user: Annotated[User, Depends(require_creator)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
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
    current_user: Annotated[User, Depends(require_creator)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
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
    "/{strategy_id}/publish",
    response_model=StrategyResponse,
)
async def publish(
    strategy_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_creator)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
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
    current_user: Annotated[User, Depends(require_creator)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
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
    current_user: Annotated[User, Depends(require_creator)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
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
    current_user: Annotated[
        User,
        Depends(require_creator),
    ],
    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],
):
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
    current_user: Annotated[
        User,
        Depends(require_creator),
    ],
    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],
):
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
    current_user: Annotated[
        User,
        Depends(require_creator),
    ],
    session: Annotated[
        AsyncSession,
        Depends(get_session),
    ],
):
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

    await delete_strategy(
        session=session,
        strategy=strategy,
    )

    await session.commit()
