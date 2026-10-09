"""Phase 7B-1: the backend V2 API contract (validate, create, vocabulary, lifecycle guard)."""

import copy
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.bootstrap.instruments import SYNTHETIC_EQUITY_ID
from app.core.abuse import abuse_controller
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.backtest import Backtest
from app.models.strategy import Strategy, StrategyStatus, StrategyVersion
from app.services import backtest as backtest_service
from app.strategy_definition.assessment import assess_v2_definition
from app.strategy_definition.indicators import DEFAULT_CATALOG
from app.strategy_definition.runtime.capabilities import RUNTIME_CAPABILITIES
from app.strategy_definition.runtime.engine import StrategyRuntimeEngine
from app.strategy_definition.schema import CrossCondition, SharesSizing
from tests.strategy_v2_builders import D, ind, leg, long_definition, op, position, rule
from tests.test_backtest_execution import (
    create_backtest,
    create_strategy_version,
    execute_path,
    register_and_login,
)

V2_ENV = {
    "initial_capital": "10000",
    "fill_model": "same_bar_close",
    "timeframe": "1d",
    "start_date": "2025-01-01T00:00:00Z",
}
VALIDATE = "/api/v1/strategies/definitions/validate"
VOCABULARY = "/api/v1/strategies/definition-vocabulary"
UNSUPPORTED_CODE = "strategy_definition_version_unsupported_for_execution"


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client


def document(name="ema", fast=3, slow=5, **changes) -> dict:
    # Indicators run on the definition's own timeframe; a coarser indicator would be a semantic error.
    timeframe = changes.get("timeframe", "1d")
    return long_definition(
        positions=(position(legs=[leg()], sizing=SharesSizing(D(5))),),
        rules=(
            rule(
                "enter",
                CrossCondition("above", ind(name, fast, timeframe), ind(name, slow, timeframe)),
                [op("open")],
            ),
            rule(
                "exit",
                CrossCondition("below", ind(name, fast, timeframe), ind(name, slow, timeframe)),
                [op("close")],
            ),
        ),
        **changes,
    ).to_dict()


def body(configuration=None, env=None, version=2, **extra) -> dict:
    return {
        "definition_schema_version": version,
        "configuration": document() if configuration is None else configuration,
        "backtest_configuration": dict(V2_ENV if env is None else env),
        **extra,
    }


def create_body(instrument=SYNTHETIC_EQUITY_ID, **kwargs) -> dict:
    return {**body(**kwargs), "instrument_id": str(instrument)}


async def new_strategy(client, headers, slug) -> dict:
    response = await client.post(
        "/api/v1/strategies", headers=headers, json={"name": f"Contract {slug}", "slug": slug}
    )
    assert response.status_code == 201
    return response.json()


async def counts() -> tuple[int, int, int]:
    async with AsyncSessionLocal() as session:
        return tuple(
            [
                await session.scalar(select(func.count()).select_from(model))
                for model in (Strategy, StrategyVersion, Backtest)
            ]
        )


def codes(result: dict) -> set[str]:
    return {issue["code"] for issue in result["issues"]}


def with_rule_limits(configuration: dict) -> dict:
    changed = copy.deepcopy(configuration)
    changed["rules"][0]["limits"] = {"max_fires_per_position": 1}
    return changed


# --- draft validation ---------------------------------------------------------------------


async def test_a_runnable_ema_definition_is_valid_savable_and_runnable(client):
    headers = await register_and_login(client)
    response = await client.post(VALIDATE, headers=headers, json=body())
    assert response.status_code == 200
    result = response.json()
    assert result["definition_schema_version"] == 2
    assert (result["valid"], result["savable"], result["runnable"]) == (True, True, True)
    assert result["issues"] == []
    assert "indicator.ema@1" in result["required_capabilities"]
    assert result["unsupported_capabilities"] == []


async def test_validation_persists_nothing(client):
    headers = await register_and_login(client)
    await new_strategy(client, headers, "validate-no-write")
    before = await counts()
    for payload in (body(), body(document("sma")), body({"schema_version": 2})):
        assert (await client.post(VALIDATE, headers=headers, json=payload)).status_code == 200
    assert await counts() == before


async def test_a_catalog_indicator_the_runtime_lacks_is_savable_but_not_runnable(client):
    headers = await register_and_login(client)
    for name in ("sma", "rsi"):
        result = (await client.post(VALIDATE, headers=headers, json=body(document(name)))).json()
        assert result["savable"] is True
        assert result["runnable"] is False and result["valid"] is False
        assert result["unsupported_capabilities"] == [f"indicator.{name}@1"]
        issue = next(i for i in result["issues"] if i["code"] == "capability_missing")
        assert issue["layer"] == "capability" and issue["severity"] == "error"


async def test_unsupported_rule_limits_are_not_runnable(client):
    headers = await register_and_login(client)
    result = (
        await client.post(VALIDATE, headers=headers, json=body(with_rule_limits(document())))
    ).json()
    assert result["savable"] is True and result["runnable"] is False
    assert "rule.limits" in result["unsupported_capabilities"]


@pytest.mark.parametrize("fill_model", ["next_bar_open", "banana"])
async def test_unsupported_fill_models_are_not_runnable(client, fill_model):
    headers = await register_and_login(client)
    env = {**V2_ENV, "fill_model": fill_model}
    result = (await client.post(VALIDATE, headers=headers, json=body(env=env))).json()
    assert result["savable"] is True and result["runnable"] is False
    issue = next(i for i in result["issues"] if i["code"] == "fill_model_unsupported")
    assert issue["layer"] == "environment"
    assert issue["path"] == "backtest_configuration.fill_model"


async def test_a_missing_fill_model_is_not_runnable(client):
    headers = await register_and_login(client)
    env = {k: v for k, v in V2_ENV.items() if k != "fill_model"}
    result = (await client.post(VALIDATE, headers=headers, json=body(env=env))).json()
    assert result["runnable"] is False and "fill_model_required" in codes(result)


@pytest.mark.parametrize("timeframe", ["1w", "5d", "1h", "15m"])
async def test_unsupported_timeframes_are_not_runnable(client, timeframe):
    headers = await register_and_login(client)
    result = (
        await client.post(
            VALIDATE,
            headers=headers,
            json=body(document(timeframe=timeframe), env={**V2_ENV, "timeframe": timeframe}),
        )
    ).json()
    assert result["runnable"] is False
    assert "timeframe_unsupported" in codes(result)


async def test_the_backtest_timeframe_is_required_and_must_match(client):
    headers = await register_and_login(client)
    missing = {k: v for k, v in V2_ENV.items() if k != "timeframe"}
    result = (await client.post(VALIDATE, headers=headers, json=body(env=missing))).json()
    assert result["runnable"] is False and "timeframe_required" in codes(result)
    mismatch = (
        await client.post(VALIDATE, headers=headers, json=body(env={**V2_ENV, "timeframe": "1w"}))
    ).json()
    assert mismatch["runnable"] is False and "timeframe_mismatch" in codes(mismatch)


async def test_structured_issues_carry_path_code_message_severity_and_layer(client):
    headers = await register_and_login(client)
    broken = document()
    broken["rules"][0]["when"]["left"]["params"]["period"] = 0
    result = (await client.post(VALIDATE, headers=headers, json=body(broken))).json()
    assert result["valid"] is False and result["savable"] is False and result["runnable"] is False
    assert result["issues"]
    for issue in result["issues"]:
        assert set(issue) == {"path", "code", "message", "severity", "layer"}
        assert issue["code"] and issue["message"]
        assert issue["layer"] in {"schema", "semantic", "position", "capability", "environment"}
    assert any(i["path"].startswith("rules[0].when.left") for i in result["issues"])

    malformed = (
        await client.post(VALIDATE, headers=headers, json=body({"schema_version": 2}))
    ).json()
    assert malformed["savable"] is False
    assert {i["layer"] for i in malformed["issues"]} == {"schema"}


async def test_warnings_are_preserved_without_failing_the_definition(client):
    headers = await register_and_login(client)
    # one rule that both opens and closes the position on the same bar: a conflicting-operations warning
    configuration = document()
    configuration["rules"][0]["then"].append({"op": "close", "position": "main"})
    result = (await client.post(VALIDATE, headers=headers, json=body(configuration))).json()
    warnings = [i for i in result["issues"] if i["severity"] == "warning"]
    assert [w["code"] for w in warnings] == ["conflicting_operations"], result
    assert warnings[0]["layer"] == "position" and warnings[0]["path"] == "rules[0].then"
    assert result["runnable"] is True and result["valid"] is True


async def test_malformed_request_bodies_are_4xx(client):
    headers = await register_and_login(client)
    for payload in (
        {},
        {"configuration": {}, "backtest_configuration": {}},  # no version
        body(version=1),
        body(version="2"),
        body(version=True),
        body(version=3),
        {**body(), "unexpected": 1},
        {**body(), "configuration": []},
    ):
        response = await client.post(VALIDATE, headers=headers, json=payload)
        assert response.status_code == 422, payload


async def test_validation_requires_authentication_and_the_creator_role(client):
    assert (await client.post(VALIDATE, json=body())).status_code == 401
    investor = await register_and_login(client, enroll=False)
    assert (await client.post(VALIDATE, headers=investor, json=body())).status_code == 403


async def test_validation_is_rate_limited_per_user(client, monkeypatch):
    monkeypatch.setenv("DEFINITION_VALIDATION_BURST_LIMIT", "1")
    get_settings.cache_clear()
    try:
        headers = await register_and_login(client)
        assert (await client.post(VALIDATE, headers=headers, json=body())).status_code == 200
        limited = await client.post(VALIDATE, headers=headers, json=body())
        assert limited.status_code == 429
        assert limited.json()["detail"]["error_code"] == "rate_limit_exceeded"
    finally:
        get_settings.cache_clear()


# --- V2 creation --------------------------------------------------------------------------


def versions_path(strategy: dict) -> str:
    return f"/api/v1/strategies/{strategy['id']}/versions/v2"


async def test_a_runnable_v2_definition_is_persisted_as_version_2_and_preserved(client):
    headers = await register_and_login(client)
    strategy = await new_strategy(client, headers, "v2-create")
    payload = create_body()
    response = await client.post(versions_path(strategy), headers=headers, json=payload)
    assert response.status_code == 201, response.text
    version = response.json()
    assert version["definition_schema_version"] == 2
    assert version["configuration"] == payload["configuration"]
    assert version["backtest_configuration"] == payload["backtest_configuration"]
    assert version["version_number"] == 1
    async with AsyncSessionLocal() as session:
        row = await session.get(StrategyVersion, uuid.UUID(version["id"]))
        assert row.definition_schema_version == 2
        assert row.configuration == payload["configuration"]
    read = await client.get(f"/api/v1/strategies/{strategy['id']}/versions", headers=headers)
    assert [v["definition_schema_version"] for v in read.json()] == [2]
    second = await client.post(versions_path(strategy), headers=headers, json=payload)
    assert second.json()["version_number"] == 2


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.pop("definition_schema_version"),
        lambda p: p.update(definition_schema_version=1),
        lambda p: p.update(definition_schema_version="2"),
        lambda p: p.update(definition_schema_version=3),
        lambda p: p.update(definition_schema_version=None),
        lambda p: p.update(unexpected="field"),
        lambda p: p.pop("backtest_configuration"),
        lambda p: p.pop("configuration"),
    ],
)
async def test_missing_wrong_or_extra_fields_are_rejected_and_never_create_a_version(
    client, mutate
):
    headers = await register_and_login(client)
    strategy = await new_strategy(client, headers, f"v2-bad-{uuid.uuid4().hex[:8]}")
    payload = create_body()
    mutate(payload)
    response = await client.post(versions_path(strategy), headers=headers, json=payload)
    assert response.status_code == 422
    assert (await counts())[1] == 0


async def test_unrunnable_definitions_cannot_be_saved_through_the_route(client):
    headers = await register_and_login(client)
    strategy = await new_strategy(client, headers, "v2-unrunnable")
    cases = {
        "sma": create_body(configuration=document("sma")),
        "limits": create_body(configuration=with_rule_limits(document())),
        "fill": create_body(env={**V2_ENV, "fill_model": "next_bar_open"}),
        "weekly": create_body(
            configuration=document(timeframe="1w"), env={**V2_ENV, "timeframe": "1w"}
        ),
    }
    for name, payload in cases.items():
        response = await client.post(versions_path(strategy), headers=headers, json=payload)
        assert response.status_code == 422, name
        detail = response.json()["detail"]
        assert detail["code"] == "strategy_definition_not_runnable", name
        assert detail["issues"] and all(i["severity"] == "error" for i in detail["issues"])
    assert (await counts())[1] == 0


async def test_an_invalid_definition_returns_structured_stable_errors(client):
    headers = await register_and_login(client)
    strategy = await new_strategy(client, headers, "v2-invalid")
    response = await client.post(
        versions_path(strategy),
        headers=headers,
        json=create_body(configuration={"schema_version": 2}),
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_strategy_definition"
    assert detail["message"]
    assert detail["issues"] and {i["layer"] for i in detail["issues"]} == {"schema"}
    assert (await counts())[1] == 0


async def test_v2_creation_ownership_auth_and_instrument_errors(client):
    owner = await register_and_login(client)
    other = await register_and_login(client)
    strategy = await new_strategy(client, owner, "v2-owner")
    assert (await client.post(versions_path(strategy), json=create_body())).status_code == 401
    # another creator's strategy is hidden exactly like the V1 route
    assert (
        await client.post(versions_path(strategy), headers=other, json=create_body())
    ).status_code == 404
    investor = await register_and_login(client, enroll=False)
    assert (
        await client.post(versions_path(strategy), headers=investor, json=create_body())
    ).status_code == 403
    missing = {"id": str(uuid.uuid4())}
    assert (
        await client.post(versions_path(missing), headers=owner, json=create_body())
    ).status_code == 404
    bad_instrument = await client.post(
        versions_path(strategy), headers=owner, json=create_body(instrument=uuid.uuid4())
    )
    assert bad_instrument.status_code == 422
    assert bad_instrument.json()["detail"] == "Instrument not found"
    assert (await counts())[1] == 0


async def test_a_version_number_race_is_still_a_409(client, monkeypatch):
    from app.api.routes import strategies as routes

    async def conflict(*args, **kwargs):
        raise ValueError("Strategy version number is already in use")

    monkeypatch.setattr(routes, "create_strategy_version_v2", conflict)
    headers = await register_and_login(client)
    strategy = await new_strategy(client, headers, "v2-race")
    response = await client.post(versions_path(strategy), headers=headers, json=create_body())
    assert response.status_code == 409
    assert response.json()["detail"] == "Strategy version number is already in use"


# --- V1 route hardening and regressions ---------------------------------------------------------

V1_BODY = {
    "instrument_id": str(SYNTHETIC_EQUITY_ID),
    "configuration": {"entry": {"type": "ema_crossover", "fast_period": 3, "slow_period": 5}},
    "backtest_configuration": {"initial_capital": "1000"},
}


async def test_the_v1_route_still_works_without_the_field_and_reports_version_1(client):
    headers = await register_and_login(client)
    strategy, version = await create_strategy_version(client, headers, "v1-compat")
    assert version["definition_schema_version"] == 1
    explicit = await client.post(
        f"/api/v1/strategies/{strategy['id']}/versions",
        headers=headers,
        json={**V1_BODY, "definition_schema_version": 1},
    )
    assert explicit.status_code == 201 and explicit.json()["definition_schema_version"] == 1


@pytest.mark.parametrize("claimed", [2, "2", 3, 2.5, "1"])
async def test_the_v1_route_rejects_a_claimed_v2_schema_version(client, claimed):
    headers = await register_and_login(client)
    strategy = await new_strategy(client, headers, f"v1-claim-{uuid.uuid4().hex[:8]}")
    response = await client.post(
        f"/api/v1/strategies/{strategy['id']}/versions",
        headers=headers,
        json={**V1_BODY, "definition_schema_version": claimed},
    )
    assert response.status_code == 422
    assert (await counts())[1] == 0


# --- backtests ----------------------------------------------------------------------------------


async def v2_version(client, headers, slug, **kwargs) -> tuple[dict, dict]:
    strategy = await new_strategy(client, headers, slug)
    response = await client.post(
        versions_path(strategy), headers=headers, json=create_body(**kwargs)
    )
    assert response.status_code == 201, response.text
    return strategy, response.json()


async def rewrite(version: dict, **columns) -> None:
    """Simulate an already-stored row, e.g. one saved before a gate existed."""
    async with AsyncSessionLocal() as session:
        row = await session.get(StrategyVersion, uuid.UUID(version["id"]))
        for name, value in columns.items():
            setattr(row, name, value)
        await session.commit()


async def run(client, headers, strategy, version) -> dict:
    await abuse_controller.clear()  # these tests run several backtests; rate limits are tested elsewhere
    backtest = await create_backtest(client, headers, strategy, version)
    response = await client.post(execute_path(strategy, version, backtest), headers=headers)
    assert response.status_code == 200
    return response.json()


@pytest.fixture
def no_data_or_runtime(monkeypatch):
    touched: list[str] = []

    async def acquire(*args, **kwargs):
        touched.append("market_data")
        raise AssertionError("market data was requested before the environment was validated")

    def run_canonical(self, *args, **kwargs):
        touched.append("runtime")
        raise AssertionError("the runtime ran before the environment was validated")

    monkeypatch.setattr(backtest_service, "_acquire_dataset", acquire)
    monkeypatch.setattr(StrategyRuntimeEngine, "run_canonical", run_canonical)
    return touched


async def test_backtests_expose_their_snapshotted_schema_version(client):
    headers = await register_and_login(client)
    v1_strategy, v1 = await create_strategy_version(client, headers, "bt-v1")
    v2_strategy, v2 = await v2_version(client, headers, "bt-v2")
    first = await create_backtest(client, headers, v1_strategy, v1)
    second = await create_backtest(client, headers, v2_strategy, v2)
    assert first["definition_schema_version"] == 1
    assert second["definition_schema_version"] == 2
    completed = await run(client, headers, v2_strategy, v2)
    assert completed["status"] == "completed"
    assert completed["definition_schema_version"] == 2
    assert completed["result_summary"]["engine_identifier"] == "strategy-runtime-v2"
    v1_done = await run(client, headers, v1_strategy, v1)
    assert v1_done["definition_schema_version"] == 1
    assert v1_done["result_summary"]["engine_identifier"] == "ema-crossover-reference-v1"


@pytest.mark.parametrize(
    "environment",
    [
        {"fill_model": "next_bar_open"},
        {"fill_model": "banana"},
        {"timeframe": None},
        {"timeframe": "1w"},
    ],
)
async def test_unsupported_environments_fail_before_market_data(
    client, no_data_or_runtime, environment
):
    headers = await register_and_login(client)
    strategy, version = await v2_version(client, headers, f"env-{uuid.uuid4().hex[:8]}")
    env = {k: v for k, v in {**V2_ENV, **environment}.items() if v is not None}
    await rewrite(version, backtest_configuration=env)
    done = await run(client, headers, strategy, version)
    assert done["status"] == "failed"
    assert done["error_code"] == "strategy_environment_invalid"
    assert no_data_or_runtime == []


async def test_weekly_definitions_fail_before_market_data(client, no_data_or_runtime):
    headers = await register_and_login(client)
    strategy, version = await v2_version(client, headers, "weekly")
    await rewrite(
        version,
        configuration=document(timeframe="1w"),
        backtest_configuration={**V2_ENV, "timeframe": "1w"},
    )
    done = await run(client, headers, strategy, version)
    assert done["status"] == "failed" and done["error_code"] == "strategy_environment_invalid"
    assert no_data_or_runtime == []


async def test_rule_limits_fail_in_the_pre_run_gate_not_as_a_market_data_error(
    client, no_data_or_runtime
):
    headers = await register_and_login(client)
    strategy, version = await v2_version(client, headers, "limits")
    await rewrite(version, configuration=with_rule_limits(document()))
    done = await run(client, headers, strategy, version)
    assert done["status"] == "failed"
    assert done["error_code"] == "strategy_definition_unsupported_capability"
    assert "rule.limits" in done["error_message"]
    assert no_data_or_runtime == []


async def test_runtime_failures_are_not_labelled_as_market_data_errors(client, monkeypatch):
    from app.strategy_definition.runtime.errors import ExecutionError, RuntimeDataError

    headers = await register_and_login(client)
    strategy, version = await v2_version(client, headers, "runtime-codes")
    expectations = (
        (ExecutionError("adapter broke"), "strategy_runtime_failed"),
        (RuntimeDataError("unordered candles"), "market_data_invalid_payload"),
        (RuntimeError("bug"), "strategy_runtime_failed"),
    )
    for error, expected in expectations:

        def boom(self, *args, _error=error, **kwargs):
            raise _error

        monkeypatch.setattr(StrategyRuntimeEngine, "_execute", boom)
        done = await run(client, headers, strategy, version)
        assert done["status"] == "failed"
        assert done["error_code"] == expected, error


# --- lifecycle guard ----------------------------------------------------------------------------


async def test_v2_strategies_cannot_be_published(client):
    headers = await register_and_login(client)
    strategy, _ = await v2_version(client, headers, "publish-v2")
    response = await client.post(f"/api/v1/strategies/{strategy['id']}/publish", headers=headers)
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == UNSUPPORTED_CODE
    assert "backtested only" in detail["message"]
    async with AsyncSessionLocal() as session:
        row = await session.get(Strategy, uuid.UUID(strategy["id"]))
        assert row.status.name == "DRAFT" and row.is_public is False


async def test_the_guard_lives_in_the_services_not_only_the_routes(client):
    from app.schemas.allocation import AllocationCreateRequest
    from app.services.allocation import create_allocation
    from app.services.strategy import (
        UnsupportedExecutionVersionError,
        deploy_strategy,
        publish_strategy,
    )

    headers = await register_and_login(client)
    strategy, version = await v2_version(client, headers, "service-guard")
    strategy_id = uuid.UUID(strategy["id"])
    async with AsyncSessionLocal() as session:
        row = await session.get(Strategy, strategy_id)
        with pytest.raises(UnsupportedExecutionVersionError):
            await publish_strategy(session, row)
        await session.rollback()

    # Force the later lifecycle states to prove deploy and allocation refuse a V2 current version.
    async def force(status: StrategyStatus) -> None:
        async with AsyncSessionLocal() as session:
            row = await session.get(Strategy, strategy_id)
            row.status = status
            row.is_public = True
            row.current_version_id = uuid.UUID(version["id"])
            await session.commit()

    await force(StrategyStatus.PUBLISHED)
    async with AsyncSessionLocal() as session:
        row = await session.get(Strategy, strategy_id)
        with pytest.raises(UnsupportedExecutionVersionError):
            await deploy_strategy(session, row)
        await session.rollback()
    response = await client.post(f"/api/v1/strategies/{strategy['id']}/deploy", headers=headers)
    assert response.status_code == 409 and response.json()["detail"]["code"] == UNSUPPORTED_CODE

    await force(StrategyStatus.DEPLOYED)
    investor = await register_and_login(client, enroll=False)
    response = await client.post(
        "/api/v1/allocations",
        headers=investor,
        json={"strategy_id": strategy["id"], "notional_amount": "1000.00", "currency": "INR"},
    )
    assert response.status_code == 409 and response.json()["detail"]["code"] == UNSUPPORTED_CODE
    async with AsyncSessionLocal() as session:
        with pytest.raises(UnsupportedExecutionVersionError):
            await create_allocation(
                session,
                uuid.uuid4(),
                AllocationCreateRequest(
                    strategy_id=strategy_id, notional_amount="1000.00", currency="INR"
                ),
            )


async def test_v1_publish_and_deploy_are_unchanged(client):
    headers = await register_and_login(client)
    strategy, _ = await create_strategy_version(client, headers, "lifecycle-v1")
    published = await client.post(f"/api/v1/strategies/{strategy['id']}/publish", headers=headers)
    assert published.status_code == 200
    deployed = await client.post(f"/api/v1/strategies/{strategy['id']}/deploy", headers=headers)
    assert deployed.status_code == 200


# --- vocabulary ---------------------------------------------------------------------------------


async def test_the_vocabulary_describes_the_runnable_subset(client):
    headers = await register_and_login(client)
    assert (await client.get(VOCABULARY)).status_code == 401
    response = await client.get(VOCABULARY, headers=headers)
    assert response.status_code == 200
    vocabulary = response.json()
    assert vocabulary["definition_schema_version"] == 2
    assert vocabulary["timeframes"] == ["1d"]
    assert vocabulary["evaluation_modes"] == ["bar_close"]
    assert vocabulary["fill_models"] == ["same_bar_close"]
    assert vocabulary["position"]["max_core_positions"] == 1
    assert vocabulary["position"]["max_legs_per_position"] == 1
    assert vocabulary["position"]["leg_sides"] == ["buy", "sell"]
    assert vocabulary["position"]["sizing_units"] == ["shares"]
    assert vocabulary["operations"] == ["close", "open"]
    assert {"compare", "cross", "all", "any", "not", "edge"} == set(vocabulary["condition_kinds"])
    assert [i["key"] for i in vocabulary["indicators"]] == ["ema@1"]
    assert vocabulary["indicators"][0]["params"][0]["maximum"] == 5000
    assert vocabulary["supports_rule_limits"] is False
    assert vocabulary["capabilities"] == sorted(RUNTIME_CAPABILITIES)


def test_the_vocabulary_cannot_drift_from_the_runtime():
    """Every advertised indicator really is runnable; every other catalog entry really is not."""
    from app.strategy_definition.vocabulary import runnable_vocabulary

    vocabulary = runnable_vocabulary()
    advertised = {item["name"] for item in vocabulary["indicators"]}
    assert advertised == {
        spec.name
        for spec in DEFAULT_CATALOG.all()
        if f"indicator.{spec.key}" in RUNTIME_CAPABILITIES
    }
    for spec in DEFAULT_CATALOG.all():
        assert assess_v2_definition(document(spec.name), V2_ENV).runnable is (
            spec.name in advertised
        ), spec.key
    for timeframe in vocabulary["timeframes"]:
        env = {**V2_ENV, "timeframe": timeframe}
        assert assess_v2_definition(document(timeframe=timeframe), env).runnable
    for fill_model in vocabulary["fill_models"]:
        assert assess_v2_definition(document(), {**V2_ENV, "fill_model": fill_model}).runnable


async def test_a_definition_the_assessment_passes_actually_runs(client):
    """Runnable-by-assessment implies the real pre-run gate and runtime accept it."""
    headers = await register_and_login(client)
    assert assess_v2_definition(document(), V2_ENV).runnable
    strategy, version = await v2_version(client, headers, "assessed-runs")
    assert (await run(client, headers, strategy, version))["status"] == "completed"


# --- compare operators: advertised vocabulary == validator behaviour -------------------------------

PRICE = {"kind": "price", "field": "close"}
EMA = {
    "kind": "indicator", "name": "ema", "version": 1, "params": {"period": 3},
    "source": PRICE, "timeframe": "1d", "output": "value",
}
CONSTANT = {"kind": "constant", "value": 100}


def compare_document(op: str, left: dict, right: dict) -> dict:
    configuration = document()
    configuration["rules"][0]["when"] = {"kind": "compare", "op": op, "left": left, "right": right}
    return configuration


def schema_compare_operators() -> tuple[str, ...]:
    from typing import get_args, get_type_hints

    from app.strategy_definition.schema import CompareCondition

    return tuple(get_args(get_type_hints(CompareCondition)["op"]))


def test_every_advertised_compare_operator_is_runnable_on_series_operands():
    from app.strategy_definition.vocabulary import runnable_vocabulary

    advertised = runnable_vocabulary()["compare_operators"]
    assert advertised == ["gt", "gte", "lt", "lte"]
    for op_name in advertised:
        for left, right in ((PRICE, CONSTANT), (CONSTANT, PRICE), (EMA, CONSTANT), (PRICE, EMA)):
            assessment = assess_v2_definition(compare_document(op_name, left, right), V2_ENV)
            assert assessment.runnable, (op_name, left["kind"], right["kind"], assessment.issues)


def test_operators_that_are_not_advertised_are_rejected_on_series_operands():
    from app.strategy_definition.vocabulary import runnable_vocabulary

    advertised = set(runnable_vocabulary()["compare_operators"])
    not_advertised = set(schema_compare_operators()) - advertised
    assert not_advertised == {"eq"}
    for op_name in not_advertised:
        for left, right in ((PRICE, CONSTANT), (CONSTANT, PRICE), (EMA, CONSTANT), (PRICE, EMA)):
            assessment = assess_v2_definition(compare_document(op_name, left, right), V2_ENV)
            assert not assessment.savable and not assessment.runnable, (op_name, left, right)
            assert any(
                i.issue.code == "invalid_condition" and i.issue.path.endswith(".op")
                for i in assessment.issues
            )


def test_eq_between_two_constants_is_the_only_accepted_eq_and_is_not_advertised():
    """Documents the exact validator behaviour: constant-vs-constant eq passes, so the
    vocabulary must (and does) leave it out rather than offer a comparison that never changes."""
    from app.strategy_definition.vocabulary import runnable_vocabulary

    assessment = assess_v2_definition(compare_document("eq", CONSTANT, CONSTANT), V2_ENV)
    assert assessment.runnable
    assert "eq" not in runnable_vocabulary()["compare_operators"]


async def test_the_endpoints_agree_with_the_advertised_compare_operators(client):
    headers = await register_and_login(client)
    advertised = (await client.get(VOCABULARY, headers=headers)).json()["compare_operators"]
    for op_name in schema_compare_operators():
        result = (
            await client.post(
                VALIDATE, headers=headers, json=body(compare_document(op_name, PRICE, CONSTANT))
            )
        ).json()
        assert result["runnable"] is (op_name in advertised), op_name
