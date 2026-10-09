"""``StrategyRuntimeEngine``: the shared runtime behind the ``BacktestEngine`` protocol.

    load canonical definition -> validate + capability check -> iterate ordered candles
      -> evaluate -> intents -> simulated execution -> ledger -> BacktestExecutionResult

Selected by the backtest service only for ``definition_schema_version = 2`` (Phase 6);
V1 versions keep ``EmaCrossoverReferenceEngine``.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Sequence

from app.backtesting.contracts import BacktestExecutionError, BacktestExecutionResult, Candle
from app.strategy_definition.errors import StrategyDefinitionError
from app.strategy_definition.evaluator import EvaluatorError
from app.strategy_definition.loading import load_definition
from app.strategy_definition.runtime.environment import (
    RuntimeEnvironment,
    parse_environment,
    prepare_definition,
)
from app.strategy_definition.runtime.errors import (
    RuntimeDataError,
    RuntimeEnvironmentError,
    RuntimeSetupError,
    StrategyRuntimeError,
    UnsupportedOperationError,
)
from app.strategy_definition.runtime.execution import ExecutionAdapter, ExecutionBar
from app.strategy_definition.runtime.ledger import JournalEntry, Trade
from app.strategy_definition.runtime.market import (
    BarCursorContext,
    compute_indicator_series,
    validate_candles,
)
from app.strategy_definition.runtime.runtime import BarOutcome, StrategyRuntime
from app.strategy_definition.schema import CanonicalDefinition

QUANTUM = Decimal("0.00000001")  # the existing 8-dp output convention (spec §17.9)


def format_decimal(value: Decimal) -> str:
    return format(value.quantize(QUANTUM), "f")


def runtime_error_code(exc: Exception) -> str:
    """A stable ``BacktestExecutionError`` code for a failure raised by the runtime.

    Only a genuine candle problem is a market-data error; setup, unsupported-operation and
    execution failures are strategy errors and must not be labelled as data errors.
    """
    if isinstance(exc, RuntimeDataError):
        return "market_data_invalid_payload"
    if isinstance(exc, RuntimeEnvironmentError):
        return "strategy_environment_invalid"
    if isinstance(exc, UnsupportedOperationError):
        return "strategy_definition_unsupported_capability"
    if isinstance(exc, (RuntimeSetupError, StrategyDefinitionError)):
        return "strategy_definition_invalid"
    return "strategy_runtime_failed"


@dataclass(frozen=True)
class RuntimeRun:
    """The full, replayable record of a run."""

    environment: RuntimeEnvironment
    outcomes: tuple[BarOutcome, ...]
    equity_curve: tuple[tuple[str, Decimal], ...]  # (UTC ISO timestamp, equity)
    trades: tuple[Trade, ...]
    journal: tuple[JournalEntry, ...]
    final_equity: Decimal


class StrategyRuntimeEngine:
    """Runs any definition this runtime's capabilities cover over historical candles."""

    identifier = "strategy-runtime-v2"

    def __init__(
        self,
        provider_identifier: str,
        strategy_version_id: str,
        *,
        liquidate_at_end: bool = True,
        adapter: ExecutionAdapter | None = None,
    ) -> None:
        self._provider_identifier = provider_identifier
        self._strategy_version_id = strategy_version_id
        self._liquidate_at_end = liquidate_at_end
        self._adapter = adapter

    # --- BacktestEngine protocol -----------------------------------------------------------

    def run(
        self,
        configuration: dict,
        backtest_configuration: dict,
        candles: Sequence[Candle],
    ) -> BacktestExecutionResult:
        try:
            run = self.run_detailed(configuration, backtest_configuration, candles)
        except (StrategyRuntimeError, StrategyDefinitionError, EvaluatorError) as exc:
            raise BacktestExecutionError(str(exc), runtime_error_code(exc)) from exc
        return self._result(run)

    def _result(self, run: RuntimeRun) -> BacktestExecutionResult:
        initial = run.environment.initial_capital
        return BacktestExecutionResult(
            initial_capital=initial,
            final_equity=run.final_equity,
            total_return=(run.final_equity - initial) / initial * Decimal("100"),
            trades=tuple(_trade_record(trade) for trade in run.trades),
            equity_curve=tuple(
                {"timestamp": stamp, "equity": format_decimal(equity)}
                for stamp, equity in run.equity_curve
            ),
            engine_identifier=self.identifier,
            provider_identifier=self._provider_identifier,
        )

    def run_canonical(
        self,
        canonical: CanonicalDefinition,
        backtest_configuration: dict,
        candles: Sequence[Candle],
    ) -> BacktestExecutionResult:
        """Run an already-loaded canonical definition (the service boundary's entry point).

        The caller resolved the persisted schema version; this never re-reads stored JSON.
        """
        try:
            run = self._execute(canonical, backtest_configuration, candles)
        except (StrategyRuntimeError, StrategyDefinitionError, EvaluatorError) as exc:
            raise BacktestExecutionError(str(exc), runtime_error_code(exc)) from exc
        return self._result(run)

    # --- The loop ---------------------------------------------------------------------------

    def run_detailed(
        self,
        configuration: dict,
        backtest_configuration: dict,
        candles: Sequence[Candle],
    ) -> RuntimeRun:
        try:
            canonical = load_definition(
                configuration, v1_timeframe=backtest_configuration.get("timeframe", "1d")
            )
        except StrategyDefinitionError as exc:
            raise RuntimeSetupError(str(exc), exc.issues) from exc
        return self._execute(canonical, backtest_configuration, candles)

    def _execute(
        self,
        canonical: CanonicalDefinition,
        backtest_configuration: dict,
        candles: Sequence[Candle],
    ) -> RuntimeRun:
        # Definition and environment are gated before any candle is looked at.
        definition = prepare_definition(canonical)
        environment = parse_environment(canonical, backtest_configuration, self._strategy_version_id)
        validate_candles(candles)
        indicators = compute_indicator_series(definition, candles)
        runtime = StrategyRuntime(definition, environment, adapter=self._adapter)

        outcomes: list[BarOutcome] = []
        curve: list[tuple[str, Decimal]] = []
        last = len(candles) - 1
        for index, candle in enumerate(candles):
            bar = ExecutionBar(candle.timestamp, candle.close)
            context = BarCursorContext(candles, indicators, index)
            outcomes.append(runtime.on_bar_close(context, bar))
            if index == last and self._liquidate_at_end:
                outcomes.append(runtime.liquidate(bar))
            curve.append((candle.timestamp.isoformat(), runtime.equity(bar)))
        return RuntimeRun(
            environment=environment,
            outcomes=tuple(outcomes),
            equity_curve=tuple(curve),
            trades=runtime.ledger.trades,
            journal=runtime.ledger.journal,
            final_equity=curve[-1][1],
        )


def _trade_record(trade: Trade) -> dict[str, str]:
    """V1's trade keys, plus additive V2 fields (spec §13.2): signal/fill times, exit reason."""
    (leg,) = trade.legs
    record: dict[str, Any] = {
        "side": leg.side,
        "entry_timestamp": trade.fill_ts.isoformat(),
        "exit_timestamp": trade.exit_fill_ts.isoformat(),
        "quantity": format_decimal(leg.quantity),
        "entry_price": format_decimal(leg.entry_price),
        "exit_price": format_decimal(leg.exit_price),
        "pnl": format_decimal(trade.pnl),
        "position": trade.position_id,
        "leg": leg.leg_id,
        "signal_timestamp": trade.signal_ts.isoformat(),
        "fill_timestamp": trade.fill_ts.isoformat(),
        "exit_fill_timestamp": trade.exit_fill_ts.isoformat(),
        "exit_reason": trade.exit_reason,
    }
    if trade.exit_signal_ts is not None:  # engine-issued exits have no signal
        record["exit_signal_timestamp"] = trade.exit_signal_ts.isoformat()
    return record

