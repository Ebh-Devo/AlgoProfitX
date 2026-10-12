"""Deterministic, synthetic worst-case size measurement for a backtest ``result_summary``.

Builds summaries through the real ``build_result_summary`` and the real cap constants, serialises
them exactly as the repository does (compact, sorted-key JSON, measured in UTF-8 bytes) and compares
against ``MAX_JSON_COLUMN_BYTES``. No I/O, no Catalyst, no randomness: all data is synthetic.

Run from backend/:  python scripts/measure_backtest_result_size.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

# Importing the app needs a configured Settings object; this script never uses the value.
os.environ.setdefault("SECRET_KEY", "measurement-script-not-a-secret")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.backtesting.contracts import BacktestExecutionResult  # noqa: E402
from app.persistence.catalyst.backtest import MAX_JSON_COLUMN_BYTES  # noqa: E402
from app.services.catalyst_backtest import (  # noqa: E402
    MAX_RESULT_EQUITY_POINTS,
    MAX_RESULT_TRADES,
    build_result_summary,
)

START = datetime(2024, 1, 1, 3, 45, tzinfo=timezone.utc)
Q = Decimal("0.00000001")


def _d(value: Decimal) -> str:
    return format(value.quantize(Q), "f")


def _stamp(index: int) -> str:
    return (START + timedelta(days=index)).isoformat()


def v1_trade(index: int) -> dict[str, str]:
    """The V1 reference engine's trade shape (7 keys)."""
    return {
        "side": "long",
        "entry_timestamp": _stamp(index),
        "exit_timestamp": _stamp(index + 1),
        "quantity": _d(Decimal("81.12345678")),
        "entry_price": _d(Decimal("1234.56789012")),
        "exit_price": _d(Decimal("1250.12345678")),
        "pnl": _d(Decimal("1262.12345678")),
    }


def v2_trade(index: int) -> dict[str, str]:
    """The V2 runtime's trade shape (V1 keys plus additive fields; the largest case)."""
    return {
        **v1_trade(index),
        "position": "position_1",
        "leg": "leg_1",
        "signal_timestamp": _stamp(index),
        "fill_timestamp": _stamp(index),
        "exit_fill_timestamp": _stamp(index + 1),
        "exit_reason": "exit_rule",
        "exit_signal_timestamp": _stamp(index + 1),
    }


def equity_point(index: int) -> dict[str, str]:
    return {"timestamp": _stamp(index), "equity": _d(Decimal("100000") + Decimal("1234.56789012") * index)}


def summary_size(trades: int, equity_points: int, *, trade_shape=v2_trade) -> int:
    result = BacktestExecutionResult(
        initial_capital=Decimal("100000"),
        final_equity=Decimal("123456.78901234"),
        total_return=Decimal("23.45678901"),
        trades=tuple(trade_shape(i) for i in range(trades)),
        equity_curve=tuple(equity_point(i) for i in range(equity_points)),
        engine_identifier="strategy-runtime-v2",
        provider_identifier="synthetic-local-v1",
    )
    encoded = json.dumps(build_result_summary(result), sort_keys=True, separators=(",", ":"))
    return len(encoded.encode("utf-8"))


def max_equity_points_that_fit(trades: int, *, trade_shape=v2_trade) -> int | None:
    """Largest equity-point count (<= the cap) that fits with ``trades`` trades; None if none do."""
    best = None
    for points in range(MAX_RESULT_EQUITY_POINTS + 1):
        if summary_size(trades, points, trade_shape=trade_shape) <= MAX_JSON_COLUMN_BYTES:
            best = points
    return best


TRADE_SWEEP = (0, 1, 5, 10, 25, 50, 100)
POINT_SWEEP = (0, 32, 64, 128, 256)


def main() -> None:
    print(f"limit: {MAX_JSON_COLUMN_BYTES} UTF-8 bytes; caps: {MAX_RESULT_TRADES} trades, {MAX_RESULT_EQUITY_POINTS} equity points")
    for name, shape in (("V2 trade shape", v2_trade), ("V1 trade shape", v1_trade)):
        print(f"\n{name}: compact-JSON bytes (rows = trades, columns = equity points)")
        print("trades | " + " ".join(f"{p:>7}" for p in POINT_SWEEP))
        for t in TRADE_SWEEP:
            print(f"{t:>6} | " + " ".join(f"{summary_size(t, p, trade_shape=shape):>7}" for p in POINT_SWEEP))
        print("max equity points that fit per trade count:")
        for t in TRADE_SWEEP:
            print(f"  trades={t:>3}: {max_equity_points_that_fit(t, trade_shape=shape)}")
        full = summary_size(MAX_RESULT_TRADES, MAX_RESULT_EQUITY_POINTS, trade_shape=shape)
        print(f"at both caps ({MAX_RESULT_TRADES}, {MAX_RESULT_EQUITY_POINTS}): {full} bytes -> {'fits' if full <= MAX_JSON_COLUMN_BYTES else 'DOES NOT FIT'}")


if __name__ == "__main__":
    main()
