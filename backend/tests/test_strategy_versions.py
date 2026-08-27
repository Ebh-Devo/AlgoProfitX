import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.strategy import Strategy, StrategyVersion
from app.models.instrument import Exchange, Instrument, InstrumentVendorMapping
from app.bootstrap.instruments import NIFTY_50_INDEX_ID, NSE_EXCHANGE_ID, SYNTHETIC_EQUITY_ID
from app.db.migration_support import SYNTHETIC_STRATEGY_VERSION_BACKFILL_SQL


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client


def unique_email() -> str:
    return f"strategy-version-{uuid.uuid4().hex}@example.com"


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
) -> dict[str, object]:
    response = await client.post(
        "/api/v1/strategies",
        headers=headers,
        json={"name": "Versioned Strategy", "slug": slug},
    )
    assert response.status_code == 201
    return response.json()


def version_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "instrument_id": str(SYNTHETIC_EQUITY_ID),
        "configuration": {"instrument": "TRADEEBH_TEST_EQ", "timeframe": "15m"},
        "backtest_configuration": {"initial_capital": 100000},
    }
    payload.update(overrides)
    return payload


async def create_version(
    client: AsyncClient,
    headers: dict[str, str],
    strategy_id: str,
    **overrides: object,
) -> dict[str, object]:
    response = await client.post(
        f"/api/v1/strategies/{strategy_id}/versions",
        headers=headers,
        json=version_payload(**overrides),
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_create_first_version_is_server_numbered_and_persisted(client):
    headers = await register_and_login(client)
    strategy = await create_strategy(client, headers, "version-first")

    response = await client.post(
        f"/api/v1/strategies/{strategy['id']}/versions",
        headers=headers,
        json=version_payload(version_number=99),
    )

    assert response.status_code == 201
    data = response.json()
    assert set(data) == {
        "id",
        "strategy_id",
        "instrument_id",
        "instrument",
        "version_number",
        "configuration",
        "backtest_configuration",
        "created_at",
    }
    assert data["strategy_id"] == strategy["id"]
    assert data["instrument_id"] == str(SYNTHETIC_EQUITY_ID)
    assert data["instrument"]["canonical_symbol"] == "ALGOPROFITX_TEST_EQ"
    assert data["version_number"] == 1
    assert data["configuration"] == {"instrument": "TRADEEBH_TEST_EQ", "timeframe": "15m"}
    assert data["backtest_configuration"] == {"initial_capital": 100000}

    async with AsyncSessionLocal() as session:
        persisted = await session.scalar(
            select(StrategyVersion).where(
                StrategyVersion.id == uuid.UUID(data["id"])
            )
        )
        parent = await session.scalar(
            select(Strategy).where(Strategy.id == uuid.UUID(strategy["id"]))
        )

    assert persisted is not None
    assert persisted.version_number == 1
    assert persisted.configuration == data["configuration"]
    assert persisted.backtest_configuration == data["backtest_configuration"]
    assert parent is not None
    assert parent.current_version_id is None


@pytest.mark.asyncio
async def test_subsequent_versions_increment_and_list_in_version_order(client):
    headers = await register_and_login(client)
    strategy = await create_strategy(client, headers, "version-order")
    first = await create_version(client, headers, strategy["id"])
    second = await create_version(
        client,
        headers,
        strategy["id"],
        configuration={"timeframe": "5m"},
    )

    response = await client.get(
        f"/api/v1/strategies/{strategy['id']}/versions", headers=headers
    )

    assert response.status_code == 200
    assert [version["id"] for version in response.json()] == [
        first["id"],
        second["id"],
    ]
    assert [version["version_number"] for version in response.json()] == [1, 2]


@pytest.mark.asyncio
async def test_owner_can_get_specific_version(client):
    headers = await register_and_login(client)
    strategy = await create_strategy(client, headers, "version-get")
    created = await create_version(client, headers, strategy["id"])

    response = await client.get(
        f"/api/v1/strategies/{strategy['id']}/versions/{created['id']}",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == created


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        (
            "post",
            "/api/v1/strategies/00000000-0000-0000-0000-000000000001/versions",
            version_payload(),
        ),
        (
            "get",
            "/api/v1/strategies/00000000-0000-0000-0000-000000000001/versions",
            None,
        ),
        (
            "get",
            "/api/v1/strategies/00000000-0000-0000-0000-000000000001/versions/00000000-0000-0000-0000-000000000002",
            None,
        ),
    ],
)
async def test_version_endpoints_require_authentication(client, method, path, payload):
    response = await client.request(method, path, json=payload)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_non_owner_cannot_create_list_or_get_versions(client):
    owner_headers = await register_and_login(client)
    other_headers = await register_and_login(client)
    strategy = await create_strategy(client, owner_headers, "version-owner-only")
    version = await create_version(client, owner_headers, strategy["id"])
    versions_path = f"/api/v1/strategies/{strategy['id']}/versions"

    create_response = await client.post(
        versions_path, headers=other_headers, json=version_payload()
    )
    list_response = await client.get(versions_path, headers=other_headers)
    get_response = await client.get(
        f"{versions_path}/{version['id']}", headers=other_headers
    )

    for response in (create_response, list_response, get_response):
        assert response.status_code == 404
        assert response.json() == {"detail": "Strategy not found"}


@pytest.mark.asyncio
async def test_nonexistent_strategy_returns_not_found_for_version_endpoints(client):
    headers = await register_and_login(client)
    path = "/api/v1/strategies/00000000-0000-0000-0000-000000000001/versions"

    create_response = await client.post(
        path, headers=headers, json=version_payload()
    )
    list_response = await client.get(path, headers=headers)
    get_response = await client.get(
        f"{path}/00000000-0000-0000-0000-000000000002", headers=headers
    )

    for response in (create_response, list_response, get_response):
        assert response.status_code == 404
        assert response.json() == {"detail": "Strategy not found"}


@pytest.mark.asyncio
async def test_nonexistent_version_returns_not_found(client):
    headers = await register_and_login(client)
    strategy = await create_strategy(client, headers, "version-missing")

    response = await client.get(
        f"/api/v1/strategies/{strategy['id']}/versions/00000000-0000-0000-0000-000000000001",
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Strategy version not found"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"configuration": []},
        {"backtest_configuration": []},
        {"configuration": "not-an-object"},
    ],
)
async def test_create_version_rejects_invalid_payload(client, payload):
    headers = await register_and_login(client)
    strategy = await create_strategy(client, headers, "version-invalid-payload")

    response = await client.post(
        f"/api/v1/strategies/{strategy['id']}/versions",
        headers=headers,
        json=payload,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_database_enforces_unique_version_number_per_strategy(client):
    headers = await register_and_login(client)
    strategy = await create_strategy(client, headers, "version-unique")
    created = await create_version(client, headers, strategy["id"])

    async with AsyncSessionLocal() as session:
        session.add(
            StrategyVersion(
                strategy_id=uuid.UUID(strategy["id"]),
                version_number=created["version_number"],
                configuration={},
                backtest_configuration={},
            )
        )
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()


@pytest.mark.asyncio
async def test_create_version_rejects_unknown_inactive_instrument_and_exchange(client):
    headers = await register_and_login(client)
    strategy = await create_strategy(client, headers, "version-instrument-state")
    path = f"/api/v1/strategies/{strategy['id']}/versions"

    unknown = await client.post(path, headers=headers, json=version_payload(instrument_id=str(uuid.uuid4())))
    assert unknown.status_code == 422
    assert unknown.json() == {"detail": "Instrument not found"}

    async with AsyncSessionLocal() as session:
        selected = await session.get(Instrument, SYNTHETIC_EQUITY_ID)
        assert selected is not None
        selected.is_active = False
        await session.commit()
    inactive = await client.post(path, headers=headers, json=version_payload())
    assert inactive.status_code == 422
    assert inactive.json() == {"detail": "Instrument is inactive"}

    async with AsyncSessionLocal() as session:
        selected = await session.get(Instrument, SYNTHETIC_EQUITY_ID)
        exchange = await session.get(Exchange, NSE_EXCHANGE_ID)
        assert selected is not None and exchange is not None
        selected.is_active = True
        exchange.is_active = False
        await session.commit()
    inactive_exchange = await client.post(path, headers=headers, json=version_payload())
    assert inactive_exchange.status_code == 422
    assert inactive_exchange.json() == {"detail": "Instrument Exchange is inactive"}


@pytest.mark.asyncio
async def test_non_tradeable_index_is_allowed_and_conflicting_json_identity_is_rejected(client):
    headers = await register_and_login(client)
    strategy = await create_strategy(client, headers, "version-index")
    path = f"/api/v1/strategies/{strategy['id']}/versions"

    conflict = await client.post(
        path,
        headers=headers,
        json=version_payload(configuration={"instrument": "OTHER"}),
    )
    assert conflict.status_code == 422
    assert "conflicts" in conflict.json()["detail"]

    created = await client.post(
        path,
        headers=headers,
        json=version_payload(
            instrument_id=str(NIFTY_50_INDEX_ID),
            configuration={"instrument": "NIFTY 50", "reference_only": True},
        ),
    )
    assert created.status_code == 201
    assert created.json()["instrument_id"] == str(NIFTY_50_INDEX_ID)
    assert created.json()["instrument"]["is_tradeable"] is False
    assert created.json()["instrument"]["instrument_type"] == "index"


@pytest.mark.asyncio
async def test_legacy_null_instrument_is_readable_and_instrument_fk_is_restrictive(client):
    headers = await register_and_login(client)
    strategy = await create_strategy(client, headers, "version-legacy")
    legacy_id = uuid.uuid4()
    async with AsyncSessionLocal() as session:
        session.add(
            StrategyVersion(
                id=legacy_id,
                strategy_id=uuid.UUID(strategy["id"]),
                instrument_id=None,
                version_number=1,
                configuration={"instrument": "UNKNOWN_LEGACY"},
                backtest_configuration={},
            )
        )
        await session.commit()

    response = await client.get(
        f"/api/v1/strategies/{strategy['id']}/versions/{legacy_id}", headers=headers
    )
    assert response.status_code == 200
    assert response.json()["instrument_id"] is None
    assert response.json()["instrument"] is None

    async with AsyncSessionLocal() as session:
        instrument = await session.get(Instrument, SYNTHETIC_EQUITY_ID)
        assert instrument is not None
        bound = StrategyVersion(
            strategy_id=uuid.UUID(strategy["id"]),
            instrument_id=instrument.id,
            version_number=2,
            configuration={},
            backtest_configuration={},
        )
        session.add(bound)
        await session.commit()
        await session.delete(instrument)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_version_response_exposes_safe_instrument_metadata_not_vendor_mapping(client):
    headers = await register_and_login(client)
    strategy = await create_strategy(client, headers, "version-safe-metadata")
    async with AsyncSessionLocal() as session:
        session.add(
            InstrumentVendorMapping(
                instrument_id=SYNTHETIC_EQUITY_ID,
                provider_code="private-test",
                vendor_instrument_id="secret-token",
                is_active=True,
                provider_metadata={"secret": True},
            )
        )
        await session.commit()

    created = await create_version(client, headers, strategy["id"])
    instrument = created["instrument"]
    assert instrument["exchange"]["code"] == "NSE"
    assert instrument["quote_currency"] == "INR"
    assert instrument["tick_size"] == "0.01000000"
    assert instrument["lot_size"] == 1
    assert "vendor_mappings" not in instrument
    assert "secret-token" not in str(created)


@pytest.mark.asyncio
async def test_migration_backfill_maps_only_recognized_synthetic_legacy_identity(client):
    headers = await register_and_login(client)
    strategy = await create_strategy(client, headers, "version-backfill")
    recognized_id = uuid.uuid4()
    unknown_id = uuid.uuid4()
    async with AsyncSessionLocal() as session:
        session.add_all(
            [
                StrategyVersion(
                    id=recognized_id,
                    strategy_id=uuid.UUID(strategy["id"]),
                    version_number=1,
                    configuration={"instrument": "TRADEEBH_TEST_EQ"},
                    backtest_configuration={},
                ),
                StrategyVersion(
                    id=unknown_id,
                    strategy_id=uuid.UUID(strategy["id"]),
                    version_number=2,
                    configuration={"instrument": "UNMAPPED_LEGACY"},
                    backtest_configuration={},
                ),
            ]
        )
        await session.flush()
        await session.execute(text(SYNTHETIC_STRATEGY_VERSION_BACKFILL_SQL))
        await session.commit()

    async with AsyncSessionLocal() as session:
        recognized = await session.get(StrategyVersion, recognized_id)
        unknown = await session.get(StrategyVersion, unknown_id)
    assert recognized is not None and recognized.instrument_id == SYNTHETIC_EQUITY_ID
    assert unknown is not None and unknown.instrument_id is None
