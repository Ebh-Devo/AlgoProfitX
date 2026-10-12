import asyncio
import hmac
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

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
from app.core.config import AppEnvironment, get_settings
from app.core.dependencies import get_current_user
from app.core.metrics import metrics
from app.core.observability import log_event
from app.core.security import create_access_token, hash_password, verify_password_or_decoy
from app.db.session import get_session
from app.models.user import User
from app.persistence.auth_session import SessionTokenRejected
from app.persistence.catalyst import (
    CatalystAuthSessionRepository,
    CatalystIdentityRepository,
    CatalystPersistenceClient,
)
from app.persistence.identity import DuplicateIdentityError, IdentityUser
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
    hash_refresh_token,
    new_refresh_token,
    revoke_refresh_session,
    rotate_refresh_session,
    session_id_from_token,
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


def _uses_catalyst_auth() -> bool:
    return get_settings().uses_catalyst_persistence


def _catalyst_auth_repositories(
    request: Request,
) -> tuple[CatalystIdentityRepository, CatalystAuthSessionRepository]:
    client = CatalystPersistenceClient(request=request)
    return CatalystIdentityRepository(client), CatalystAuthSessionRepository(client)


def _set_session_cookies(response: Response, refresh_token: str, csrf_token: str) -> None:
    settings = get_settings()
    max_age = settings.refresh_token_expire_days * 24 * 60 * 60
    common = {
        "secure": settings.auth_cookie_secure,
        "samesite": settings.auth_cookie_samesite,
        "max_age": max_age,
    }
    response.set_cookie(
        settings.auth_refresh_cookie_name,
        refresh_token,
        httponly=settings.auth_cookie_httponly,
        path=settings.auth_cookie_path,
        domain=settings.auth_cookie_domain,
        **common,
    )
    response.set_cookie(
        settings.auth_csrf_cookie_name,
        csrf_token,
        httponly=False,
        path=settings.auth_csrf_cookie_path,
        domain=settings.auth_csrf_cookie_domain,
        **common,
    )


def _clear_session_cookies(response: Response) -> None:
    settings = get_settings()
    cookie_scopes = (
        (
            settings.auth_refresh_cookie_name,
            settings.auth_cookie_path,
            settings.auth_cookie_domain,
            True,
        ),
        (
            settings.auth_csrf_cookie_name,
            settings.auth_csrf_cookie_path,
            settings.auth_csrf_cookie_domain,
            False,
        ),
    )
    for name, path, domain, httponly in cookie_scopes:
        response.delete_cookie(
            name,
            path=path,
            domain=domain,
            secure=settings.auth_cookie_secure,
            httponly=httponly,
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


def _unexpected_failure_response(request: Request, event: str) -> JSONResponse:
    """Generic 500 for an unexpected failure: never echo exception text to the client.

    The detail is logged server-side with the request id (log redaction scrubs secrets); the client
    gets a stable body carrying only that request id.
    """
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    log_event(event, level=logging.ERROR, exc_info=True, request_id=request_id)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "request_id": request_id},
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
        if _uses_catalyst_auth():
            identity, _ = _catalyst_auth_repositories(request)
            user = await identity.register_user(
                email=str(data.email),
                password_hash=await asyncio.to_thread(hash_password, data.password),
                full_name=data.full_name,
            )
        else:
            user = await register_user(session, data)
            await session.commit()
    except DuplicateIdentityError as exc:
        # A fixed, non-sensitive message raised only for a taken email address.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    except Exception:
        return _unexpected_failure_response(request, "registration_failed")

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
    identity: CatalystIdentityRepository | None = None
    auth_sessions: CatalystAuthSessionRepository | None = None
    if _uses_catalyst_auth():
        identity, auth_sessions = _catalyst_auth_repositories(request)
        user = await identity.get_user_by_email(str(data.email))
        # One full verification for every outcome (unknown, inactive, wrong password, success).
        matched = await asyncio.to_thread(
            verify_password_or_decoy,
            data.password,
            user.password_hash if user is not None else None,
        )
        if user is None or not user.is_active or not matched:
            user = None
    else:
        user = await authenticate_user(session, data.email, data.password)

    if user is None:
        record_authentication_failure(client_ip)
        metrics.increment("authentication.failures", tags={"reason": "invalid_credentials"})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if auth_sessions is not None:
        session_id = uuid.uuid4()
        refresh_token = new_refresh_token(session_id)
        await auth_sessions.create_session(
            session_id=session_id,
            user_id=user.id,
            refresh_token_hash=hash_refresh_token(refresh_token),
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.refresh_token_expire_days),
            max_sessions=settings.auth_max_sessions_per_user,
        )
    else:
        _, refresh_token = await create_refresh_session(session, user.id)
        await session.commit()
    _set_session_cookies(response, refresh_token, secrets.token_urlsafe(32))
    access_token = create_access_token(str(user.id))

    return TokenResponse(
        access_token=access_token,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    _require_csrf(request)
    refresh_token = _refresh_cookie(request)
    uses_catalyst = _uses_catalyst_auth()
    try:
        if uses_catalyst:
            identity, auth_sessions = _catalyst_auth_repositories(request)
            session_id = session_id_from_token(refresh_token)
            rotated_token = new_refresh_token(session_id)
            rotated = await auth_sessions.rotate_session(
                session_id=session_id,
                supplied_token_hash=hash_refresh_token(refresh_token),
                replacement_token_hash=hash_refresh_token(rotated_token),
            )
            user = await identity.get_user_by_id(rotated.user_id)
            if user is None or not user.is_active:
                await auth_sessions.revoke_session(
                    session_id=session_id,
                    supplied_token_hash=hash_refresh_token(rotated_token),
                )
                raise SessionTokenRejected()
        else:
            user, rotated_token = await rotate_refresh_session(session, refresh_token)
            await session.commit()
    except (RefreshSessionError, SessionTokenRejected) as exc:
        if exc.suspicious_reuse:
            if not uses_catalyst:
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
async def logout(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    _require_csrf(request)
    refresh_token = _refresh_cookie(request)
    uses_catalyst = _uses_catalyst_auth()
    try:
        if uses_catalyst:
            _, auth_sessions = _catalyst_auth_repositories(request)
            await auth_sessions.revoke_session(
                session_id=session_id_from_token(refresh_token),
                supplied_token_hash=hash_refresh_token(refresh_token),
            )
        else:
            await revoke_refresh_session(session, refresh_token)
            await session.commit()
        log_event("session_revoked")
    except (RefreshSessionError, SessionTokenRejected):
        if not uses_catalyst:
            await session.rollback()
    _clear_session_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT


@router.post(
    "/creator/enroll",
    response_model=UserResponse,
)
async def enroll_as_creator(
    request: Request,
    current_user: Annotated[User | IdentityUser, Depends(get_current_user)],
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
        if _uses_catalyst_auth():
            identity, _ = _catalyst_auth_repositories(request)
            user = await identity.enroll_creator(current_user.id)
        else:
            user = await enroll_creator(session, current_user)
            await session.commit()
    except Exception:
        return _unexpected_failure_response(request, "creator_enrollment_failed")

    return user


@router.get(
    "/me",
    response_model=UserResponse,
)
async def me(
    current_user: Annotated[User | IdentityUser, Depends(get_current_user)],
):
    return current_user
