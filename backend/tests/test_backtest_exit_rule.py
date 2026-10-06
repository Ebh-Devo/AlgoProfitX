from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.backtesting.contracts import BacktestExecutionError, Candle
from app.backtesting.reference import EmaCrossoverReferenceEngine
from app.schemas.strategy import StrategyVersionCreateRequest

ENTRY = {"type": "ema_crossover", "fast_period": 3, "slow_period": 9}
EXIT = {"type": "ema_crossover", "direction": "below", "fast_period": 3, "slow_period": 9}
CAPITAL = {"initial_capital": 50000}


def candles(closes):
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return tuple(
        Candle(
            session_date=date(2025, 1, 1) + timedelta(days=i),
            timestamp=start + timedelta(days=i),
            open=Decimal(c), high=Decimal(c), low=Decimal(c), close=Decimal(c), volume=1,
        )
        for i, c in enumerate(closes)
    )


# Falls, rises (entry cross up), then falls again (exit cross down).
CLOSES = [100 - i for i in range(15)] + [86 + 2 * i for i in range(15)] + [114 - 3 * i for i in range(15)]
engine = EmaCrossoverReferenceEngine("test")


def run(configuration):
    return engine.run(configuration, CAPITAL, candles(CLOSES))


def test_entry_only_configuration_holds_to_final_candle():
    result = run({"entry": ENTRY})
    assert len(result.trades) == 1
    assert result.trades[0]["exit_timestamp"] == candles(CLOSES)[-1].timestamp.isoformat()


def test_exit_rule_closes_trade_on_downward_cross():
    held = run({"entry": ENTRY})
    exited = run({"entry": ENTRY, "exit": EXIT})
    trade = exited.trades[0]
    assert trade["exit_timestamp"] < held.trades[0]["exit_timestamp"]
    assert Decimal(trade["exit_price"]) != Decimal(held.trades[0]["exit_price"])
    # Equity is flat after the exit.
    tail = [p["equity"] for p in exited.equity_curve if p["timestamp"] >= trade["exit_timestamp"]]
    assert len(set(tail)) == 1
    assert abs(exited.final_equity - Decimal(tail[-1])) < Decimal("0.00000001")


def test_exit_without_cross_holds_to_end():
    closes = [128 - i for i in range(28)] + [101 + i for i in range(36)]
    result = engine.run({"entry": ENTRY, "exit": EXIT}, CAPITAL, candles(closes))
    assert result.trades[0]["exit_timestamp"] == candles(closes)[-1].timestamp.isoformat()


@pytest.mark.parametrize(
    "bad",
    [
        {"type": "ema_crossover", "direction": "above", "fast_period": 3, "slow_period": 9},
        {"type": "ema_crossover", "direction": "below", "fast_period": 9, "slow_period": 9},
        {"type": "ema_crossover", "direction": "below", "fast_period": 0, "slow_period": 9},
        {"type": "ema_crossover", "direction": "below", "fast_period": "x", "slow_period": 9},
        {"type": "other"},
        "sell",
    ],
)
def test_invalid_exit_rules_are_rejected(bad):
    with pytest.raises(BacktestExecutionError):
        run({"entry": ENTRY, "exit": bad})
    with pytest.raises(ValidationError):
        StrategyVersionCreateRequest(
            instrument_id="00000000-0000-0000-0000-000000000001",
            configuration={"entry": ENTRY, "exit": bad},
        )


def test_entry_only_and_valid_exit_configurations_validate():
    for cfg in ({"entry": ENTRY}, {"entry": ENTRY, "exit": EXIT}):
        StrategyVersionCreateRequest(
            instrument_id="00000000-0000-0000-0000-000000000001", configuration=cfg
        )
