from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import AppEnvironment, get_settings
from app.db.session import get_session
from app.models.strategy import Strategy
from app.persistence.catalyst import CatalystPersistenceClient, CatalystStrategyRepository
from app.persistence.strategy import StrategyRecord
from app.schemas.marketplace import MarketplaceStrategyResponse
from app.services.marketplace import (
    get_marketplace_strategies,
    get_marketplace_strategy_by_slug,
)


router = APIRouter(
    prefix="/marketplace/strategies",
    tags=["Marketplace"],
)


def serialize_marketplace_strategy(
    strategy: Strategy | StrategyRecord,
    current_version_number: int | None,
) -> MarketplaceStrategyResponse:
    return MarketplaceStrategyResponse(
        id=strategy.id,
        slug=strategy.slug,
        name=strategy.name,
        description=strategy.description,
        status=strategy.status,
        published_at=strategy.published_at,
        current_version_id=strategy.current_version_id,
        current_version_number=current_version_number,
    )


@router.get("", response_model=list[MarketplaceStrategyResponse])
async def list_marketplace_strategies(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    if get_settings().app_env is AppEnvironment.DEVELOPMENT:
        strategies = await CatalystStrategyRepository(
            CatalystPersistenceClient(request=request)
        ).list_marketplace(limit=limit, offset=offset)
        return [
            serialize_marketplace_strategy(strategy, version_number)
            for strategy, version_number in strategies
        ]
    strategies = await get_marketplace_strategies(
        session=session,
        limit=limit,
        offset=offset,
    )
    return [
        serialize_marketplace_strategy(strategy, version_number)
        for strategy, version_number in strategies
    ]


@router.get("/{slug}", response_model=MarketplaceStrategyResponse)
async def get_marketplace_strategy(
    slug: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    if get_settings().app_env is AppEnvironment.DEVELOPMENT:
        marketplace_strategy = await CatalystStrategyRepository(
            CatalystPersistenceClient(request=request)
        ).get_marketplace_by_slug(slug)
    else:
        marketplace_strategy = await get_marketplace_strategy_by_slug(
            session=session,
            slug=slug,
        )
    if marketplace_strategy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Marketplace strategy not found",
        )

    strategy, version_number = marketplace_strategy
    return serialize_marketplace_strategy(strategy, version_number)
