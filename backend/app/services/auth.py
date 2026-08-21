from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import Role, User, UserProfile, user_roles
from app.schemas.auth import RegisterRequest
from app.core.security import hash_password, verify_password


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
        raise ValueError("Email is already registered")

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

    if user is None:
        return None

    if not user.is_active:
        return None

    if not verify_password(password, user.password_hash):
        return None

    return user
