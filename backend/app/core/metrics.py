from collections import Counter
from collections.abc import Mapping
from typing import Protocol


class Metrics(Protocol):
    def increment(
        self, name: str, value: int = 1, tags: Mapping[str, str] | None = None
    ) -> None: ...

    def observe(
        self, name: str, value: float, tags: Mapping[str, str] | None = None
    ) -> None: ...


class NoOpMetrics:
    def increment(
        self, name: str, value: int = 1, tags: Mapping[str, str] | None = None
    ) -> None:
        return None

    def observe(
        self, name: str, value: float, tags: Mapping[str, str] | None = None
    ) -> None:
        return None


class InMemoryMetrics(NoOpMetrics):
    """Small deterministic recorder for tests; not a production metrics backend."""

    def __init__(self) -> None:
        self.counters: Counter[tuple[str, tuple[tuple[str, str], ...]]] = Counter()
        self.observations: list[tuple[str, float, dict[str, str]]] = []

    def increment(
        self, name: str, value: int = 1, tags: Mapping[str, str] | None = None
    ) -> None:
        self.counters[(name, tuple(sorted((tags or {}).items())))] += value

    def observe(
        self, name: str, value: float, tags: Mapping[str, str] | None = None
    ) -> None:
        self.observations.append((name, value, dict(tags or {})))


class MetricsFacade(NoOpMetrics):
    def __init__(self) -> None:
        self.backend: Metrics = NoOpMetrics()

    def increment(
        self, name: str, value: int = 1, tags: Mapping[str, str] | None = None
    ) -> None:
        self.backend.increment(name, value, tags)

    def observe(
        self, name: str, value: float, tags: Mapping[str, str] | None = None
    ) -> None:
        self.backend.observe(name, value, tags)


metrics = MetricsFacade()


def set_metrics(backend: Metrics) -> None:
    metrics.backend = backend
