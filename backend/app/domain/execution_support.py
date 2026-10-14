"""ORM-free execution-support guard for strategy definition versions.

Strategy V2 definitions are backtest-only: publishing, deploying and allocating them is refused with a
stable structured 409. This module must stay free of SQLAlchemy imports so the Catalyst runtime can use
the guard without loading the ORM. ``app.services.strategy`` re-exports every name here, so existing
imports (and ``except`` clauses) keep referring to the same objects.
"""

V1_SCHEMA_VERSION = 1

UNSUPPORTED_EXECUTION_VERSION_CODE = "strategy_definition_version_unsupported_for_execution"


class UnsupportedExecutionVersionError(ValueError):
    """A strategy whose version this execution environment cannot run (V2 is backtest-only).

    A ``ValueError`` so existing lifecycle handlers still treat it as a 409; routes map it to the
    stable structured detail ``{"code", "message"}``.
    """

    code = UNSUPPORTED_EXECUTION_VERSION_CODE

    def __init__(self, action: str, schema_version: object):
        self.message = (
            f"Cannot {action}: strategy definition schema version {schema_version!r} is not "
            "supported by the current execution environment. Version 2 definitions can be "
            "backtested only."
        )
        super().__init__(self.message)

    def detail(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


def require_execution_supported(version: object | None, action: str) -> None:
    """Only legacy/V1 versions can be published, deployed or allocated: paper and live execution
    understand the V1 configuration only. The persisted column decides; the JSON is never read."""
    if version is None:
        return
    schema_version = getattr(version, "definition_schema_version", None)
    if schema_version is not None and schema_version != V1_SCHEMA_VERSION:
        raise UnsupportedExecutionVersionError(action, schema_version)
