from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.backtesting.contracts import BacktestExecutionError, Candle
from app.backtesting.reference import EmaCrossoverReferenceEngine
from app.schemas.strategy import StrategyVersionCreateRequest

ENTRY = {"type": "ema_crossover", "fast_period": 3, "slow_period": 9}
EXIT = {"type": "ema_crossover", "direction": "below", "fast_period": 3, "slow_period": 9}
LONG_ENTRY = {**ENTRY, "action": "buy", "direction": "above"}
LONG_EXIT = {**EXIT, "action": "sell"}
SHORT_ENTRY = {**ENTRY, "action": "sell", "direction": "below"}
SHORT_EXIT = {**EXIT, "action": "buy", "direction": "above"}
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
        {"type": "ema_crossover", "direction": "sideways", "fast_period": 3, "slow_period": 9},
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


# ── Buy/sell actions ────────────────────────────────────────────────────────────

# Rises (long entry cross up), falls (long exit / short entry cross down), rises again
# (short exit cross up). Deterministic.
ZIGZAG = (
    [100 - i for i in range(15)]
    + [86 + 2 * i for i in range(15)]
    + [114 - 3 * i for i in range(15)]
    + [69 + 3 * i for i in range(15)]
)


def run_zigzag(configuration):
    return engine.run(configuration, CAPITAL, candles(ZIGZAG))


def test_long_buy_then_sell_matches_existing_behaviour():
    explicit = run_zigzag({"entry": LONG_ENTRY, "exit": LONG_EXIT})
    legacy = run_zigzag({"entry": ENTRY, "exit": EXIT})
    assert explicit.trades == legacy.trades
    assert explicit.equity_curve == legacy.equity_curve
    trade = explicit.trades[0]
    assert trade["side"] == "long"
    entry_price, exit_price = Decimal(trade["entry_price"]), Decimal(trade["exit_price"])
    assert Decimal(trade["pnl"]) > 0
    assert abs(Decimal(trade["pnl"]) - Decimal(trade["quantity"]) * (exit_price - entry_price)) < Decimal("0.0001")


def test_short_sell_then_buy_profits_when_price_falls():
    result = run_zigzag({"entry": SHORT_ENTRY, "exit": SHORT_EXIT})
    trade = result.trades[0]
    assert trade["side"] == "short"
    entry_price, exit_price = Decimal(trade["entry_price"]), Decimal(trade["exit_price"])
    assert exit_price < entry_price
    quantity = Decimal(trade["quantity"])
    expected = quantity * (entry_price - exit_price)
    assert Decimal(trade["pnl"]) > 0
    assert abs(Decimal(trade["pnl"]) - expected) < Decimal("0.0001")
    assert abs(result.final_equity - (Decimal(50000) + expected)) < Decimal("0.0001")
    # Equity moves opposite to price while the short is open and is flat after the exit.
    points = {p["timestamp"]: Decimal(p["equity"]) for p in result.equity_curve}
    assert points[trade["entry_timestamp"]] == Decimal(50000)
    tail = [v for t, v in points.items() if t >= trade["exit_timestamp"]]
    assert len(set(tail)) == 1


def test_short_loses_when_price_rises():
    closes = [100 - i for i in range(15)] + [86 + 2 * i for i in range(15)]
    # Short entry on a cross *above* (mean-reversion style) then no exit: price keeps rising.
    config = {"entry": {**SHORT_ENTRY, "direction": "above"}}
    result = engine.run(config, CAPITAL, candles(closes))
    trade = result.trades[0]
    assert trade["side"] == "short"
    assert Decimal(trade["exit_price"]) > Decimal(trade["entry_price"])
    assert Decimal(trade["pnl"]) < 0
    assert result.final_equity < Decimal(50000)


def test_entry_only_short_holds_to_final_candle():
    result = run_zigzag({"entry": SHORT_ENTRY})
    assert result.trades[0]["exit_timestamp"] == candles(ZIGZAG)[-1].timestamp.isoformat()


@pytest.mark.parametrize("action", ["BUY", "hold", "", None, 1])
def test_invalid_actions_are_rejected(action):
    for cfg in (
        {"entry": {**ENTRY, "action": action}},
        {"entry": LONG_ENTRY, "exit": {**LONG_EXIT, "action": action}},
    ):
        with pytest.raises(BacktestExecutionError):
            run_zigzag(cfg)
        with pytest.raises(ValidationError):
            StrategyVersionCreateRequest(
                instrument_id="00000000-0000-0000-0000-000000000001", configuration=cfg
            )


@pytest.mark.parametrize(
    "cfg",
    [
        {"entry": LONG_ENTRY, "exit": {**LONG_EXIT, "action": "buy"}},
        {"entry": SHORT_ENTRY, "exit": {**SHORT_EXIT, "action": "sell"}},
        {"entry": ENTRY, "exit": {**EXIT, "action": "buy"}},
    ],
)
def test_exit_must_take_the_opposite_side(cfg):
    with pytest.raises(BacktestExecutionError):
        run_zigzag(cfg)
    with pytest.raises(ValidationError):
        StrategyVersionCreateRequest(
            instrument_id="00000000-0000-0000-0000-000000000001", configuration=cfg
        )


def test_buy_sell_and_legacy_configurations_validate():
    for cfg in (
        {"entry": ENTRY},
        {"entry": ENTRY, "exit": EXIT},
        {"entry": LONG_ENTRY, "exit": LONG_EXIT},
        {"entry": SHORT_ENTRY, "exit": SHORT_EXIT},
        {"entry": SHORT_ENTRY},
    ):
        StrategyVersionCreateRequest(
            instrument_id="00000000-0000-0000-0000-000000000001", configuration=cfg
        )


def test_schema_does_not_depend_on_a_concrete_engine():
    import app.schemas.strategy as schema

    source = open(schema.__file__, encoding="utf-8").read()
    assert "backtesting" not in source
