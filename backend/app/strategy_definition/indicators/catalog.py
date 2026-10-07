"""The indicator catalog: a local, immutable, deterministic registry of indicator specs."""

from typing import Iterable

from app.strategy_definition.indicators.spec import IndicatorSpec, OutputSpec, ParamSpec


class UnknownIndicatorError(LookupError):
    """No indicator with this name is registered."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"unknown indicator {name!r}")


class UnknownIndicatorVersionError(LookupError):
    """The indicator exists but not at this version. Never resolved to another version."""

    def __init__(self, name: str, version: int, available: tuple[int, ...]):
        self.name = name
        self.version = version
        self.available = available
        super().__init__(
            f"indicator {name!r} has no version {version} "
            f"(available: {', '.join(str(v) for v in available)})"
        )


class IndicatorCatalog:
    """Read-only lookup over indicator specs, keyed by ``(name, version)``."""

    def __init__(self, specs: Iterable[IndicatorSpec]):
        by_key: dict[tuple[str, int], IndicatorSpec] = {}
        for spec in specs:
            key = (spec.name, spec.version)
            if key in by_key:
                raise ValueError(f"duplicate indicator {spec.key}")
            by_key[key] = spec
        self._specs = tuple(by_key[key] for key in sorted(by_key))

    def get(self, name: str, version: int) -> IndicatorSpec:
        for spec in self._specs:
            if spec.name == name and spec.version == version:
                return spec
        available = self.versions(name)
        if not available:
            raise UnknownIndicatorError(name)
        raise UnknownIndicatorVersionError(name, version, available)

    def has(self, name: str, version: int) -> bool:
        return any(spec.name == name and spec.version == version for spec in self._specs)

    def versions(self, name: str) -> tuple[int, ...]:
        return tuple(spec.version for spec in self._specs if spec.name == name)

    def all(self) -> tuple[IndicatorSpec, ...]:
        """Every registered indicator, ordered by (name, version)."""
        return self._specs


_VALUE = (OutputSpec("value", "the indicator's single output series"),)
# Upper bound on lookback periods (spec §9.3: period in [1, 5000]).
_PERIOD = ParamSpec("period", "integer", required=True, minimum=1, maximum=5000)

# Only what the V2 foundation and its fixtures use. Add entries here, never speculatively.
DEFAULT_CATALOG = IndicatorCatalog(
    [
        IndicatorSpec("ema", 1, (_PERIOD,), _VALUE),
        IndicatorSpec("rsi", 1, (_PERIOD,), _VALUE),
    ]
)
