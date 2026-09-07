"""Expose process health even when deployment configuration is incomplete.

The commercial API is loaded only after the same Settings/TLS validation used
by the application passes. Invalid configuration never enables product routes.
Restart the process after correcting runtime configuration.
"""

import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.core.config import get_settings


def create_runtime_app() -> FastAPI:
    try:
        settings = get_settings()
        # This validates CA material locally; it does not connect to PostgreSQL.
        settings.database_connect_args
    except (ValidationError, ValueError, OSError):
        # Pydantic errors can include raw input. Never log the exception or
        # serialize it in a response, including exception chaining/tracebacks.
        logging.getLogger(__name__).error("runtime_configuration_unavailable")
        unavailable = FastAPI(
            title="AlgoProfitX runtime",
            docs_url=None,
            redoc_url=None,
            openapi_url=None,
        )

        @unavailable.get("/health", include_in_schema=False)
        @unavailable.get("/health/live", include_in_schema=False)
        async def live():
            return {"status": "ok"}

        @unavailable.api_route(
            "/{path:path}",
            methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            include_in_schema=False,
        )
        async def configuration_unavailable(path: str):
            return JSONResponse(
                status_code=503,
                content={"status": "unavailable", "dependency": "configuration"},
                headers={"Cache-Control": "no-store"},
            )

        return unavailable

    # Keep business routes and DB initialization out of the unconfigured path.
    # Unexpected code/import errors still fail visibly rather than being hidden.
    from app.main import app as configured_app

    return configured_app


app = create_runtime_app()
