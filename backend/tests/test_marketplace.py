import uuid

import pytest
from app.bootstrap.instruments import SYNTHETIC_EQUITY_ID
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
    return f"marketplace-{uuid.uuid4().hex}@example.com"


async def register_login_and_enroll(client: AsyncClient) -> dict[str, str]:
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
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}

    response = await client.post("/api/v1/auth/creator/enroll", headers=headers)
    assert response.status_code == 200
    return headers


async def create_strategy(
    client: AsyncClient,
    headers: dict[str, str],
    slug: str,
) -> dict[str, object]:
    response = await client.post(
        "/api/v1/strategies",
        headers=headers,
        json={"name": f"Strategy {slug}", "slug": slug},
    )
    assert response.status_code == 201
    return response.json()


async def publish_strategy(
    client: AsyncClient,
    headers: dict[str, str],
    slug: str,
    deploy: bool = False,
) -> dict[str, object]:
    strategy = await create_strategy(client, headers, slug)
    response = await client.post(
        f"/api/v1/strategies/{strategy['id']}/versions",
        headers=headers,
        json={"instrument_id": str(SYNTHETIC_EQUITY_ID), "configuration": {"private_rule": "do-not-publish"}},
    )
    assert response.status_code == 201
    version = response.json()

    response = await client.post(
        f"/api/v1/strategies/{strategy['id']}/publish",
        headers=headers,
    )
    assert response.status_code == 200

    if deploy:
        response = await client.post(
            f"/api/v1/strategies/{strategy['id']}/deploy",
            headers=headers,
        )
        assert response.status_code == 200

    return {**strategy, "version_id": version["id"], "version_number": version["version_number"]}


async def make_private(strategy_id: str) -> None:
    async with AsyncSessionLocal() as session:
        strategy = await session.scalar(
            select(Strategy).where(Strategy.id == uuid.UUID(strategy_id))
        )
        assert strategy is not None
        strategy.is_public = False
        await session.commit()


@pytest.mark.asyncio
async def test_anonymous_list_includes_published_and_deployed_public_strategies(
    client,
):
    headers = await register_login_and_enroll(client)
    published = await publish_strategy(client, headers, "market-published")
    deployed = await publish_strategy(client, headers, "market-deployed", deploy=True)
    await create_strategy(client, headers, "market-draft")

    response = await client.get("/api/v1/marketplace/strategies")

    assert response.status_code == 200
    discovered = response.json()
    assert {strategy["id"] for strategy in discovered} == {
        published["id"],
        deployed["id"],
    }
    assert {strategy["status"] for strategy in discovered} == {
        "published",
        "deployed",
    }


@pytest.mark.asyncio
async def test_archived_and_non_public_strategies_are_not_discoverable(client):
    headers = await register_login_and_enroll(client)
    archived = await publish_strategy(client, headers, "market-archived")
    private = await publish_strategy(client, headers, "market-private")

    response = await client.post(
        f"/api/v1/strategies/{archived['id']}/archive",
        headers=headers,
    )
    assert response.status_code == 200
    await make_private(private["id"])

    response = await client.get("/api/v1/marketplace/strategies")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_anonymous_marketplace_detail_exposes_only_public_metadata(client):
    headers = await register_login_and_enroll(client)
    strategy = await publish_strategy(client, headers, "market-detail")

    response = await client.get("/api/v1/marketplace/strategies/market-detail")

    assert response.status_code == 200
    detail = response.json()
    assert detail == {
        "id": strategy["id"],
        "slug": "market-detail",
        "name": "Strategy market-detail",
        "description": None,
        "status": "published",
        "published_at": detail["published_at"],
        "current_version_id": strategy["version_id"],
        "current_version_number": strategy["version_number"],
    }
    assert detail["published_at"] is not None
    assert "creator_id" not in detail
    assert "is_public" not in detail
    assert "configuration" not in detail
    assert "backtest_configuration" not in detail


@pytest.mark.asyncio
@pytest.mark.parametrize("visibility", ["draft", "archived", "private"])
async def test_non_discoverable_marketplace_detail_returns_not_found(
    client,
    visibility,
):
    headers = await register_login_and_enroll(client)
    slug = f"market-hidden-{visibility}"

    if visibility == "draft":
        await create_strategy(client, headers, slug)
    else:
        strategy = await publish_strategy(client, headers, slug)
        if visibility == "archived":
            response = await client.post(
                f"/api/v1/strategies/{strategy['id']}/archive",
                headers=headers,
            )
            assert response.status_code == 200
        else:
            await make_private(strategy["id"])

    response = await client.get(f"/api/v1/marketplace/strategies/{slug}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Marketplace strategy not found"}


@pytest.mark.asyncio
async def test_marketplace_pagination_is_deterministic(client):
    headers = await register_login_and_enroll(client)
    first = await publish_strategy(client, headers, "market-page-first")
    second = await publish_strategy(client, headers, "market-page-second")
    third = await publish_strategy(client, headers, "market-page-third")

    all_response = await client.get("/api/v1/marketplace/strategies")
    first_page = await client.get("/api/v1/marketplace/strategies?limit=2&offset=0")
    second_page = await client.get("/api/v1/marketplace/strategies?limit=2&offset=2")

    assert all_response.status_code == 200
    assert first_page.status_code == 200
    assert second_page.status_code == 200
    assert [strategy["id"] for strategy in all_response.json()] == [
        third["id"],
        second["id"],
        first["id"],
    ]
    assert first_page.json() == all_response.json()[:2]
    assert second_page.json() == all_response.json()[2:]
