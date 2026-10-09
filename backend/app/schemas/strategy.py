import uuid
from datetime import datetime
from typing import Any, Literal

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
    # Optional for existing V1 clients. A body claiming any other version (e.g. 2) is a 422:
    # this route never creates anything but V1.
    definition_schema_version: Literal[1] | None = None
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


class StrategyVersionV2CreateRequest(BaseModel):
    """A V2 definition. The version is explicit, required and never inferred from the JSON."""

    model_config = ConfigDict(extra="forbid")

    definition_schema_version: Literal[2]
    instrument_id: uuid.UUID
    configuration: dict[str, Any]
    backtest_configuration: dict[str, Any]


class DefinitionValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    definition_schema_version: Literal[2]
    configuration: dict[str, Any]
    backtest_configuration: dict[str, Any]


DefinitionIssueLayer = Literal["schema", "semantic", "position", "capability", "environment"]


class DefinitionIssue(BaseModel):
    path: str
    code: str
    message: str
    severity: Literal["error", "warning"]
    layer: DefinitionIssueLayer


class DefinitionValidationResponse(BaseModel):
    definition_schema_version: Literal[2]
    valid: bool
    savable: bool
    runnable: bool
    issues: list[DefinitionIssue]
    required_capabilities: list[str]
    unsupported_capabilities: list[str]


class InvalidDefinitionDetail(BaseModel):
    """The ``detail`` of a 422 for a V2 definition that cannot be saved."""

    code: str
    message: str
    issues: list[DefinitionIssue]


class VocabularyParam(BaseModel):
    name: str
    type: str
    required: bool
    minimum: int | None
    maximum: int | None


class VocabularyIndicator(BaseModel):
    key: str
    name: str
    version: int
    params: list[VocabularyParam]
    outputs: list[str]


class VocabularyPosition(BaseModel):
    roles: list[str]
    max_core_positions: int | None
    max_legs_per_position: int | None
    instrument_kinds: list[str]
    leg_sides: list[str]
    sizing_units: list[str]


class DefinitionVocabularyResponse(BaseModel):
    definition_schema_version: Literal[2]
    timeframes: list[str]
    evaluation_modes: list[str]
    fill_models: list[str]
    position: VocabularyPosition
    operations: list[str]
    condition_kinds: list[str]
    compare_operators: list[str]
    cross_directions: list[str]
    edge_directions: list[str]
    operand_kinds: list[str]
    price_fields: list[str]
    indicator_source_fields: list[str]
    indicators: list[VocabularyIndicator]
    supports_rule_limits: bool
    supports_risk_rules: bool
    capabilities: list[str]


class StrategyVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_id: uuid.UUID
    instrument_id: uuid.UUID | None
    instrument: InstrumentResponse | None
    version_number: int
    definition_schema_version: int
    configuration: dict[str, Any]
    backtest_configuration: dict[str, Any]
    created_at: datetime
