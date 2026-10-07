"""Structured validation errors for strategy definitions."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationIssue:
    """One problem in a document. ``path`` locates the node (``rules[0].when.left``)."""

    path: str
    code: str
    message: str
    severity: str = "error"

    def to_dict(self) -> dict[str, str]:
        return {
            "path": self.path,
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
        }


class StrategyDefinitionError(ValueError):
    """A strategy configuration cannot be loaded into a canonical definition."""

    def __init__(self, issues: list[ValidationIssue] | tuple[ValidationIssue, ...]):
        self.issues = tuple(issues)
        super().__init__(
            "; ".join(f"{issue.path or '<root>'}: {issue.message}" for issue in self.issues)
        )
