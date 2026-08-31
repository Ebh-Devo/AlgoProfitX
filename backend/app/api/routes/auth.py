from typing import Annotated

import hmac
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.abuse import (
    RateLimitRule,
    abuse_controller,
    normalized_account_key,
    normalized_client_ip,
    record_authentication_failure,
)
from app.core.config import get_settings
from app.core.metrics import metrics
from app.core.observability import log_event
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
from app.services.auth_session import (
    RefreshSessionError,
    create_refresh_session,
    revoke_refresh_session,
    rotate_refresh_session,
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


def _set_session_cookies(response: Response, refresh_token: str, csrf_token: str) -> None:
    settings = get_settings()
    max_age = settings.refresh_token_expire_days * 24 * 60 * 60
    common = {
        "secure": settings.auth_cookie_secure,
        "samesite": settings.auth_cookie_samesite,
        "path": settings.auth_cookie_path,
        "domain": settings.auth_cookie_domain,
        "max_age": max_age,
    }
    response.set_cookie(
        settings.auth_refresh_cookie_name,
        refresh_token,
        httponly=settings.auth_cookie_httponly,
        **common,
    )
    response.set_cookie(
        settings.auth_csrf_cookie_name,
        csrf_token,
        httponly=False,
        **common,
    )


def _clear_session_cookies(response: Response) -> None:
    settings = get_settings()
    for name in (settings.auth_refresh_cookie_name, settings.auth_csrf_cookie_name):
        response.delete_cookie(
            name,
            path=settings.auth_cookie_path,
            domain=settings.auth_cookie_domain,
            secure=settings.auth_cookie_secure,
            httponly=name == settings.auth_refresh_cookie_name,
            samesite=settings.auth_cookie_samesite,
        )


def _require_csrf(request: Request) -> None:
    settings = get_settings()
    cookie_token = request.cookies.get(settings.auth_csrf_cookie_name, "")
    header_token = request.headers.get("X-CSRF-Token", "")
    if not cookie_token or not header_token or not hmac.compare_digest(
        cookie_token, header_token
    ):
        raise HTTPException(status_code=403, detail="CSRF validation failed")


def _refresh_cookie(request: Request) -> str:
    settings = get_settings()
    token = request.cookies.get(settings.auth_refresh_cookie_name)
    if not token:
        raise HTTPException(status_code=401, detail="Invalid refresh session")
    return token


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
    response: Response,
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
        metrics.increment("authentication.failures", tags={"reason": "invalid_credentials"})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    _, refresh_token = await create_refresh_session(session, user.id)
    await session.commit()
    _set_session_cookies(response, refresh_token, secrets.token_urlsafe(32))
    access_token = create_access_token(str(user.id))

    return TokenResponse(
        access_token=access_token,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, response: Response, session: Annotated[AsyncSession, Depends(get_session)]):
    _require_csrf(request)
    refresh_token = _refresh_cookie(request)
    try:
        user, rotated_token = await rotate_refresh_session(session, refresh_token)
        await session.commit()
    except RefreshSessionError as exc:
        if exc.suspicious_reuse:
            await session.commit()
            log_event("refresh_token_reuse_detected", level=30)
            metrics.increment("authentication.failures", tags={"reason": "refresh_reuse"})
        error_response = JSONResponse(
            status_code=401, content={"detail": "Invalid refresh session"}
        )
        _clear_session_cookies(error_response)
        return error_response
    _set_session_cookies(response, rotated_token, secrets.token_urlsafe(32))
    return TokenResponse(access_token=create_access_token(str(user.id)))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, session: Annotated[AsyncSession, Depends(get_session)]):
    _require_csrf(request)
    refresh_token = _refresh_cookie(request)
    try:
        await revoke_refresh_session(session, refresh_token)
        await session.commit()
        log_event("session_revoked")
    except RefreshSessionError:
        await session.rollback()
    _clear_session_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT


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
