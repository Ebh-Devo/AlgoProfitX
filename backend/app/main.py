from contextlib import asynccontextmanager
import logging
import re
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.allocations import router as allocations_router
from app.api.routes.auth import router as auth_router
from app.api.routes.executions import router as executions_router
from app.api.routes.instruments import router as instruments_router
from app.api.routes.marketplace import router as marketplace_router
from app.api.routes.strategies import router as strategies_router
from app.core.config import get_settings
from app.core import health
from app.core.metrics import metrics
from app.core.observability import (
    configure_logging,
    log_event,
    request_id_context,
)
from app.db.session import dispose_engine


REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")


def _request_id(request: Request, header: str) -> str:
    supplied = request.headers.get(header, "")
    return supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else str(uuid.uuid4())


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
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
        if await health.database_ready(settings.readiness_db_timeout_seconds):
            return {"status": "ok"}
        metrics.increment("readiness.failures", tags={"dependency": "database"})
        return JSONResponse(status_code=503, content={"status": "unavailable"})

    return application


app = create_app()
