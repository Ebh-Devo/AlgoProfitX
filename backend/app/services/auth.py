from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import Role, User, UserProfile, user_roles
from app.schemas.auth import RegisterRequest
from app.core.security import hash_password, verify_password_or_decoy
from app.persistence.identity import DuplicateIdentityError


DEFAULT_ROLE = "INVESTOR"
CREATOR_ROLE = "CREATOR"


async def get_user_by_email(
    session: AsyncSession,
    email: str,
) -> User | None:
    result = await session.execute(
        select(User).where(User.email == email.lower())
    )

    return result.scalar_one_or_none()


async def register_user(
    session: AsyncSession,
    data: RegisterRequest,
) -> User:
    email = data.email.lower()

    existing_user = await get_user_by_email(session, email)

    if existing_user is not None:
        raise DuplicateIdentityError("Email is already registered")

    role_result = await session.execute(
        select(Role).where(Role.name == DEFAULT_ROLE)
    )

    role = role_result.scalar_one_or_none()

    if role is None:
        raise RuntimeError("Default user role is not configured")

    user = User(
        email=email,
        password_hash=hash_password(data.password),
    )

    user.roles.append(role)

    if data.full_name:
        user.profile = UserProfile(
            full_name=data.full_name,
        )

    session.add(user)

    await session.flush()
    await session.refresh(user, attribute_names=["roles"])

    return user


async def enroll_creator(
    session: AsyncSession,
    user: User,
) -> User:
    role_result = await session.execute(
        select(Role).where(Role.name == CREATOR_ROLE)
    )
    creator_role = role_result.scalar_one_or_none()

    if creator_role is None:
        raise RuntimeError("Creator role is not configured")

    await session.execute(
        insert(user_roles)
        .values(user_id=user.id, role_id=creator_role.id)
        .on_conflict_do_nothing(index_elements=["user_id", "role_id"])
    )

    await session.refresh(user, attribute_names=["roles"])
    return user


async def authenticate_user(
    session: AsyncSession,
    email: str,
    password: str,
) -> User | None:
    user = await get_user_by_email(session, email.lower())

    # One full verification for every outcome (unknown, inactive, wrong password, success), so
    # timing does not reveal whether the account exists or is active.
    matched = verify_password_or_decoy(
        password, user.password_hash if user is not None else None
    )
    if user is None or not user.is_active or not matched:
        return None

    return user
