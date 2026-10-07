"""Support for the Strategy V2 Phase 1 golden parity fixtures.

Regenerate the golden file after an *intentional* change with:

    python -m tests.strategy_v2_parity_support

Two independent paths produce a parity record for the same V1 configuration:

  V1 configuration -> V1 reference engine (EmaCrossoverReferenceEngine) -> V1 result
                      -> ``v1_parity_record`` (adds the fields V1 does not report)

  V1 configuration -> V1 adapter -> canonical V2 definition
                      -> ``run_v2_compat_seam`` (reads ONLY the V2 definition)

The seam is test-only and deliberately limited to the existing V1 EMA behaviour: it is not
a V2 engine. It exists to prove the canonical definition carries every semantic the V1
engine used (side, cross directions, periods, sizing, presence of an exit rule).
"""

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence

from app.backtesting.contracts import BacktestExecutionResult, Candle
from app.backtesting.reference import EmaCrossoverReferenceEngine
from app.strategy_definition import load_definition
from app.strategy_definition.schema import (
    CrossCondition,
    IndicatorRef,
    PercentOfAllocationSizing,
    StrategyDefinition,
)

GOLDEN_PATH = Path(__file__).parent / "fixtures" / "strategy_v2_parity.json"
CAPITAL = {"initial_capital": 50000}

EMA_3_9_LONG_ENTRY = {
    "type": "ema_crossover", "action": "buy", "direction": "above",
    "fast_period": 3, "slow_period": 9,
}
EMA_3_9_LONG_EXIT = {
    "type": "ema_crossover", "action": "sell", "direction": "below",
    "fast_period": 3, "slow_period": 9,
}
EMA_3_9_SHORT_ENTRY = {
    "type": "ema_crossover", "action": "sell", "direction": "below",
    "fast_period": 3, "slow_period": 9,
}
EMA_3_9_SHORT_EXIT = {
    "type": "ema_crossover", "action": "buy", "direction": "above",
    "fast_period": 3, "slow_period": 9,
}
LEGACY_ENTRY = {"type": "ema_crossover", "fast_period": 3, "slow_period": 9}

# Falls, rises (cross up), falls (cross down) and the mirror image.
DOWN_UP_DOWN = [100 - i for i in range(15)] + [86 + 2 * i for i in range(15)] + [114 - 3 * i for i in range(15)]
UP_DOWN_UP = [100 + i for i in range(15)] + [114 - 2 * i for i in range(15)] + [86 + 3 * i for i in range(15)]
# The first 28 falling then 36 rising closes of the synthetic provider: one cross up, no exit.
SYNTHETIC = [128 - i for i in range(28)] + [101 + i for i in range(36)]
STEADY_RISE = [100 + i for i in range(30)]

CASES: tuple[dict[str, Any], ...] = (
    {"name": "long_with_exit", "closes": DOWN_UP_DOWN,
     "v1_configuration": {"entry": EMA_3_9_LONG_ENTRY, "exit": EMA_3_9_LONG_EXIT}},
    {"name": "short_with_exit", "closes": UP_DOWN_UP,
     "v1_configuration": {"entry": EMA_3_9_SHORT_ENTRY, "exit": EMA_3_9_SHORT_EXIT}},
    {"name": "legacy_entry_only", "closes": DOWN_UP_DOWN,
     "v1_configuration": {"entry": LEGACY_ENTRY}},
    {"name": "long_exit_never_crosses", "closes": SYNTHETIC,
     "v1_configuration": {"entry": EMA_3_9_LONG_ENTRY, "exit": EMA_3_9_LONG_EXIT}},
    {"name": "no_entry_signal", "closes": STEADY_RISE,
     "v1_configuration": {"entry": EMA_3_9_LONG_ENTRY, "exit": EMA_3_9_LONG_EXIT}},
)

MAPPING_NOTES = {
    "fill_model": "Lifted V1 documents carry fill_model=same_bar_close: signal and fill "
    "timestamps are the same bar close, asserted equal.",
    "exit_reason": "V1 reports no exit reason. 'rule:exit' = the exit rule's cross; "
    "'end_of_data' = held to the final candle (an engine artefact, not a signal). The V1 "
    "side infers it from the exit timestamp, which cannot distinguish an exit cross on the "
    "very last candle from end-of-data; no fixture places one there.",
    "end_of_data": "An end_of_data exit has no signal, so exit_signal_timestamp is null.",
}


def candles(closes: Sequence[int]) -> tuple[Candle, ...]:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return tuple(
        Candle(
            session_date=date(2025, 1, 1) + timedelta(days=i),
            timestamp=start + timedelta(days=i),
            open=Decimal(c), high=Decimal(c), low=Decimal(c), close=Decimal(c), volume=1,
        )
        for i, c in enumerate(closes)
    )


def _text(value: Decimal) -> str:
    return EmaCrossoverReferenceEngine._decimal_string(value)


def v1_parity_record(
    configuration: dict, result: BacktestExecutionResult, series: Sequence[Candle]
) -> dict[str, Any]:
    """The V1 result extended with the fields the V1 engine does not report."""
    trades = []
    for trade in result.trades:
        rule_exit = (
            "exit" in configuration and trade["exit_timestamp"] != series[-1].timestamp.isoformat()
        )
        trades.append(
            {
                "side": trade["side"],
                "signal_timestamp": trade["entry_timestamp"],
                "fill_timestamp": trade["entry_timestamp"],
                "exit_signal_timestamp": trade["exit_timestamp"] if rule_exit else None,
                "exit_fill_timestamp": trade["exit_timestamp"],
                "quantity": trade["quantity"],
                "entry_price": trade["entry_price"],
                "exit_price": trade["exit_price"],
                "pnl": trade["pnl"],
                "exit_reason": "rule:exit" if rule_exit else "end_of_data",
            }
        )
    return {
        "trade_count": len(trades),
        "trades": trades,
        "initial_capital": _text(result.initial_capital),
        "final_equity": _text(result.final_equity),
        "equity_curve": [dict(point) for point in result.equity_curve],
    }


def _ema_cross(condition: Any) -> tuple[str, int, int]:
    assert isinstance(condition, CrossCondition)
    fast, slow = condition.left, condition.right
    for ref in (fast, slow):
        assert isinstance(ref, IndicatorRef) and (ref.name, ref.version) == ("ema", 1)
    return condition.dir, fast.params["period"], slow.params["period"]


def run_v2_compat_seam(
    definition: StrategyDefinition,
    fill_model: str | None,
    backtest_configuration: dict,
    series: Sequence[Candle],
) -> dict[str, Any]:
    """Reproduce V1 EMA behaviour from a canonical definition alone. Not a V2 engine."""
    assert fill_model == "same_bar_close", "the seam only knows V1's fill model"
    (position,) = definition.positions
    (leg,) = position.legs
    assert isinstance(position.sizing, PercentOfAllocationSizing)
    opens = [r for r in definition.rules if r.then[0].op == "open"]
    closes_ = [r for r in definition.rules if r.then[0].op == "close"]
    assert len(opens) == 1 and len(closes_) <= 1

    capital = Decimal(str(backtest_configuration["initial_capital"]))
    sign = Decimal(1) if leg.side == "buy" else Decimal(-1)
    prices = [candle.close for candle in series]
    ema, cross_index = EmaCrossoverReferenceEngine._ema, EmaCrossoverReferenceEngine._cross_index

    direction, fast, slow = _ema_cross(opens[0].when)
    entry_index = cross_index(ema(prices, fast), ema(prices, slow), direction, 1)
    exit_index, exit_signal = len(series) - 1, False
    if entry_index is not None and closes_:
        direction, fast, slow = _ema_cross(closes_[0].when)
        crossed = cross_index(ema(prices, fast), ema(prices, slow), direction, entry_index + 1)
        if crossed is not None:
            exit_index, exit_signal = crossed, True

    def equity_at(price: Decimal) -> Decimal:
        return capital + sign * quantity * (price - prices[entry_index])

    quantity = Decimal(0)
    if entry_index is not None:
        quantity = capital * position.sizing.value / Decimal(100) / prices[entry_index]
    curve = [
        {
            "timestamp": candle.timestamp.isoformat(),
            "equity": _text(
                capital
                if entry_index is None or index < entry_index
                else equity_at(prices[min(index, exit_index)])
            ),
        }
        for index, candle in enumerate(series)
    ]
    final_equity = capital if entry_index is None else equity_at(prices[exit_index])
    trades = []
    if entry_index is not None:
        trades.append(
            {
                "side": "long" if sign > 0 else "short",
                "signal_timestamp": series[entry_index].timestamp.isoformat(),
                "fill_timestamp": series[entry_index].timestamp.isoformat(),
                "exit_signal_timestamp": series[exit_index].timestamp.isoformat() if exit_signal else None,
                "exit_fill_timestamp": series[exit_index].timestamp.isoformat(),
                "quantity": _text(quantity),
                "entry_price": _text(prices[entry_index]),
                "exit_price": _text(prices[exit_index]),
                "pnl": _text(final_equity - capital),
                "exit_reason": "rule:exit" if exit_signal else "end_of_data",
            }
        )
    return {
        "trade_count": len(trades),
        "trades": trades,
        "initial_capital": _text(capital),
        "final_equity": _text(final_equity),
        "equity_curve": curve,
    }


def compute_case(spec: dict[str, Any]) -> dict[str, Any]:
    series = candles(spec["closes"])
    configuration = spec["v1_configuration"]
    result = EmaCrossoverReferenceEngine("golden").run(configuration, CAPITAL, series)
    loaded = load_definition(configuration)
    return {
        "name": spec["name"],
        "closes": spec["closes"],
        "backtest_configuration": CAPITAL,
        "v1_configuration": configuration,
        "v1_parity": v1_parity_record(configuration, result, series),
        "v2_definition": loaded.definition.to_dict(),
        "v2_fill_model": loaded.fill_model,
        "v2_parity": run_v2_compat_seam(loaded.definition, loaded.fill_model, CAPITAL, series),
    }


def compute_golden() -> dict[str, Any]:
    return {"mapping_notes": MAPPING_NOTES, "cases": [compute_case(spec) for spec in CASES]}


if __name__ == "__main__":
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_PATH.write_text(json.dumps(compute_golden(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {GOLDEN_PATH}")
