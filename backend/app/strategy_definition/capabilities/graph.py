"""The capability graph: each capability's prerequisites, expanded transitively (spec §15)."""

from types import MappingProxyType
from typing import Iterable, Mapping

from app.strategy_definition.capabilities.model import CapabilityRequirements, CapabilitySpec


class CapabilityGraphCycleError(ValueError):
    """The graph has a prerequisite cycle; ``cycle`` lists it, first node repeated last."""

    def __init__(self, cycle: tuple[str, ...]):
        self.cycle = cycle
        super().__init__("capability prerequisite cycle: " + " -> ".join(cycle))


class CapabilityGraph:
    """Immutable ``capability -> prerequisites`` relation, built from capability specs.

    Acyclic and fully classified. The graph is the single owner of prerequisites: nothing
    else (catalog metadata included) is inspected to decide what a capability needs.
    """

    __slots__ = ("_edges",)

    def __init__(self, specs: Iterable[CapabilitySpec] = ()):
        edges: dict[str, frozenset[str]] = {}
        for spec in specs:
            if spec.name in edges:
                raise ValueError(f"duplicate capability {spec.name!r}")
            edges[spec.name] = spec.prerequisites
        _reject_cycles(edges)
        object.__setattr__(self, "_edges", MappingProxyType(dict(sorted(edges.items()))))

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable")

    def prerequisites(self, name: str) -> tuple[str, ...]:
        """Direct prerequisites only, sorted."""
        return tuple(sorted(self._edges.get(name, ())))

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


def _reject_cycles(edges: Mapping[str, frozenset[str]]) -> None:
    done: set[str] = set()

    def visit(name: str, trail: tuple[str, ...]) -> None:
        if name in trail:
            raise CapabilityGraphCycleError(trail[trail.index(name) :] + (name,))
        if name in done:
            return
        for dep in sorted(edges.get(name, ())):
            visit(dep, trail + (name,))
        done.add(name)

    for name in sorted(edges):
        visit(name, ())


# Capabilities that declare prerequisites. Empty today: no V2.0 catalog indicator needs
# anything beyond its own name. Entries are added with the feature that introduces them, e.g.
# CapabilitySpec("indicator.vwap@1", frozenset({"data.intraday_bars", "data.session_anchor"})).
DEFAULT_CAPABILITY_GRAPH = CapabilityGraph()
