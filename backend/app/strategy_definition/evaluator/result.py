"""Three-valued condition result (docs/STRATEGY_DEFINITION_V2.md §8.3)."""

from enum import Enum
from typing import Iterable


class Tri(Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"

    @property
    def fires(self) -> bool:
        """A rule fires only on strictly TRUE."""
        return self is Tri.TRUE


def tri_not(value: Tri) -> Tri:
    if value is Tri.TRUE:
        return Tri.FALSE
    if value is Tri.FALSE:
        return Tri.TRUE
    return Tri.UNKNOWN


def tri_all(values: Iterable[Tri]) -> Tri:
    items = tuple(values)
    if any(item is Tri.FALSE for item in items):
        return Tri.FALSE
    if any(item is Tri.UNKNOWN for item in items):
        return Tri.UNKNOWN
    return Tri.TRUE


def tri_any(values: Iterable[Tri]) -> Tri:
    items = tuple(values)
    if any(item is Tri.TRUE for item in items):
        return Tri.TRUE
    if any(item is Tri.UNKNOWN for item in items):
        return Tri.UNKNOWN
    return Tri.FALSE
