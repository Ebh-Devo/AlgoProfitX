import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_investor
from app.core.config import AppEnvironment, get_settings
from app.db.session import get_session
from app.models.user import User
from app.persistence.catalyst import CatalystAllocationRepository, CatalystPersistenceClient
from app.persistence.catalyst.allocation import (
    CatalystAllocationConflict,
    CatalystAllocationEligibilityError,
)
from app.schemas.allocation import (
    AllocationCreateRequest,
    AllocationResponse,
    AllocationUpdateRequest,
)
from app.services.allocation import (
    AllocationConflict,
    AllocationEligibilityError,
    create_allocation,
    delete_allocation,
    get_allocation,
    get_allocations_for_investor,
    update_allocation,
)
from app.services.strategy import UnsupportedExecutionVersionError


router = APIRouter(prefix="/allocations", tags=["Allocations"])


def _uses_catalyst_allocations() -> bool:
    return get_settings().uses_catalyst_persistence


def _catalyst_repository(request: Request) -> CatalystAllocationRepository:
    return CatalystAllocationRepository(CatalystPersistenceClient(request=request))


@router.post("", response_model=AllocationResponse, status_code=status.HTTP_201_CREATED)
async def create_allocation_intent(
    data: AllocationCreateRequest,
    request: Request,
    current_user: Annotated[User, Depends(require_investor)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    try:
        if _uses_catalyst_allocations():
            return await _catalyst_repository(request).create(
                investor_user_id=current_user.id,
                strategy_id=data.strategy_id,
                notional_amount=data.notional_amount,
                currency=data.currency,
            )
        allocation = await create_allocation(session, current_user.id, data)
        await session.commit()
    except UnsupportedExecutionVersionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.detail())
    except (AllocationEligibilityError, CatalystAllocationEligibilityError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return allocation


@router.get("", response_model=list[AllocationResponse])
async def list_allocation_intents(
    request: Request,
    current_user: Annotated[User, Depends(require_investor)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    if _uses_catalyst_allocations():
        return await _catalyst_repository(request).list_for_investor(current_user.id)
    return await get_allocations_for_investor(session, current_user.id)


@router.get("/{allocation_id}", response_model=AllocationResponse)
async def get_allocation_intent(
    allocation_id: uuid.UUID,
    request: Request,
    current_user: Annotated[User, Depends(require_investor)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    if _uses_catalyst_allocations():
        allocation = await _catalyst_repository(request).get_owned(
            allocation_id, current_user.id
        )
        if allocation is None:
            raise HTTPException(status_code=404, detail="Allocation not found")
        return allocation
    return await _get_owned_allocation(session, allocation_id, current_user.id)


@router.patch("/{allocation_id}", response_model=AllocationResponse)
async def update_allocation_intent(
    allocation_id: uuid.UUID,
    data: AllocationUpdateRequest,
    request: Request,
    current_user: Annotated[User, Depends(require_investor)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    if _uses_catalyst_allocations():
        allocation = await _catalyst_repository(request).update_owned(
            allocation_id=allocation_id,
            investor_user_id=current_user.id,
            updates=data.model_dump(exclude_unset=True),
        )
        if allocation is None:
            raise HTTPException(status_code=404, detail="Allocation not found")
        return allocation
    allocation = await _get_owned_allocation(session, allocation_id, current_user.id)
    allocation = await update_allocation(session, allocation, data)
    await session.commit()
    return allocation


@router.delete("/{allocation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_allocation_intent(
    allocation_id: uuid.UUID,
    request: Request,
    current_user: Annotated[User, Depends(require_investor)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    try:
        if _uses_catalyst_allocations():
            deleted = await _catalyst_repository(request).delete_owned(
                allocation_id, current_user.id
            )
            if not deleted:
                raise HTTPException(status_code=404, detail="Allocation not found")
            return
        allocation = await _get_owned_allocation(session, allocation_id, current_user.id)
        await delete_allocation(session, allocation)
        await session.commit()
    except (AllocationConflict, CatalystAllocationConflict) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


async def _get_owned_allocation(
    session: AsyncSession,
    allocation_id: uuid.UUID,
    investor_user_id: uuid.UUID,
):
    allocation = await get_allocation(session, allocation_id, investor_user_id)
    if allocation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Allocation not found",
        )
    return allocation
