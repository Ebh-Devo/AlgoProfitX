from fastapi import FastAPI

from app.api.routes.allocations import router as allocations_router
from app.api.routes.auth import router as auth_router
from app.api.routes.marketplace import router as marketplace_router
from app.api.routes.strategies import router as strategies_router


app = FastAPI(
    title="TradeEBH API",
    version="0.1.0",
)


app.include_router(
    auth_router,
    prefix="/api/v1",
)

app.include_router(
    strategies_router,
    prefix="/api/v1",
)

app.include_router(
    marketplace_router,
    prefix="/api/v1",
)

app.include_router(
    allocations_router,
    prefix="/api/v1",
)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
