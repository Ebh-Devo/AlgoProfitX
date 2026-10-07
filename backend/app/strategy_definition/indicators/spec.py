"""Typed, immutable descriptions of catalog indicators.

These types *describe* an indicator (identity, parameters, outputs). They contain no
calculation: how an indicator is computed is a runtime concern outside this package.
"""

from dataclasses import dataclass
from typing import Any, Literal, Mapping

ParamType = Literal["integer"]


@dataclass(frozen=True)
class ParamViolation:
    """One way a params object breaks a spec. ``param`` is ``None`` for whole-object issues."""

    param: str | None
    code: str
    message: str


@dataclass(frozen=True)
class ParamSpec:
    """One accepted parameter: its type, whether it is required, and inclusive bounds."""

    name: str
    type: ParamType
    required: bool = True
    minimum: int | None = None
    maximum: int | None = None

    def check(self, value: Any) -> ParamViolation | None:
        # bool is an int subclass in Python; it is never a valid numeric parameter.
        if isinstance(value, bool) or not isinstance(value, int):
            return ParamViolation(self.name, "invalid_param_type", f"must be an {self.type}")
        if self.minimum is not None and value < self.minimum:
            return ParamViolation(self.name, "param_out_of_range", f"must be >= {self.minimum}")
        if self.maximum is not None and value > self.maximum:
            return ParamViolation(self.name, "param_out_of_range", f"must be <= {self.maximum}")
        return None


@dataclass(frozen=True)
class OutputSpec:
    """A named output of an indicator. ``value`` is the single output of simple indicators."""

    name: str
    description: str = ""


@dataclass(frozen=True)
class IndicatorSpec:
    """Versioned identity (``name@version``) plus accepted parameters and available outputs."""

    name: str
    version: int
    params: tuple[ParamSpec, ...]
    outputs: tuple[OutputSpec, ...]

    @property
    def key(self) -> str:
        return f"{self.name}@{self.version}"

    def has_output(self, name: Any) -> bool:
        return any(output.name == name for output in self.outputs)

    def validate_params(self, supplied: Mapping[str, Any]) -> tuple[ParamViolation, ...]:
        """Every violation, in deterministic order: declared params first, then unknown ones."""
        violations: list[ParamViolation] = []
        declared = {param.name for param in self.params}
        for param in self.params:
            if param.name not in supplied:
                if param.required:
                    violations.append(
                        ParamViolation(param.name, "missing_param", f"{param.name} is required")
                    )
                continue
            violation = param.check(supplied[param.name])
            if violation is not None:
                violations.append(violation)
        for name in sorted(str(key) for key in supplied if key not in declared):
            violations.append(
                ParamViolation(name, "unknown_param", f"{self.key} has no parameter {name!r}")
            )
        return tuple(violations)
