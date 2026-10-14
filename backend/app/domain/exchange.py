"""ORM-free view of an exchange, for code that only reads its identity and calendar settings.

The trading calendar needs just three attributes of an exchange: its ``code``, its IANA ``timezone`` and
whether it ``is_active``. ``ExchangeLike`` describes exactly that, so the SQLAlchemy ``Exchange`` model
and ``ExchangeSpec`` are interchangeable wherever a calendar is used. This module must stay free of
SQLAlchemy imports so the Catalyst runtime can use it without loading the ORM.
"""

from dataclasses import dataclass
from typing import Protocol


class ExchangeLike(Protocol):
    @property
    def code(self) -> str: ...

    @property
    def timezone(self) -> str: ...

    @property
    def is_active(self) -> bool: ...


@dataclass(frozen=True)
class ExchangeSpec:
    """A plain, immutable exchange description (the Catalyst backtest path has no Exchange row)."""

    code: str
    timezone: str
    is_active: bool
