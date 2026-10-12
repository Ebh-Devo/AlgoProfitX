import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import AppEnvironment, get_settings
from app.core.security import decode_access_token
from app.db.session import get_session
from app.models.user import User
from app.persistence.catalyst import CatalystIdentityRepository, CatalystPersistenceClient
from app.persistence.identity import IdentityUser


bearer_scheme = HTTPBearer()
CREATOR_ROLE = "CREATOR"
INVESTOR_ROLE = "INVESTOR"


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials,
        Depends(bearer_scheme),
    ],
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User | IdentityUser:
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = uuid.UUID(payload["sub"])
    except (ValueError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if get_settings().uses_catalyst_persistence:
        user = await CatalystIdentityRepository(
            CatalystPersistenceClient(request=request)
        ).get_user_by_id(user_id)
    else:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def require_creator(
    current_user: Annotated[User | IdentityUser, Depends(get_current_user)],
) -> User | IdentityUser:
    if not any(role.name == CREATOR_ROLE for role in current_user.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Creator role is required",
        )

    return current_user


async def require_investor(
    current_user: Annotated[User | IdentityUser, Depends(get_current_user)],
) -> User | IdentityUser:
    if not any(role.name == INVESTOR_ROLE for role in current_user.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Investor role is required",
        )

    return current_user
