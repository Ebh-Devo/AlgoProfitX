import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.strategy import Strategy


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client


def unique_email() -> str:
    return f"strategy-{uuid.uuid4().hex}@example.com"


def strategy_payload(slug: str, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "Momentum Strategy",
        "slug": slug,
        "description": "A deterministic test strategy.",
    }
    payload.update(overrides)
    return payload


async def register_and_login(client: AsyncClient) -> dict[str, str]:
    email = unique_email()
    registration = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "TestPassword123"},
    )
    assert registration.status_code == 201

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "TestPassword123"},
    )
    assert login.status_code == 200

    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    enrollment = await client.post("/api/v1/auth/creator/enroll", headers=headers)
    assert enrollment.status_code == 200
    return headers


async def create_strategy(
    client: AsyncClient,
    headers: dict[str, str],
    slug: str,
    **overrides: object,
) -> dict[str, object]:
    response = await client.post(
        "/api/v1/strategies",
        headers=headers,
        json=strategy_payload(slug, **overrides),
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_create_strategy_cannot_force_public_visibility(client):
    headers = await register_and_login(client)

    response = await client.post(
        "/api/v1/strategies",
        headers=headers,
        json=strategy_payload("momentum-create", is_public=True),
    )

    assert response.status_code == 201
    data = response.json()
    assert set(data) == {
        "id",
        "creator_id",
        "name",
        "slug",
        "description",
        "status",
        "is_public",
        "current_version_id",
        "created_at",
        "updated_at",
        "published_at",
        "deployed_at",
    }
    assert data["name"] == "Momentum Strategy"
    assert data["slug"] == "momentum-create"
    assert data["status"] == "draft"
    assert data["is_public"] is False
    assert data["current_version_id"] is None
    assert data["published_at"] is None
    assert data["deployed_at"] is None

    async with AsyncSessionLocal() as session:
        persisted = await session.scalar(
            select(Strategy).where(Strategy.id == uuid.UUID(data["id"]))
        )

    assert persisted is not None
    assert str(persisted.creator_id) == data["creator_id"]
    assert persisted.slug == "momentum-create"
    assert persisted.is_public is False


@pytest.mark.asyncio
async def test_owner_can_retrieve_strategy(client):
    headers = await register_and_login(client)
    created = await create_strategy(client, headers, "owner-get")

    response = await client.get(
        f"/api/v1/strategies/{created['id']}", headers=headers
    )

    assert response.status_code == 200
    assert response.json() == created


@pytest.mark.asyncio
async def test_list_returns_only_authenticated_users_strategies(client):
    owner_headers = await register_and_login(client)
    other_headers = await register_and_login(client)
    first = await create_strategy(client, owner_headers, "owner-first")
    second = await create_strategy(client, owner_headers, "owner-second")
    other = await create_strategy(client, other_headers, "other-only")

    response = await client.get("/api/v1/strategies", headers=owner_headers)

    assert response.status_code == 200
    strategies = response.json()
    assert {strategy["id"] for strategy in strategies} == {
        first["id"],
        second["id"],
    }
    assert other["id"] not in {strategy["id"] for strategy in strategies}


@pytest.mark.asyncio
async def test_owner_update_cannot_force_public_visibility(client):
    headers = await register_and_login(client)
    created = await create_strategy(client, headers, "before-update")

    response = await client.patch(
        f"/api/v1/strategies/{created['id']}",
        headers=headers,
        json={
            "name": "Updated Momentum Strategy",
            "slug": "after-update",
            "description": "Updated configuration notes.",
            "is_public": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == created["id"]
    assert data["name"] == "Updated Momentum Strategy"
    assert data["slug"] == "after-update"
    assert data["description"] == "Updated configuration notes."
    assert data["is_public"] is False
    assert data["status"] == "draft"

    async with AsyncSessionLocal() as session:
        persisted = await session.scalar(
            select(Strategy).where(Strategy.id == uuid.UUID(created["id"]))
        )

    assert persisted is not None
    assert persisted.name == "Updated Momentum Strategy"
    assert persisted.slug == "after-update"
    assert persisted.description == "Updated configuration notes."
    assert persisted.is_public is False


@pytest.mark.asyncio
async def test_owner_can_delete_strategy_and_record_is_removed(client):
    headers = await register_and_login(client)
    created = await create_strategy(client, headers, "delete-owned")

    response = await client.delete(
        f"/api/v1/strategies/{created['id']}", headers=headers
    )

    assert response.status_code == 204
    assert response.content == b""

    async with AsyncSessionLocal() as session:
        persisted = await session.scalar(
            select(Strategy).where(Strategy.id == uuid.UUID(created["id"]))
        )

    assert persisted is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("post", "/api/v1/strategies", strategy_payload("unauth-create")),
        ("get", "/api/v1/strategies", None),
        ("get", "/api/v1/strategies/00000000-0000-0000-0000-000000000001", None),
        ("patch", "/api/v1/strategies/00000000-0000-0000-0000-000000000001", {"name": "Updated"}),
        ("delete", "/api/v1/strategies/00000000-0000-0000-0000-000000000001", None),
    ],
)
async def test_all_strategy_endpoints_require_authentication(
    client, method, path, payload
):
    response = await client.request(method, path, json=payload)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_non_owner_cannot_retrieve_update_or_delete_strategy(client):
    owner_headers = await register_and_login(client)
    other_headers = await register_and_login(client)
    created = await create_strategy(client, owner_headers, "owner-private")
    path = f"/api/v1/strategies/{created['id']}"

    get_response = await client.get(path, headers=other_headers)
    update_response = await client.patch(
        path, headers=other_headers, json={"name": "Unauthorized update"}
    )
    delete_response = await client.delete(path, headers=other_headers)

    for response in (get_response, update_response, delete_response):
        assert response.status_code == 404
        assert response.json() == {"detail": "Strategy not found"}

    owner_response = await client.get(path, headers=owner_headers)
    assert owner_response.status_code == 200
    assert owner_response.json()["name"] == "Momentum Strategy"


@pytest.mark.asyncio
async def test_duplicate_slug_returns_conflict(client):
    headers = await register_and_login(client)
    await create_strategy(client, headers, "shared-slug")

    response = await client.post(
        "/api/v1/strategies",
        headers=headers,
        json=strategy_payload("shared-slug"),
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Strategy slug is already in use"}


@pytest.mark.asyncio
async def test_nonexistent_strategy_returns_not_found(client):
    headers = await register_and_login(client)
    path = "/api/v1/strategies/00000000-0000-0000-0000-000000000001"

    get_response = await client.get(path, headers=headers)
    update_response = await client.patch(
        path, headers=headers, json={"name": "No Strategy"}
    )
    delete_response = await client.delete(path, headers=headers)

    for response in (get_response, update_response, delete_response):
        assert response.status_code == 404
        assert response.json() == {"detail": "Strategy not found"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"name": "ab", "slug": "short-name"},
        {"name": "Valid Name", "slug": "Not-A-Valid-Slug"},
        {"slug": "missing-name"},
    ],
)
async def test_create_rejects_invalid_schema_payloads(client, payload):
    headers = await register_and_login(client)

    response = await client.post(
        "/api/v1/strategies", headers=headers, json=payload
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_rejects_invalid_schema_payload(client):
    headers = await register_and_login(client)
    created = await create_strategy(client, headers, "invalid-update")

    response = await client.patch(
        f"/api/v1/strategies/{created['id']}",
        headers=headers,
        json={"slug": "invalid_slug"},
    )

    assert response.status_code == 422
