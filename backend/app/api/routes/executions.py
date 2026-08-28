import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.abuse import RateLimitRule, abuse_controller
from app.core.config import get_settings
from app.core.dependencies import require_investor
from app.db.session import get_session
from app.models.user import User
from app.schemas.execution import ExecutionIntentCreateRequest, ExecutionIntentResponse
from app.services.execution import (
    ExecutionIntentConflict,
    ExecutionIntentEligibilityError,
    PaperExecutionConflict,
    create_execution_intent,
    execute_paper_execution_intent,
    get_execution_intent,
    get_execution_intents_for_investor,
)


router = APIRouter(tags=["Execution Intents"])


async def _enforce_execution_limit(user_id: uuid.UUID) -> None:
    settings = get_settings()
    user_key = str(user_id)
    await abuse_controller.enforce(
        (
            RateLimitRule(
                "execution_burst_user",
                user_key,
                settings.execution_burst_limit,
                settings.execution_burst_window_seconds,
            ),
            RateLimitRule(
                "execution_sustained_user",
                user_key,
                settings.execution_sustained_limit,
                settings.execution_sustained_window_seconds,
            ),
        ),
        settings.abuse_protection_enabled,
    )


@router.post(
    "/allocations/{allocation_id}/execution-intents",
    response_model=ExecutionIntentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_execution_intent_request(
    allocation_id: uuid.UUID,
    data: ExecutionIntentCreateRequest,
    response: Response,
    current_user: Annotated[User, Depends(require_investor)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    await _enforce_execution_limit(current_user.id)
    try:
        execution_intent, created = await create_execution_intent(
            session,
            allocation_id,
            current_user.id,
            data.idempotency_key,
        )
        if created:
            await session.commit()
        else:
            response.status_code = status.HTTP_200_OK
        return execution_intent
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except (ExecutionIntentConflict, ExecutionIntentEligibilityError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get("/execution-intents", response_model=list[ExecutionIntentResponse])
async def list_execution_intent_requests(
    current_user: Annotated[User, Depends(require_investor)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    return await get_execution_intents_for_investor(session, current_user.id)


@router.get(
    "/execution-intents/{execution_intent_id}",
    response_model=ExecutionIntentResponse,
)
async def get_execution_intent_request(
    execution_intent_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_investor)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    execution_intent = await get_execution_intent(
        session,
        execution_intent_id,
        current_user.id,
    )
    if execution_intent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution intent not found",
        )
    return execution_intent


@router.post(
    "/execution-intents/{execution_intent_id}/execute",
    response_model=ExecutionIntentResponse,
)
async def execute_paper_execution_intent_request(
    execution_intent_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_investor)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    await _enforce_execution_limit(current_user.id)
    try:
        return await execute_paper_execution_intent(
            session,
            execution_intent_id,
            current_user.id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except PaperExecutionConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
