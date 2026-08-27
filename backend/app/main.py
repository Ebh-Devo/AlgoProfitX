from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.allocations import router as allocations_router
from app.api.routes.auth import router as auth_router
from app.api.routes.executions import router as executions_router
from app.api.routes.instruments import router as instruments_router
from app.api.routes.marketplace import router as marketplace_router
from app.api.routes.strategies import router as strategies_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=f"{settings.app_name} API",
        version="0.1.0",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
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

    @application.get("/health")
    async def health_check():
        return {"status": "ok"}

    return application


app = create_app()
