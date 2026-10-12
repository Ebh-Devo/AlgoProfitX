import uuid
from datetime import datetime

from pydantic import BaseModel

from app.domain.enums import StrategyStatus


class MarketplaceStrategyResponse(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str | None
    status: StrategyStatus
    published_at: datetime | None
    current_version_id: uuid.UUID | None
    current_version_number: int | None
