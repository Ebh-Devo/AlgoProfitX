"""Shared helpers for the Strategy V2 Phase 5 runtime tests, and the runtime parity fixture.

Regenerate the golden runtime parity file after an *intentional* change with:

    python -m tests.strategy_v2_runtime_support

Two independent paths produce a parity record for the same V1 configuration:

  V1 configuration -> EmaCrossoverReferenceEngine (the V1 oracle) -> ``v1_parity_record``
  V1 configuration -> load_definition (V1 adapter) -> StrategyRuntimeEngine, same_bar_close
                      -> ``runtime_parity_record``

The golden file stores both so a change to either side fails loudly.
"""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.backtesting.contracts import BacktestExecutionResult
from app.backtesting.reference import EmaCrossoverReferenceEngine
from app.strategy_definition.evaluator import Bar, HistoricalContext
from app.strategy_definition.runtime.environment import RuntimeEnvironment
from app.strategy_definition.runtime.execution import ExecutionBar
from app.strategy_definition.runtime.engine import StrategyRuntimeEngine
from app.strategy_definition.runtime.intents import OrderConstraints, OrderIntent, ResolvedContract
from app.strategy_definition.runtime.operations import OperationSource
from tests.strategy_v2_parity_support import CAPITAL, CASES, candles, v1_parity_record

RUNTIME_GOLDEN_PATH = Path(__file__).parent / "fixtures" / "strategy_v2_runtime_parity.json"
T0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
D = Decimal


def ts(index: int) -> datetime:
    return T0 + timedelta(days=index)


def environment(capital: str = "10000", fill_model: str = "same_bar_close") -> RuntimeEnvironment:
    return RuntimeEnvironment("version-1", D(capital), fill_model)


def context(closes: list[int], index: int, indicators=None) -> HistoricalContext:
    """An evaluation context holding only bars ``0..index`` (nothing after ``t``)."""
    bars = [
        Bar(ts(i), D(c), D(c), D(c), D(c), D(1)) for i, c in enumerate(closes[: index + 1])
    ]
    series = {
        key: values[: index + 1] for key, values in (indicators or {}).items()
    }
    return HistoricalContext(bars, series)


def exec_bar(closes: list[int], index: int) -> ExecutionBar:
    return ExecutionBar(ts(index), D(closes[index]))


def intent(
    intent_id: str,
    op: str = "open",
    side: str = "buy",
    quantity: str = "10",
    position: str = "main",
    leg: str = "stock",
    source: OperationSource = OperationSource("rule", "enter"),
    at: int = 0,
) -> OrderIntent:
    return OrderIntent(
        intent_id=intent_id,
        group_id="g-" + intent_id,
        position=position,
        leg=leg,
        op=op,
        contract=ResolvedContract("primary", "primary"),
        side=side,  # type: ignore[arg-type]
        quantity=D(quantity),
        constraints=OrderConstraints(reference_price=D(100)),
        group_policy="all_or_unwind",
        signal_ts=ts(at),
        source=source,
    )


def runtime_parity_record(result: BacktestExecutionResult) -> dict[str, Any]:
    """The runtime result in the same shape as ``v1_parity_record``."""
    trades = [
        {
            "side": trade["side"],
            "signal_timestamp": trade["signal_timestamp"],
            "fill_timestamp": trade["fill_timestamp"],
            "exit_signal_timestamp": trade.get("exit_signal_timestamp"),
            "exit_fill_timestamp": trade["exit_fill_timestamp"],
            "quantity": trade["quantity"],
            "entry_price": trade["entry_price"],
            "exit_price": trade["exit_price"],
            "pnl": trade["pnl"],
            "exit_reason": trade["exit_reason"],
        }
        for trade in result.trades
    ]
    return {
        "trade_count": len(trades),
        "trades": trades,
        "initial_capital": EmaCrossoverReferenceEngine._decimal_string(result.initial_capital),
        "final_equity": EmaCrossoverReferenceEngine._decimal_string(result.final_equity),
        "equity_curve": [dict(point) for point in result.equity_curve],
    }


def compute_runtime_case(spec: dict[str, Any]) -> dict[str, Any]:
    series = candles(spec["closes"])
    configuration = spec["v1_configuration"]
    v1 = EmaCrossoverReferenceEngine("golden").run(configuration, CAPITAL, series)
    runtime = StrategyRuntimeEngine("golden", "parity-fixture").run(configuration, CAPITAL, series)
    return {
        "name": spec["name"],
        "closes": spec["closes"],
        "fill_model": "same_bar_close",
        "backtest_configuration": CAPITAL,
        "v1_configuration": configuration,
        "v1": v1_parity_record(configuration, v1, series),
        "runtime": runtime_parity_record(runtime),
    }


def compute_runtime_golden() -> dict[str, Any]:
    return {"cases": [compute_runtime_case(spec) for spec in CASES]}


if __name__ == "__main__":
    RUNTIME_GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_GOLDEN_PATH.write_text(
        json.dumps(compute_runtime_golden(), indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {RUNTIME_GOLDEN_PATH}")
