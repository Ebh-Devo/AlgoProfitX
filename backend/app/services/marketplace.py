from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.strategy import Strategy, StrategyStatus, StrategyVersion


DISCOVERABLE_STATUSES = (
    StrategyStatus.PUBLISHED,
    StrategyStatus.DEPLOYED,
)


def _marketplace_query():
    return (
        select(
            Strategy,
            StrategyVersion.version_number.label("current_version_number"),
        )
        .outerjoin(
            StrategyVersion,
            Strategy.current_version_id == StrategyVersion.id,
        )
        .where(
            Strategy.status.in_(DISCOVERABLE_STATUSES),
            Strategy.is_public.is_(True),
        )
    )


async def get_marketplace_strategies(
    session: AsyncSession,
    limit: int,
    offset: int,
) -> list[tuple[Strategy, int | None]]:
    result = await session.execute(
        _marketplace_query()
        .order_by(Strategy.published_at.desc(), Strategy.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.tuples().all())


async def get_marketplace_strategy_by_slug(
    session: AsyncSession,
    slug: str,
) -> tuple[Strategy, int | None] | None:
    result = await session.execute(
        _marketplace_query().where(Strategy.slug == slug)
    )
    return result.tuples().one_or_none()
