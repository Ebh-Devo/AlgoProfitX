import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

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
    return f"strategy-lifecycle-{uuid.uuid4().hex}@example.com"


async def register_and_login(client: AsyncClient) -> dict[str, str]:
    email = unique_email()
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "TestPassword123"},
    )
    assert response.status_code == 201

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "TestPassword123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def create_strategy(
    client: AsyncClient,
    headers: dict[str, str],
    slug: str,
) -> dict[str, object]:
    response = await client.post(
        "/api/v1/strategies",
        headers=headers,
        json={"name": "Lifecycle Strategy", "slug": slug},
    )
    assert response.status_code == 201
    return response.json()


async def create_version(
    client: AsyncClient,
    headers: dict[str, str],
    strategy_id: str,
    marker: str,
) -> dict[str, object]:
    response = await client.post(
        f"/api/v1/strategies/{strategy_id}/versions",
        headers=headers,
        json={"configuration": {"marker": marker}},
    )
    assert response.status_code == 201
    return response.json()


async def publish_strategy(
    client: AsyncClient,
    headers: dict[str, str],
    strategy_id: str,
) -> dict[str, object]:
    response = await client.post(
        f"/api/v1/strategies/{strategy_id}/publish", headers=headers
    )
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_publish_requires_at_least_one_version(client):
    headers = await register_and_login(client)
    strategy = await create_strategy(client, headers, "publish-needs-version")

    response = await client.post(
        f"/api/v1/strategies/{strategy['id']}/publish", headers=headers
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "A strategy version is required before publishing"
    }


@pytest.mark.asyncio
async def test_publish_selects_latest_version_makes_public_and_persists(client):
    headers = await register_and_login(client)
    strategy = await create_strategy(client, headers, "publish-latest-version")
    await create_version(client, headers, strategy["id"], "first")
    latest = await create_version(client, headers, strategy["id"], "second")

    published = await publish_strategy(client, headers, strategy["id"])

    assert published["status"] == "published"
    assert published["current_version_id"] == latest["id"]
    assert published["is_public"] is True
    assert published["published_at"] is not None
    assert published["deployed_at"] is None

    async with AsyncSessionLocal() as session:
        persisted = await session.scalar(
            select(Strategy).where(Strategy.id == uuid.UUID(strategy["id"]))
        )

    assert persisted is not None
    assert str(persisted.current_version_id) == latest["id"]
    assert persisted.is_public is True
    assert persisted.published_at is not None


@pytest.mark.asyncio
async def test_published_strategy_can_be_deployed_and_persists_timestamp(client):
    headers = await register_and_login(client)
    strategy = await create_strategy(client, headers, "publish-deploy")
    await create_version(client, headers, strategy["id"], "version")
    await publish_strategy(client, headers, strategy["id"])

    response = await client.post(
        f"/api/v1/strategies/{strategy['id']}/deploy", headers=headers
    )

    assert response.status_code == 200
    deployed = response.json()
    assert deployed["status"] == "deployed"
    assert deployed["deployed_at"] is not None
    assert deployed["is_public"] is True

    async with AsyncSessionLocal() as session:
        persisted = await session.scalar(
            select(Strategy).where(Strategy.id == uuid.UUID(strategy["id"]))
        )

    assert persisted is not None
    assert persisted.status.value == "deployed"
    assert persisted.deployed_at is not None


@pytest.mark.asyncio
async def test_ordinary_update_cannot_make_published_strategy_private(client):
    headers = await register_and_login(client)
    strategy = await create_strategy(client, headers, "published-stays-public")
    await create_version(client, headers, strategy["id"], "version")
    await publish_strategy(client, headers, strategy["id"])

    response = await client.patch(
        f"/api/v1/strategies/{strategy['id']}",
        headers=headers,
        json={"name": "Updated Published Strategy", "is_public": False},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated Published Strategy"
    assert response.json()["status"] == "published"
    assert response.json()["is_public"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("initial_state", ["draft", "published", "deployed"])
async def test_allowed_states_can_be_archived_and_become_private(
    client, initial_state
):
    headers = await register_and_login(client)
    strategy = await create_strategy(client, headers, f"archive-{initial_state}")

    if initial_state != "draft":
        await create_version(client, headers, strategy["id"], "version")
        await publish_strategy(client, headers, strategy["id"])
    if initial_state == "deployed":
        deploy_response = await client.post(
            f"/api/v1/strategies/{strategy['id']}/deploy", headers=headers
        )
        assert deploy_response.status_code == 200

    response = await client.post(
        f"/api/v1/strategies/{strategy['id']}/archive", headers=headers
    )

    assert response.status_code == 200
    assert response.json()["status"] == "archived"
    assert response.json()["is_public"] is False

    async with AsyncSessionLocal() as session:
        persisted = await session.scalar(
            select(Strategy).where(Strategy.id == uuid.UUID(strategy["id"]))
        )

    assert persisted is not None
    assert persisted.status.value == "archived"
    assert persisted.is_public is False


@pytest.mark.asyncio
async def test_invalid_and_terminal_lifecycle_transitions_return_conflict(client):
    headers = await register_and_login(client)
    strategy = await create_strategy(client, headers, "invalid-transitions")
    base_path = f"/api/v1/strategies/{strategy['id']}"

    deploy_response = await client.post(f"{base_path}/deploy", headers=headers)
    assert deploy_response.status_code == 409

    archive_response = await client.post(f"{base_path}/archive", headers=headers)
    assert archive_response.status_code == 200

    for action in ("publish", "deploy", "archive"):
        response = await client.post(f"{base_path}/{action}", headers=headers)
        assert response.status_code == 409
        assert "Invalid strategy lifecycle transition" in response.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["publish", "deploy", "archive"])
async def test_lifecycle_endpoints_require_authentication(client, action):
    response = await client.post(
        f"/api/v1/strategies/00000000-0000-0000-0000-000000000001/{action}"
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_non_owner_and_nonexistent_strategies_are_hidden(client):
    owner_headers = await register_and_login(client)
    other_headers = await register_and_login(client)
    strategy = await create_strategy(client, owner_headers, "lifecycle-owner-only")

    for action in ("publish", "deploy", "archive"):
        response = await client.post(
            f"/api/v1/strategies/{strategy['id']}/{action}", headers=other_headers
        )
        assert response.status_code == 404
        assert response.json() == {"detail": "Strategy not found"}

        response = await client.post(
            f"/api/v1/strategies/00000000-0000-0000-0000-000000000001/{action}",
            headers=owner_headers,
        )
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_ordinary_update_cannot_bypass_lifecycle_status(client):
    headers = await register_and_login(client)
    strategy = await create_strategy(client, headers, "update-cannot-publish")

    response = await client.patch(
        f"/api/v1/strategies/{strategy['id']}",
        headers=headers,
        json={"status": "published", "name": "Still Draft"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Still Draft"
    assert response.json()["status"] == "draft"
    assert response.json()["current_version_id"] is None


@pytest.mark.asyncio
async def test_database_rejects_current_version_from_another_strategy(client):
    headers = await register_and_login(client)
    first = await create_strategy(client, headers, "current-version-first")
    second = await create_strategy(client, headers, "current-version-second")
    other_version = await create_version(client, headers, second["id"], "other")

    async with AsyncSessionLocal() as session:
        first_strategy = await session.scalar(
            select(Strategy).where(Strategy.id == uuid.UUID(first["id"]))
        )
        assert first_strategy is not None
        first_strategy.current_version_id = uuid.UUID(other_version["id"])

        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()
