"""The capability graph: each capability's prerequisites, expanded transitively (spec §15)."""

from types import MappingProxyType
from typing import Iterable, Mapping

from app.strategy_definition.capabilities.model import CapabilityRequirements, layer_of
from app.strategy_definition.indicators import DEFAULT_CATALOG, IndicatorCatalog


class CapabilityGraphCycleError(ValueError):
    """The graph has a prerequisite cycle; ``cycle`` lists it, first node repeated last."""

    def __init__(self, cycle: tuple[str, ...]):
        self.cycle = cycle
        super().__init__("capability prerequisite cycle: " + " -> ".join(cycle))


class CapabilityGraph:
    """Immutable ``capability -> prerequisites`` edges. Acyclic and fully classified."""

    __slots__ = ("_edges",)

    def __init__(self, edges: Mapping[str, Iterable[str]]):
        normalized = {name: tuple(sorted(set(deps))) for name, deps in edges.items()}
        for name, deps in normalized.items():
            layer_of(name)
            for dep in deps:
                layer_of(dep)
        _reject_cycles(normalized)
        object.__setattr__(self, "_edges", MappingProxyType(dict(sorted(normalized.items()))))

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable")

    def prerequisites(self, name: str) -> tuple[str, ...]:
        """Direct prerequisites only, sorted."""
        return self._edges.get(name, ())

    def expand(self, requirements: CapabilityRequirements) -> CapabilityRequirements:
        """The requirements plus every transitive prerequisite. Deterministic and idempotent."""
        seen: set[str] = set()
        pending = sorted(requirements.required)
        while pending:
            name = pending.pop()
            if name in seen:
                continue
            seen.add(name)
            pending.extend(self.prerequisites(name))
        return CapabilityRequirements(seen)


def _reject_cycles(edges: Mapping[str, tuple[str, ...]]) -> None:
    done: set[str] = set()

    def visit(name: str, trail: tuple[str, ...]) -> None:
        if name in trail:
            raise CapabilityGraphCycleError(trail[trail.index(name) :] + (name,))
        if name in done:
            return
        for dep in edges.get(name, ()):
            visit(dep, trail + (name,))
        done.add(name)

    for name in sorted(edges):
        visit(name, ())


def build_capability_graph(catalog: IndicatorCatalog = DEFAULT_CATALOG) -> CapabilityGraph:
    """Edges implied by the catalog: a session-anchored indicator needs intraday bars and the
    session calendar. Nothing is hard-coded per indicator, so new catalog entries declare
    their own requirements through their spec."""
    edges: dict[str, tuple[str, ...]] = {}
    for spec in catalog.all():
        if spec.anchor == "session":
            edges[f"indicator.{spec.key}"] = ("data.intraday_bars", "data.session_anchor")
    return CapabilityGraph(edges)


DEFAULT_CAPABILITY_GRAPH = build_capability_graph()
