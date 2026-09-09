from contextlib import asynccontextmanager
import asyncio
import hashlib
import hmac
import logging
import re
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone

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
from app.core.metrics import metrics
from app.core.observability import (
    configure_logging,
    log_event,
    request_id_context,
)
from app.backtesting.worker import run_backtest_worker
from app.db.session import dispose_engine
from app.persistence.catalyst import (
    CatalystAuthSessionRepository,
    CatalystIdentityRepository,
    CatalystPersistenceClient,
    CatalystPersistenceError,
)
from app.persistence.auth_session import SessionTokenRejected


REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")


def _catalyst_probe_crud_allowed(settings) -> bool:
    """Keep the destructive connectivity probe out of Production."""
    return (
        settings.app_env is AppEnvironment.DEVELOPMENT
        or settings.catalyst_probe_crud_enabled
    ) and settings.app_env is not AppEnvironment.PRODUCTION


def _request_id(request: Request, header: str) -> str:
    supplied = request.headers.get(header, "")
    return supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else str(uuid.uuid4())


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    stop_event = asyncio.Event()
    worker = None
    if settings.backtest_execution_mode == "worker":
        worker = asyncio.create_task(run_backtest_worker(stop_event))
    try:
        yield
    finally:
        if worker is not None:
            stop_event.set()
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
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

    @application.get("/health", include_in_schema=False)
    @application.get("/health/live", include_in_schema=False)
    async def health_live():
        return {"status": "ok"}

    @application.get("/health/ready", include_in_schema=False)
    async def health_ready():
        try:
            if await health.database_ready(settings.readiness_db_timeout_seconds):
                return {"status": "ok"}
        except Exception:
            pass
        metrics.increment("readiness.failures", tags={"dependency": "database"})
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

    return application


app = create_app()
