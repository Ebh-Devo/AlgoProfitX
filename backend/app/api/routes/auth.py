from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.abuse import (
    RateLimitRule,
    abuse_controller,
    normalized_account_key,
    normalized_client_ip,
    record_authentication_failure,
)
from app.core.config import get_settings
from app.core.dependencies import get_current_user
from app.core.security import create_access_token
from app.db.session import get_session
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth import authenticate_user, enroll_creator, register_user


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    data: RegisterRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    settings = get_settings()
    await abuse_controller.enforce(
        (
            RateLimitRule(
                "registration_ip",
                normalized_client_ip(request),
                settings.registration_ip_limit,
                settings.registration_ip_window_seconds,
            ),
        ),
        settings.abuse_protection_enabled,
    )
    try:
        user = await register_user(session, data)
        await session.commit()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )

    return user


@router.post(
    "/login",
    response_model=TokenResponse,
)
async def login(
    data: LoginRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    settings = get_settings()
    client_ip = normalized_client_ip(request)
    await abuse_controller.enforce(
        (
            RateLimitRule(
                "login_ip",
                client_ip,
                settings.login_ip_limit,
                settings.login_ip_window_seconds,
            ),
            RateLimitRule(
                "login_account",
                normalized_account_key(str(data.email)),
                settings.login_account_limit,
                settings.login_account_window_seconds,
            ),
        ),
        settings.abuse_protection_enabled,
    )
    user = await authenticate_user(
        session,
        data.email,
        data.password,
    )

    if user is None:
        record_authentication_failure(client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(str(user.id))

    return TokenResponse(
        access_token=access_token,
    )


@router.post(
    "/creator/enroll",
    response_model=UserResponse,
)
async def enroll_as_creator(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    settings = get_settings()
    await abuse_controller.enforce(
        (
            RateLimitRule(
                "creator_enrollment_user",
                str(current_user.id),
                settings.creator_enrollment_limit,
                settings.creator_enrollment_window_seconds,
            ),
        ),
        settings.abuse_protection_enabled,
    )
    try:
        user = await enroll_creator(session, current_user)
        await session.commit()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )

    return user


@router.get(
    "/me",
    response_model=UserResponse,
)
async def me(
    current_user: Annotated[User, Depends(get_current_user)],
):
    return current_user
