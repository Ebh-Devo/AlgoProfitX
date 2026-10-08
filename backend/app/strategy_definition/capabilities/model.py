"""Capability names, their three layers, and the requirement set (spec §15).

A capability is a *requirement* a definition places on whatever runs it. Nothing here knows
what any environment provides.
"""

from dataclasses import dataclass
from enum import Enum
from typing import AbstractSet, Iterable


class CapabilityLayer(str, Enum):
    """Who provides a capability; kept apart so a failure can say which is missing."""

    IMPLEMENTATION = "implementation"  # the runtime's code
    DATA = "data"  # market-data / reference-data providers
    ENVIRONMENT = "environment"  # the execution / accounting environment


# Each capability name belongs to exactly one family; a name outside every family is rejected.
_LAYER_PREFIXES: tuple[tuple[str, CapabilityLayer], ...] = (
    ("indicator.", CapabilityLayer.IMPLEMENTATION),
    ("op.", CapabilityLayer.IMPLEMENTATION),
    ("risk.", CapabilityLayer.IMPLEMENTATION),
    ("leg.", CapabilityLayer.IMPLEMENTATION),
    ("resolver.", CapabilityLayer.IMPLEMENTATION),
    ("data.", CapabilityLayer.DATA),
    ("short_sell", CapabilityLayer.ENVIRONMENT),
    ("margin.", CapabilityLayer.ENVIRONMENT),
    ("multi_leg.", CapabilityLayer.ENVIRONMENT),
    ("positions.", CapabilityLayer.ENVIRONMENT),
)


def layer_of(name: str) -> CapabilityLayer:
    """The layer a capability belongs to; unknown name families are rejected."""
    for prefix, layer in _LAYER_PREFIXES:
        if name == prefix or (prefix.endswith(".") and name.startswith(prefix)):
            return layer
    raise ValueError(f"unknown capability {name!r}: no layer declared for it")


@dataclass(frozen=True)
class CapabilitySpec:
    """A capability and the prerequisites it declares. The graph owns this relationship."""

    name: str
    prerequisites: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        layer_of(self.name)
        for prerequisite in self.prerequisites:
            layer_of(prerequisite)
        object.__setattr__(self, "prerequisites", frozenset(self.prerequisites))

    @property
    def layer(self) -> CapabilityLayer:
        return layer_of(self.name)


@dataclass(frozen=True)
class CapabilityRequirements:
    """An immutable set of required capability names."""

    required: frozenset[str]

    def __init__(self, required: Iterable[str] = ()) -> None:
        names = frozenset(required)
        for name in names:
            layer_of(name)
        object.__setattr__(self, "required", names)

    def sorted(self) -> tuple[str, ...]:
        return tuple(sorted(self.required))

    def by_layer(self) -> dict[CapabilityLayer, tuple[str, ...]]:
        """Names grouped by layer, every layer present, each group sorted."""
        return {
            layer: tuple(name for name in self.sorted() if layer_of(name) is layer)
            for layer in CapabilityLayer
        }

    def to_dict(self) -> dict[str, list[str]]:
        return {layer.value: list(names) for layer, names in self.by_layer().items()}

    def __sub__(self, provided: "AbstractSet[str] | CapabilityRequirements") -> frozenset[str]:
        """What is required but not provided: ``required_capabilities(d) - provided``."""
        if isinstance(provided, CapabilityRequirements):
            provided = provided.required
        return self.required - frozenset(provided)

    def __contains__(self, name: object) -> bool:
        return name in self.required

    def __len__(self) -> int:
        return len(self.required)
