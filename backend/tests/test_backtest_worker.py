from types import SimpleNamespace

import pytest

from app.backtesting import worker


@pytest.mark.asyncio
async def test_catalyst_worker_polls_durable_queue_in_production(monkeypatch):
    settings = SimpleNamespace(
        uses_catalyst_persistence=True,
        backtest_worker_poll_seconds=0.01,
    )
    client = object()
    repositories = []
    stop_event = worker.asyncio.Event()

    class Repository:
        def __init__(self, candidate):
            assert candidate is client

    async def process(repository):
        repositories.append(repository)
        stop_event.set()
        return None

    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    monkeypatch.setattr(worker, "CatalystPersistenceClient", lambda: client)
    monkeypatch.setattr(worker, "CatalystBacktestRepository", Repository)
    monkeypatch.setattr(worker, "process_oldest_catalyst_backtest", process)

    await worker.run_backtest_worker(stop_event)

    assert len(repositories) == 1
