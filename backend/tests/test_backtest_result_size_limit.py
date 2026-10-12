"""The 10,000-byte JSON column limit, and the measured size of a worst-case backtest result.

Synthetic data and in-memory Data Store doubles only; nothing touches a live Catalyst environment.
The measurement helpers live in backend/scripts/measure_backtest_result_size.py (run it to print the
full table); the conclusions it supports are pinned here so they cannot silently rot.
"""

import importlib.util
import json
import uuid
from pathlib import Path

import pytest

from app.backtesting.contracts import BacktestExecutionResult
from app.models.backtest import BacktestStatus
from app.persistence.catalyst import backtest as backtest_module
from app.persistence.catalyst import strategy as strategy_module
from app.persistence.catalyst.backtest import MAX_JSON_COLUMN_BYTES, CatalystBacktestRepository
from app.schemas.backtest import BacktestCreateRequest
from app.services.catalyst_backtest import (
    MAX_RESULT_EQUITY_POINTS,
    MAX_RESULT_TRADES,
    execute_catalyst_backtest,
)
from app.strategy_definition.runtime.engine import StrategyRuntimeEngine
from tests.catalyst_memory import backtest_store
from tests.test_catalyst_strategy_v2 import v2_backtest_version

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "measure_backtest_result_size.py"
_spec = importlib.util.spec_from_file_location("measure_backtest_result_size", _SCRIPT)
measure = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(measure)

# Both repositories enforce the same limit through their own helper.
ENCODERS = [
    pytest.param(lambda v: backtest_module._json(v, "result_summary", required=True), id="backtest"),
    pytest.param(lambda v: strategy_module._bounded_json(v, "configuration"), id="strategy"),
]


def compact_len(value: dict) -> int:
    return len(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def payload_of_size(size: int, filler: str = "x") -> dict:
    """An object whose compact JSON is exactly ``size`` bytes: {"a":"<filler * n>"} is 8 + n."""
    value = {"a": filler * (size - 8)}
    assert compact_len(value) == size
    return value


def test_the_limit_is_ten_thousand_bytes():
    assert MAX_JSON_COLUMN_BYTES == 10_000
    assert strategy_module.MAX_JSON_COLUMN_BYTES == 10_000


@pytest.mark.parametrize("encode", ENCODERS)
def test_exact_boundary_is_accepted_and_one_byte_over_is_rejected(encode):
    exactly = payload_of_size(10_000)
    assert len(encode(exactly).encode("utf-8")) == 10_000
    with pytest.raises(ValueError, match="is too large"):
        encode(payload_of_size(10_001))


@pytest.mark.parametrize("encode", ENCODERS)
def test_multibyte_text_is_measured_in_encoded_bytes_not_source_characters(encode):
    # Non-ASCII is JSON-escaped (é = 6 bytes), so 1,667 characters already exceed 10,000 bytes
    # even though the source string is far below 10,000 characters.
    over = {"a": "é" * 1_667}
    assert len(over["a"]) < 10_000 and compact_len(over) > 10_000
    with pytest.raises(ValueError, match="is too large"):
        encode(over)
    # 1,665 characters is 9,998 bytes: accepted.
    under = {"a": "é" * 1_665}
    assert compact_len(under) == 9_998
    encoded = encode(under)
    assert len(encoded.encode("utf-8")) == 9_998
    # An astral character escapes to a 12-byte surrogate pair.
    assert compact_len({"a": "\U0001F600" * 832}) == 8 + 832 * 12 <= 10_000
    with pytest.raises(ValueError, match="is too large"):
        encode({"a": "\U0001F600" * 833})


@pytest.mark.parametrize("encode", ENCODERS)
def test_the_stored_text_never_has_more_bytes_than_characters(encode):
    # The reason enforcing bytes is safe for a 10,000-character column: the stored text is ASCII.
    encoded = encode({"a": "é\U0001F600" * 100})
    assert len(encoded) == len(encoded.encode("utf-8")) <= 10_000


# ------------------------------------------------------------------- terminal path, real sizes


def patched_runtime(monkeypatch, trades: int, equity_points: int):
    """Make the V2 runtime return a synthetic result of the given size (within the service caps)."""

    def run_canonical(self, canonical, backtest_configuration, candles):
        return BacktestExecutionResult(
            initial_capital=measure.Decimal("100000"),
            final_equity=measure.Decimal("123456.78901234"),
            total_return=measure.Decimal("23.45678901"),
            trades=tuple(measure.v2_trade(i) for i in range(trades)),
            equity_curve=tuple(measure.equity_point(i) for i in range(equity_points)),
            engine_identifier="strategy-runtime-v2",
            provider_identifier="synthetic-local-v1",
        )

    monkeypatch.setattr(StrategyRuntimeEngine, "run_canonical", run_canonical)


async def run_to_terminal(provision):
    provision()
    repository = CatalystBacktestRepository(backtest_store(with_schema_column=True))
    queued = await repository.create(
        version=v2_backtest_version(), requested_by_user_id=uuid.uuid4(), data=BacktestCreateRequest()
    )
    return await execute_catalyst_backtest(repository, queued.id)


@pytest.mark.asyncio
async def test_a_result_just_inside_the_limit_completes(monkeypatch, provision_schema_version_column):
    fits = measure.max_equity_points_that_fit(10)
    assert measure.summary_size(10, fits) <= 10_000 < measure.summary_size(10, fits + 1)
    patched_runtime(monkeypatch, trades=10, equity_points=fits)
    done = await run_to_terminal(provision_schema_version_column)
    assert done.status is BacktestStatus.COMPLETED
    assert done.result_summary["trade_count"] == 10


@pytest.mark.asyncio
async def test_a_result_one_point_over_the_limit_fails_terminally_without_retry(
    monkeypatch, provision_schema_version_column
):
    fits = measure.max_equity_points_that_fit(10)
    patched_runtime(monkeypatch, trades=10, equity_points=fits + 1)
    failed = await run_to_terminal(provision_schema_version_column)
    assert failed.status is BacktestStatus.FAILED
    assert failed.error_code == "backtest_result_too_large"
    assert failed.attempt_count == 1  # not retried


# ------------------------------------------------------------------------ pinned measurements


def test_the_service_caps_are_unchanged():
    assert (MAX_RESULT_TRADES, MAX_RESULT_EQUITY_POINTS) == (100, 256)


def test_the_maximum_allowed_result_does_not_fit_one_text_column():
    """Pinned finding: the caps admit results the persistence layer must reject (see issue #51).

    If this fails because a cap was lowered, a downsampling/size strategy was added, or storage
    moved off a single Text column, update the measurement and the schema-plan note deliberately.
    """
    for shape in (measure.v2_trade, measure.v1_trade):
        assert measure.summary_size(MAX_RESULT_TRADES, MAX_RESULT_EQUITY_POINTS, trade_shape=shape) > 10_000
    # Even the equity curve alone (no trades) at the cap is too large.
    assert measure.summary_size(0, MAX_RESULT_EQUITY_POINTS) > 10_000


def test_measured_frontier_of_combinations_that_fit():
    # Largest equity-point count that fits for a given trade count (V2 trade shape, synthetic data).
    assert {t: measure.max_equity_points_that_fit(t) for t in (0, 1, 5, 10, 25, 100)} == {
        0: 141, 1: 134, 5: 107, 10: 73, 25: None, 100: None,
    }
    assert measure.summary_size(0, 141) <= 10_000 < measure.summary_size(0, 142)
