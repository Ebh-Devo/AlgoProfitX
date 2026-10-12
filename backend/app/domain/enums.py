"""ORM-free domain enums.

These are the persisted status/type enums shared by the SQLAlchemy models, the schemas
and the Catalyst persistence layer. This module must stay free of SQLAlchemy imports so the
Catalyst runtime can use the enums without loading the ORM. The members and values are
persisted (PostgreSQL enum types and Catalyst rows) and must not change.
"""

import enum


class StrategyStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPLOYED = "deployed"
    ARCHIVED = "archived"


class InstrumentType(str, enum.Enum):
    EQUITY = "equity"
    INDEX = "index"


class BacktestStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AllocationStatus(str, enum.Enum):
    ACTIVE = "active"


class ExecutionStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class MarketDataDatasetStatus(str, enum.Enum):
    READY = "ready"
    FAILED = "failed"
