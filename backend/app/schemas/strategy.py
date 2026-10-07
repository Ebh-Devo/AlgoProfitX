import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.strategy import StrategyStatus
from app.schemas.instrument import InstrumentResponse
from app.strategy_rules import StrategyRuleError, validate_rule_configuration


class StrategyCreateRequest(BaseModel):
    name: str = Field(
        min_length=3,
        max_length=150,
    )
    # Optional: when omitted the server derives a unique slug from the name.
    slug: str | None = Field(
        default=None,
        min_length=3,
        max_length=180,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    description: str | None = None


class StrategyUpdateRequest(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=3,
        max_length=150,
    )
    slug: str | None = Field(
        default=None,
        min_length=3,
        max_length=180,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    description: str | None = None


class StrategyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    creator_id: uuid.UUID
    name: str
    slug: str
    description: str | None
    status: StrategyStatus
    is_public: bool
    current_version_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None
    deployed_at: datetime | None


class StrategyVersionCreateRequest(BaseModel):
    instrument_id: uuid.UUID
    configuration: dict[str, Any] = Field(default_factory=dict)
    backtest_configuration: dict[str, Any] = Field(
        default_factory=dict
    )

    @field_validator("configuration")
    @classmethod
    def _validate_rules(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            validate_rule_configuration(value)
        except StrategyRuleError as exc:
            raise ValueError(str(exc)) from exc
        return value


class StrategyVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_id: uuid.UUID
    instrument_id: uuid.UUID | None
    instrument: InstrumentResponse | None
    version_number: int
    configuration: dict[str, Any]
    backtest_configuration: dict[str, Any]
    created_at: datetime
