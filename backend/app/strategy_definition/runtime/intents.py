"""The broker-independent order-intent contract (spec §14.4) and deterministic identity.

Nothing here knows a broker: no broker ids, symbols or tokens. Intent ids are a SHA-256 of a
canonical JSON of the approved identity inputs. There is no randomness, clock or process
state in an id, so replaying the same strategy, data and state regenerates the same ids.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal

from app.strategy_definition.runtime.operations import OperationSource

INTENT_ID_SCHEME = "algoprofitx.intent-id/v1"
GROUP_ID_SCHEME = "algoprofitx.group-id/v1"
DEFAULT_GROUP_POLICY = "all_or_unwind"


def _canonical_ts(timestamp: datetime) -> str:
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("bar timestamps must be timezone-aware")
    return timestamp.astimezone(timezone.utc).isoformat()


def _digest(payload: dict[str, Any]) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def make_group_id(
    strategy_version_id: str, source: OperationSource, bar_timestamp: datetime, op_index: int
) -> str:
    """Legs of one operation share a group: hash(version, rule|risk id, bar ts, op_index)."""
    return _digest(
        {
            "scheme": GROUP_ID_SCHEME,
            "strategy_version_id": strategy_version_id,
            "source_kind": source.kind,
            "source_id": source.id,
            "bar_ts": _canonical_ts(bar_timestamp),
            "op_index": op_index,
        }
    )


def make_intent_id(
    strategy_version_id: str,
    source: OperationSource,
    bar_timestamp: datetime,
    op_index: int,
    leg_id: str,
) -> str:
    """hash(strategy_version_id, rule_id|risk_id, bar_timestamp, op_index, leg_id)."""
    return _digest(
        {
            "scheme": INTENT_ID_SCHEME,
            "strategy_version_id": strategy_version_id,
            "source_kind": source.kind,
            "source_id": source.id,
            "bar_ts": _canonical_ts(bar_timestamp),
            "op_index": op_index,
            "leg_id": leg_id,
        }
    )


@dataclass(frozen=True)
class ResolvedContract:
    """A broker-agnostic tradeable. V2.0 has only the ``primary`` instrument."""

    kind: Literal["primary"]
    instrument_ref: str


@dataclass(frozen=True)
class OrderConstraints:
    reference_price: Decimal
    time_in_force: str = "bar"
    limit_price: Decimal | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "time_in_force": self.time_in_force,
            "limit_price": None if self.limit_price is None else str(self.limit_price),
            "reference_price": str(self.reference_price),
        }


@dataclass(frozen=True)
class OrderIntent:
    intent_id: str
    group_id: str
    position: str
    leg: str
    op: str
    contract: ResolvedContract
    side: Literal["buy", "sell"]
    quantity: Decimal
    constraints: OrderConstraints
    group_policy: str
    signal_ts: datetime  # the bar close at which the strategy decided (spec §17.3)
    source: OperationSource  # rule / risk / engine that produced it, for attribution

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "group_id": self.group_id,
            "position": self.position,
            "leg": self.leg,
            "op": self.op,
            "contract": {"kind": self.contract.kind, "instrument_ref": self.contract.instrument_ref},
            "side": self.side,
            "quantity": str(self.quantity),
            "constraints": self.constraints.to_dict(),
            "group_policy": self.group_policy,
            "signal_ts": _canonical_ts(self.signal_ts),
            "source": {"kind": self.source.kind, "id": self.source.id},
        }
