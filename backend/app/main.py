from contextlib import asynccontextmanager
import asyncio
import hashlib
import hmac
import logging
import os
import re
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.allocations import router as allocations_router
from app.api.routes.auth import router as auth_router
from app.api.routes.executions import router as executions_router
from app.api.routes.instruments import router as instruments_router
from app.api.routes.marketplace import router as marketplace_router
from app.api.routes.strategies import router as strategies_router
from app.core.config import AppEnvironment, get_settings
from app.core.security import hash_password, verify_password
from app.core import health
from app.core.build_info import build_identity
from app.core.metrics import metrics
from app.core.observability import (
    configure_logging,
    log_event,
    request_id_context,
)
from app.db.session import dispose_engine
from app.persistence.catalyst import (
    CatalystAuthSessionRepository,
    CatalystBacktestRepository,
    CatalystIdentityRepository,
    CatalystInstrumentRepository,
    CatalystPersistenceClient,
    CatalystPersistenceError,
    CatalystStrategyRepository,
)
from app.persistence.catalyst.backtest import (
    CatalystBacktestConflict,
)
from app.persistence.auth_session import SessionTokenRejected
from app.domain.enums import InstrumentType
from app.domain.enums import BacktestStatus
from app.domain.enums import StrategyStatus
from app.persistence.strategy import (
    DuplicateStrategySlug,
    ExchangeSnapshotRecord,
    InstrumentSnapshotRecord,
)
from app.schemas.backtest import BacktestCreateRequest
from app.services.analytics import build_backtest_analytics
from app.services.catalyst_backtest import execute_catalyst_backtest
from app.instrument_identity import SYNTHETIC_EQUITY_ID, SYNTHETIC_EQUITY_SYMBOL


REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")


def _catalyst_probe_crud_allowed(settings) -> bool:
    """The write probes are unauthenticated and mutate the Data Store, so they are explicit opt-in
    (CATALYST_PROBE_CRUD_ENABLED=true) in non-production and never available in Production."""
    return (
        settings.catalyst_probe_crud_enabled
        and settings.app_env is not AppEnvironment.PRODUCTION
    )


def _request_id(request: Request, header: str) -> str:
    supplied = request.headers.get(header, "")
    return supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else str(uuid.uuid4())


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        yield
    finally:
        await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    application = FastAPI(
        title=f"{settings.app_name} API",
        version="0.1.0",
        docs_url="/docs" if settings.api_docs_enabled else None,
        redoc_url="/redoc" if settings.api_docs_enabled else None,
        openapi_url="/openapi.json" if settings.api_docs_enabled else None,
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
    )

    @application.middleware("http")
    async def observe_request(request: Request, call_next):
        request_id = _request_id(request, settings.request_id_header)
        request.state.request_id = request_id
        token = request_id_context.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_context.reset(token)
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        response.headers[settings.request_id_header] = request_id
        route = request.scope.get("route")
        safe_path = getattr(route, "path", request.url.path)
        tags = {"method": request.method, "status": str(response.status_code)}
        metrics.increment("http.requests", tags=tags)
        metrics.observe("http.duration_ms", duration_ms, tags=tags)
        if response.status_code >= 500:
            metrics.increment("http.server_errors", tags=tags)
        log_event(
            "http_request_completed",
            request_id=request_id,
            method=request.method,
            path=safe_path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response

    @application.exception_handler(Exception)
    async def unexpected_exception(request: Request, _: Exception):
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        log_event(
            "unexpected_server_error",
            level=logging.ERROR,
            exc_info=True,
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
            headers={settings.request_id_header: request_id},
        )

    application.include_router(
        auth_router,
        prefix="/api/v1",
    )

    application.include_router(
        strategies_router,
        prefix="/api/v1",
    )

    application.include_router(
        marketplace_router,
        prefix="/api/v1",
    )

    application.include_router(
        allocations_router,
        prefix="/api/v1",
    )

    application.include_router(
        executions_router,
        prefix="/api/v1",
    )

    application.include_router(
        instruments_router,
        prefix="/api/v1",
    )

    _RELEASE_IDENTITY = {
        "repository": os.getenv("APP_SOURCE_REPO", "Ebh-Devo/AlgoProfitX"),
        **build_identity(),
        "component": "algoprofitx-api",
    }

    @application.get("/api/version", include_in_schema=True, tags=["meta"])
    async def api_version():
        return _RELEASE_IDENTITY

    @application.get("/health", include_in_schema=False)
    @application.get("/health/live", include_in_schema=False)
    async def health_live():
        return {"status": "ok"}

    @application.get("/health/ready", include_in_schema=False)
    async def health_ready(request: Request):
        try:
            if settings.uses_catalyst_persistence:
                client = CatalystPersistenceClient(request=request)
                checks = await client.async_connectivity_checks(
                    settings.catalyst_probe_table
                )
                ready = all(checks.values())
            else:
                ready = await health.database_ready(settings.readiness_db_timeout_seconds)
            if ready:
                return {"status": "ok"}
        except Exception:
            pass
        dependency = "catalyst" if settings.uses_catalyst_persistence else "database"
        metrics.increment("readiness.failures", tags={"dependency": dependency})
        return JSONResponse(status_code=503, content={"status": "unavailable"})

    @application.get("/health/catalyst", include_in_schema=False)
    async def health_catalyst(request: Request):
        catalyst_client = CatalystPersistenceClient(request=request)
        try:
            checks = await catalyst_client.async_connectivity_checks(
                settings.catalyst_probe_table
            )
        except (CatalystPersistenceError, ValueError):
            checks = {
                "sdk_initialization": False,
                "datastore_access": False,
                "zcql_access": False,
            }
        ready = all(checks.values())
        if not ready:
            metrics.increment("readiness.failures", tags={"dependency": "catalyst"})
        return JSONResponse(
            status_code=200 if ready else 503,
            content={
                "status": "ok" if ready else "unavailable",
                "dependency": "catalyst",
                "checks": {
                    name: "PASS" if passed else "FAIL"
                    for name, passed in checks.items()
                },
            },
        )

    @application.post("/health/catalyst/crud", include_in_schema=False)
    async def health_catalyst_crud(request: Request):
        if not _catalyst_probe_crud_allowed(settings):
            return JSONResponse(status_code=404, content={"status": "not_found"})

        catalyst_client = CatalystPersistenceClient(request=request)
        table_name = settings.catalyst_probe_table
        marker = secrets.token_urlsafe(18)
        result = {
            "insert": "FAIL",
            "select": "FAIL",
            "update": "FAIL",
            "delete": "FAIL",
            "probe_cleanup": "FAIL",
        }
        row_id: str | None = None
        try:
            inserted = await catalyst_client.async_insert_row(
                table_name,
                {"probe_value": "connectivity-test", "probe_marker": marker},
            )
            row_id = str(inserted.get("ROWID", ""))
            if not row_id or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", row_id):
                raise CatalystPersistenceError("Catalyst returned an invalid probe row")
            result["insert"] = "PASS"

            selected = await asyncio.to_thread(
                catalyst_client.query_rows,
                f"SELECT ROWID, probe_value, probe_marker FROM {table_name} "
                f"WHERE ROWID = '{row_id}' LIMIT 1",
                table_name,
            )
            if (
                isinstance(selected, list)
                and selected
                and selected[0].get("ROWID") is not None
                and selected[0].get("probe_marker") == marker
            ):
                result["select"] = "PASS"

            updated = await catalyst_client.async_update_row(
                table_name,
                {"ROWID": row_id, "probe_value": "connectivity-updated"},
            )
            if updated.get("ROWID") == row_id:
                result["update"] = "PASS"

            await catalyst_client.async_delete_row(table_name, row_id)
            result["delete"] = "PASS"

            remaining = await asyncio.to_thread(
                catalyst_client.query_rows,
                f"SELECT ROWID FROM {table_name} WHERE ROWID = '{row_id}' LIMIT 1",
                table_name,
            )
            if isinstance(remaining, list) and not remaining:
                result["probe_cleanup"] = "PASS"
        except (CatalystPersistenceError, ValueError):
            if row_id and result["delete"] != "PASS":
                try:
                    await catalyst_client.async_delete_row(table_name, row_id)
                    result["probe_cleanup"] = "PASS"
                except (CatalystPersistenceError, ValueError):
                    pass
        return result

    @application.post("/health/catalyst/identity", include_in_schema=False)
    async def health_catalyst_identity(request: Request):
        if not _catalyst_probe_crud_allowed(settings):
            return JSONResponse(status_code=404, content={"status": "not_found"})

        catalyst_client = CatalystPersistenceClient(request=request)
        repository = CatalystIdentityRepository(catalyst_client)
        marker = secrets.token_urlsafe(18)
        email = f"identity-probe-{marker}@example.invalid"
        result = {
            "registration": "FAIL",
            "email_lookup": "FAIL",
            "authentication": "FAIL",
            "default_role": "FAIL",
            "creator_enrollment": "FAIL",
            "probe_cleanup": "FAIL",
        }
        user_id: uuid.UUID | None = None
        try:
            password_hash = await asyncio.to_thread(hash_password, marker)
            registered = await repository.register_user(
                email=email,
                password_hash=password_hash,
                full_name="Connectivity Probe",
            )
            user_id = registered.id
            result["registration"] = "PASS"
            if [role.name for role in registered.roles] == ["INVESTOR"]:
                result["default_role"] = "PASS"

            selected = await repository.get_user_by_email(email)
            if selected is not None and selected.id == user_id:
                result["email_lookup"] = "PASS"
                if await asyncio.to_thread(
                    verify_password,
                    marker,
                    selected.password_hash,
                ):
                    result["authentication"] = "PASS"

            enrolled = await repository.enroll_creator(user_id)
            if [role.name for role in enrolled.roles] == ["CREATOR", "INVESTOR"]:
                result["creator_enrollment"] = "PASS"
        except (CatalystPersistenceError, ValueError, RuntimeError):
            pass
        finally:
            if user_id is not None:
                try:
                    deleted = await repository.delete_user(user_id)
                    remaining = await repository.get_user_by_id(user_id)
                    if deleted and remaining is None:
                        result["probe_cleanup"] = "PASS"
                except (CatalystPersistenceError, ValueError):
                    pass
        return result

    @application.post("/health/catalyst/auth-sessions", include_in_schema=False)
    async def health_catalyst_auth_sessions(request: Request):
        if not _catalyst_probe_crud_allowed(settings):
            return JSONResponse(status_code=404, content={"status": "not_found"})

        repository = CatalystAuthSessionRepository(
            CatalystPersistenceClient(request=request)
        )
        user_id = uuid.uuid4()
        created_ids: set[uuid.UUID] = set()
        result = {
            "session_create": "FAIL",
            "refresh_rotation": "FAIL",
            "reuse_detection": "FAIL",
            "session_limit": "FAIL",
            "revocation": "FAIL",
            "probe_cleanup": "FAIL",
        }

        def token_hash() -> str:
            return hashlib.sha256(secrets.token_bytes(48)).hexdigest()

        try:
            first_id = uuid.uuid4()
            first_hash = token_hash()
            rotated_hash = token_hash()
            await repository.create_session(
                session_id=first_id,
                user_id=user_id,
                refresh_token_hash=first_hash,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
                max_sessions=1,
            )
            created_ids.add(first_id)
            result["session_create"] = "PASS"

            rotated = await repository.rotate_session(
                session_id=first_id,
                supplied_token_hash=first_hash,
                replacement_token_hash=rotated_hash,
            )
            if hmac.compare_digest(rotated.refresh_token_hash, rotated_hash):
                result["refresh_rotation"] = "PASS"

            try:
                await repository.rotate_session(
                    session_id=first_id,
                    supplied_token_hash=first_hash,
                    replacement_token_hash=token_hash(),
                )
            except SessionTokenRejected as exc:
                if exc.suspicious_reuse:
                    result["reuse_detection"] = "PASS"

            limited_id = uuid.uuid4()
            limited_hash = token_hash()
            await repository.create_session(
                session_id=limited_id,
                user_id=user_id,
                refresh_token_hash=limited_hash,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
                max_sessions=1,
            )
            created_ids.add(limited_id)
            try:
                await repository.rotate_session(
                    session_id=first_id,
                    supplied_token_hash=rotated_hash,
                    replacement_token_hash=token_hash(),
                )
            except SessionTokenRejected:
                result["session_limit"] = "PASS"

            revoked = await repository.revoke_session(
                session_id=limited_id,
                supplied_token_hash=limited_hash,
            )
            if revoked.revoked_at is not None:
                result["revocation"] = "PASS"
        except (CatalystPersistenceError, SessionTokenRejected, ValueError):
            pass
        finally:
            cleanup_ok = True
            for session_id in created_ids:
                try:
                    await repository.delete_session(session_id)
                except (CatalystPersistenceError, ValueError):
                    cleanup_ok = False
            for session_id in created_ids:
                try:
                    if await repository.delete_session(session_id):
                        cleanup_ok = False
                except (CatalystPersistenceError, ValueError):
                    cleanup_ok = False
            if cleanup_ok and created_ids:
                result["probe_cleanup"] = "PASS"
        return result

    @application.post("/health/catalyst/strategies", include_in_schema=False)
    async def health_catalyst_strategies(request: Request):
        if not _catalyst_probe_crud_allowed(settings):
            return JSONResponse(status_code=404, content={"status": "not_found"})

        repository = CatalystStrategyRepository(
            CatalystPersistenceClient(request=request)
        )
        creator_id = uuid.uuid4()
        marker = secrets.token_hex(12)
        slug = f"strategy-probe-{marker}"
        updated_slug = f"strategy-probe-updated-{marker}"
        result = {
            "create": "FAIL",
            "owned_read": "FAIL",
            "list": "FAIL",
            "update": "FAIL",
            "duplicate_slug": "FAIL",
            "version_create": "FAIL",
            "version_read": "FAIL",
            "version_list": "FAIL",
            "publish": "FAIL",
            "deploy": "FAIL",
            "archive": "FAIL",
            "probe_cleanup": "FAIL",
        }
        strategy_id: uuid.UUID | None = None
        try:
            created = await repository.create_strategy(
                creator_id=creator_id,
                name="Connectivity Strategy",
                slug=slug,
                description="Generated Development connectivity probe",
            )
            strategy_id = created.id
            result["create"] = "PASS"

            selected = await repository.get_strategy(
                strategy_id=strategy_id,
                creator_id=creator_id,
            )
            if selected is not None and selected.id == strategy_id:
                result["owned_read"] = "PASS"

            listed = await repository.list_strategies(creator_id)
            if [item.id for item in listed] == [strategy_id]:
                result["list"] = "PASS"

            updated = await repository.update_strategy(
                strategy_id=strategy_id,
                creator_id=creator_id,
                updates={
                    "name": "Updated Connectivity Strategy",
                    "slug": updated_slug,
                },
            )
            if updated is not None and updated.slug == updated_slug:
                result["update"] = "PASS"

            try:
                await repository.create_strategy(
                    creator_id=uuid.uuid4(),
                    name="Duplicate Connectivity Strategy",
                    slug=updated_slug,
                    description=None,
                )
            except DuplicateStrategySlug:
                result["duplicate_slug"] = "PASS"

            now = datetime.now(timezone.utc)
            instrument = InstrumentSnapshotRecord(
                id=uuid.uuid4(),
                exchange=ExchangeSnapshotRecord(
                    id=uuid.uuid4(),
                    code="PROBE",
                    name="Development Probe Exchange",
                    country_code="IN",
                    timezone="Asia/Kolkata",
                    default_currency="INR",
                    calendar_code="PROBE",
                    is_active=True,
                ),
                canonical_symbol="PROBE_EQ",
                exchange_symbol="PROBE_EQ",
                name="Development Probe Equity",
                instrument_type=InstrumentType.EQUITY,
                quote_currency="INR",
                tick_size=Decimal("0.05"),
                lot_size=1,
                is_tradeable=True,
                isin=None,
                is_synthetic=True,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            version = await repository.create_version(
                strategy_id=strategy_id,
                creator_id=creator_id,
                instrument=instrument,
                configuration={"probe": True},
                backtest_configuration={},
            )
            result["version_create"] = "PASS"
            selected_version = await repository.get_version(
                strategy_id=strategy_id,
                version_id=version.id,
                creator_id=creator_id,
            )
            if selected_version is not None and selected_version.id == version.id:
                result["version_read"] = "PASS"
            versions = await repository.list_versions(
                strategy_id=strategy_id, creator_id=creator_id
            )
            if [item.id for item in versions] == [version.id]:
                result["version_list"] = "PASS"

            published = await repository.transition_strategy(
                strategy_id=strategy_id,
                creator_id=creator_id,
                target=StrategyStatus.PUBLISHED,
            )
            if published is not None and published.current_version_id == version.id:
                result["publish"] = "PASS"
            deployed = await repository.transition_strategy(
                strategy_id=strategy_id,
                creator_id=creator_id,
                target=StrategyStatus.DEPLOYED,
            )
            if deployed is not None and deployed.deployed_at is not None:
                result["deploy"] = "PASS"
            archived = await repository.transition_strategy(
                strategy_id=strategy_id,
                creator_id=creator_id,
                target=StrategyStatus.ARCHIVED,
            )
            if archived is not None and not archived.is_public:
                result["archive"] = "PASS"
        except (CatalystPersistenceError, DuplicateStrategySlug, ValueError):
            pass
        finally:
            if strategy_id is not None:
                try:
                    await repository.cleanup_probe_strategy(
                        strategy_id=strategy_id,
                        creator_id=creator_id,
                    )
                    verified = await repository.get_strategy(
                        strategy_id=strategy_id,
                        creator_id=creator_id,
                    )
                    if verified is None:
                        result["probe_cleanup"] = "PASS"
                except (CatalystPersistenceError, ValueError):
                    pass
        return result

    @application.post("/health/catalyst/instruments", include_in_schema=False)
    async def health_catalyst_instruments(request: Request):
        if not _catalyst_probe_crud_allowed(settings):
            return JSONResponse(status_code=404, content={"status": "not_found"})
        repository = CatalystInstrumentRepository(
            CatalystPersistenceClient(request=request)
        )
        result = {
            "bootstrap": "FAIL",
            "detail": "FAIL",
            "list": "FAIL",
            "filters": "FAIL",
        }
        try:
            exchanges, instruments = await repository.bootstrap_defaults()
            if (exchanges, instruments) == (2, 3):
                result["bootstrap"] = "PASS"
            selected = await repository.get_instrument(
                uuid.UUID("20000000-0000-4000-8000-000000000001")
            )
            if selected is not None and selected.exchange.code == "NSE":
                result["detail"] = "PASS"
            listed = await repository.list_instruments(
                exchange_code=None,
                instrument_type=None,
                symbol=None,
                search=None,
                is_tradeable=None,
                is_active=True,
                limit=20,
                offset=0,
            )
            if len(listed) == 3:
                result["list"] = "PASS"
            filtered = await repository.list_instruments(
                exchange_code="nse",
                instrument_type=InstrumentType.INDEX,
                symbol=None,
                search="bank",
                is_tradeable=False,
                is_active=True,
                limit=20,
                offset=0,
            )
            if len(filtered) == 1 and filtered[0].canonical_symbol == "NSE:BANK_NIFTY":
                result["filters"] = "PASS"
        except (CatalystPersistenceError, ValueError):
            pass
        return result

    @application.post("/health/catalyst/backtests", include_in_schema=False)
    async def health_catalyst_backtests(request: Request):
        if not _catalyst_probe_crud_allowed(settings):
            return JSONResponse(status_code=404, content={"status": "not_found"})
        client = CatalystPersistenceClient(request=request)
        strategies = CatalystStrategyRepository(client)
        instruments = CatalystInstrumentRepository(client)
        backtests = CatalystBacktestRepository(client)
        creator_id = uuid.uuid4()
        marker = secrets.token_hex(12)
        strategy_id: uuid.UUID | None = None
        backtest_id: uuid.UUID | None = None
        result = {
            "queue": "FAIL",
            "claim": "FAIL",
            "execute": "FAIL",
            "terminal_read": "FAIL",
            "analytics": "FAIL",
            "probe_cleanup": "FAIL",
        }
        try:
            instrument = await instruments.get_instrument(SYNTHETIC_EQUITY_ID)
            if instrument is None:
                return result
            strategy = await strategies.create_strategy(
                creator_id=creator_id,
                name="Backtest Connectivity Strategy",
                slug=f"backtest-probe-{marker}",
                description="Generated Development backtest probe",
            )
            strategy_id = strategy.id
            version = await strategies.create_version(
                strategy_id=strategy.id,
                creator_id=creator_id,
                instrument=instrument,
                configuration={
                    "instrument": SYNTHETIC_EQUITY_SYMBOL,
                    "entry": {"type": "ema_crossover", "fast_period": 5, "slow_period": 20},
                },
                backtest_configuration={"initial_capital": "100000", "timeframe": "1d"},
            )
            queued = await backtests.create(
                version=version,
                requested_by_user_id=creator_id,
                data=BacktestCreateRequest(),
            )
            backtest_id = queued.id
            if queued.status is BacktestStatus.QUEUED:
                result["queue"] = "PASS"
            completed = await execute_catalyst_backtest(backtests, queued.id)
            if completed.attempt_count == 1:
                result["claim"] = "PASS"
            if completed.status is BacktestStatus.COMPLETED:
                result["execute"] = "PASS"
            selected = await backtests.get(
                strategy_version_id=version.id, backtest_id=queued.id
            )
            if selected is not None and selected.status is BacktestStatus.COMPLETED:
                result["terminal_read"] = "PASS"
                analytics = build_backtest_analytics(selected)
                if analytics["backtest_id"] == queued.id:
                    result["analytics"] = "PASS"
        except (CatalystPersistenceError, ValueError):
            pass
        finally:
            cleanup_ok = True
            if backtest_id is not None:
                try:
                    await backtests.cleanup(backtest_id)
                except (CatalystPersistenceError, ValueError):
                    cleanup_ok = False
            if strategy_id is not None:
                try:
                    await strategies.cleanup_probe_strategy(
                        strategy_id=strategy_id, creator_id=creator_id
                    )
                except (CatalystPersistenceError, ValueError):
                    cleanup_ok = False
            if cleanup_ok and strategy_id is not None and backtest_id is not None:
                result["probe_cleanup"] = "PASS"
        return result

    return application


app = create_app()
