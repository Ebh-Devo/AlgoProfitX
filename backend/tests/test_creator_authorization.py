import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.user import Role, user_roles


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client


def unique_email() -> str:
    return f"creator-auth-{uuid.uuid4().hex}@example.com"


async def register_and_login(
    client: AsyncClient,
) -> tuple[dict[str, str], dict[str, object]]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": unique_email(), "password": "TestPassword123"},
    )
    assert response.status_code == 201
    registered = response.json()

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": registered["email"], "password": "TestPassword123"},
    )
    assert response.status_code == 200
    return (
        {"Authorization": f"Bearer {response.json()['access_token']}"},
        registered,
    )


@pytest.mark.asyncio
async def test_registration_assigns_investor_and_me_exposes_roles(client):
    headers, registered = await register_and_login(client)

    assert registered["roles"] == ["INVESTOR"]

    response = await client.get("/api/v1/auth/me", headers=headers)

    assert response.status_code == 200
    assert response.json()["roles"] == ["INVESTOR"]


@pytest.mark.asyncio
async def test_creator_enrollment_is_idempotent_and_preserves_investor(client):
    headers, registered = await register_and_login(client)

    first_response = await client.post(
        "/api/v1/auth/creator/enroll", headers=headers
    )
    second_response = await client.post(
        "/api/v1/auth/creator/enroll", headers=headers
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["roles"] == ["CREATOR", "INVESTOR"]
    assert second_response.json()["roles"] == ["CREATOR", "INVESTOR"]

    async with AsyncSessionLocal() as session:
        creator_memberships = await session.scalar(
            select(func.count())
            .select_from(user_roles.join(Role))
            .where(
                user_roles.c.user_id == uuid.UUID(registered["id"]),
                Role.name == "CREATOR",
            )
        )

    assert creator_memberships == 1


@pytest.mark.asyncio
async def test_creator_enrollment_requires_authentication(client):
    response = await client.post("/api/v1/auth/creator/enroll")

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("post", "/api/v1/strategies", {"name": "Investor Strategy", "slug": "investor-strategy"}),
        ("get", "/api/v1/strategies", None),
        ("get", "/api/v1/strategies/00000000-0000-0000-0000-000000000001", None),
        ("patch", "/api/v1/strategies/00000000-0000-0000-0000-000000000001", {"name": "Updated Strategy"}),
        ("delete", "/api/v1/strategies/00000000-0000-0000-0000-000000000001", None),
        ("post", "/api/v1/strategies/00000000-0000-0000-0000-000000000001/versions", {"instrument_id": "20000000-0000-4000-8000-000000000001", "configuration": {}}),
        ("get", "/api/v1/strategies/00000000-0000-0000-0000-000000000001/versions", None),
        ("get", "/api/v1/strategies/00000000-0000-0000-0000-000000000001/versions/00000000-0000-0000-0000-000000000002", None),
        ("post", "/api/v1/strategies/00000000-0000-0000-0000-000000000001/publish", None),
        ("post", "/api/v1/strategies/00000000-0000-0000-0000-000000000001/deploy", None),
        ("post", "/api/v1/strategies/00000000-0000-0000-0000-000000000001/archive", None),
    ],
)
async def test_investor_cannot_access_creator_strategy_endpoints(
    client,
    method,
    path,
    payload,
):
    headers, _ = await register_and_login(client)

    request_kwargs = {"headers": headers}
    if payload is not None:
        request_kwargs["json"] = payload

    response = await getattr(client, method)(path, **request_kwargs)

    assert response.status_code == 403
    assert response.json() == {"detail": "Creator role is required"}
