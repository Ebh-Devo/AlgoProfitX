from decimal import Decimal, InvalidOperation
from typing import Any

from app.models.backtest import Backtest, BacktestStatus


class BacktestAnalyticsConflict(Exception):
    pass


class BacktestAnalyticsDataError(Exception):
    pass


def build_backtest_analytics(backtest: Backtest) -> dict[str, Any]:
    if backtest.status != BacktestStatus.COMPLETED:
        raise BacktestAnalyticsConflict(
            "Backtest must be completed before analytics can be requested"
        )
    if not isinstance(backtest.result_summary, dict):
        raise BacktestAnalyticsDataError("Backtest result summary is unavailable")

    summary = backtest.result_summary
    initial_capital = _decimal(summary, "initial_capital")
    final_equity = _decimal(summary, "final_equity")
    total_return = _decimal(summary, "total_return")
    trades = _trades(summary)
    equity_curve = _equity_curve(summary)

    wins = [trade_pnl for trade_pnl in trades if trade_pnl > 0]
    losses = [trade_pnl for trade_pnl in trades if trade_pnl < 0]
    decisive_trades = len(wins) + len(losses)

    gross_wins = sum(wins, Decimal("0"))
    gross_losses = sum(losses, Decimal("0"))
    return {
        "backtest_id": backtest.id,
        "engine_identifier": _string(summary, "engine_identifier"),
        "provider_identifier": _string(summary, "provider_identifier"),
        "initial_capital": _decimal_string(initial_capital),
        "final_equity": _decimal_string(final_equity),
        "total_return": _decimal_string(total_return),
        "trade_count": len(trades),
        "win_rate": (
            _decimal_string(Decimal(len(wins)) / Decimal(decisive_trades))
            if decisive_trades
            else None
        ),
        "profit_factor": (
            _decimal_string(gross_wins / abs(gross_losses)) if losses else None
        ),
        "average_win": (
            _decimal_string(gross_wins / Decimal(len(wins))) if wins else None
        ),
        "average_loss": (
            _decimal_string(gross_losses / Decimal(len(losses))) if losses else None
        ),
        "max_drawdown": _decimal_string(_max_drawdown(equity_curve)),
        "equity_curve": equity_curve,
    }


def _trades(summary: dict[str, Any]) -> list[Decimal]:
    trades = summary.get("trades")
    if not isinstance(trades, list):
        raise BacktestAnalyticsDataError("Backtest trades are unavailable")

    pnl_values: list[Decimal] = []
    for trade in trades:
        if not isinstance(trade, dict):
            raise BacktestAnalyticsDataError("Backtest trade data is invalid")
        pnl_values.append(_decimal(trade, "pnl"))
    return pnl_values


def _equity_curve(summary: dict[str, Any]) -> list[dict[str, str]]:
    curve = summary.get("equity_curve")
    if not isinstance(curve, list):
        raise BacktestAnalyticsDataError("Backtest equity curve is unavailable")

    normalized: list[dict[str, str]] = []
    for point in curve:
        if not isinstance(point, dict):
            raise BacktestAnalyticsDataError("Backtest equity curve data is invalid")
        timestamp = _string(point, "timestamp")
        normalized.append(
            {
                "timestamp": timestamp,
                "equity": _decimal_string(_decimal(point, "equity")),
            }
        )
    return normalized


def _max_drawdown(equity_curve: list[dict[str, str]]) -> Decimal:
    """Return a non-negative closing-equity peak-to-trough percentage.

    An empty curve, or a curve without a positive peak, has zero drawdown.
    """
    peak: Decimal | None = None
    maximum_drawdown = Decimal("0")
    for point in equity_curve:
        equity = _decimal(point, "equity")
        if peak is None or equity > peak:
            peak = equity
        if peak is not None and peak > 0:
            maximum_drawdown = max(
                maximum_drawdown,
                (peak - equity) / peak * Decimal("100"),
            )
    return maximum_drawdown


def _decimal(values: dict[str, Any], key: str) -> Decimal:
    try:
        return Decimal(str(values[key]))
    except (InvalidOperation, KeyError, TypeError, ValueError) as exc:
        raise BacktestAnalyticsDataError(
            f"Backtest {key} is invalid"
        ) from exc


def _string(values: dict[str, Any], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value:
        raise BacktestAnalyticsDataError(f"Backtest {key} is invalid")
    return value


def _decimal_string(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.00000001")), "f")
