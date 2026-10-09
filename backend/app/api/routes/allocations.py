import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_investor
from app.db.session import get_session
from app.models.user import User
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


@router.post("", response_model=AllocationResponse, status_code=status.HTTP_201_CREATED)
async def create_allocation_intent(
    data: AllocationCreateRequest,
    current_user: Annotated[User, Depends(require_investor)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    try:
        allocation = await create_allocation(session, current_user.id, data)
        await session.commit()
    except UnsupportedExecutionVersionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.detail())
    except AllocationEligibilityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return allocation


@router.get("", response_model=list[AllocationResponse])
async def list_allocation_intents(
    current_user: Annotated[User, Depends(require_investor)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    return await get_allocations_for_investor(session, current_user.id)


@router.get("/{allocation_id}", response_model=AllocationResponse)
async def get_allocation_intent(
    allocation_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_investor)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    return await _get_owned_allocation(session, allocation_id, current_user.id)


@router.patch("/{allocation_id}", response_model=AllocationResponse)
async def update_allocation_intent(
    allocation_id: uuid.UUID,
    data: AllocationUpdateRequest,
    current_user: Annotated[User, Depends(require_investor)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    allocation = await _get_owned_allocation(session, allocation_id, current_user.id)
    allocation = await update_allocation(session, allocation, data)
    await session.commit()
    return allocation


@router.delete("/{allocation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_allocation_intent(
    allocation_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_investor)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    allocation = await _get_owned_allocation(session, allocation_id, current_user.id)
    try:
        await delete_allocation(session, allocation)
        await session.commit()
    except AllocationConflict as exc:
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
