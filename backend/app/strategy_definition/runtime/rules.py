"""The rule engine: conditions -> position operations. Nothing else.

It evaluates the *existing* V2 conditions with the existing evaluator, fires a rule only on a
strictly TRUE result (UNKNOWN does not fire), reads position state only from the immutable
pre-bar snapshot, and emits operations. It computes no order side, plans no quantity, and has
no handle on the ledger, so it cannot mutate one.
"""

from dataclasses import dataclass

from app.strategy_definition.evaluator import EvaluationContext, Tri, evaluate_condition
from app.strategy_definition.runtime.errors import RuntimeSetupError, UnsupportedOperationError
from app.strategy_definition.runtime.operations import (
    CandidateOperation,
    OperationSource,
    SkippedOperation,
)
from app.strategy_definition.runtime.state import RuntimeSnapshot
from app.strategy_definition.runtime.state_machine import precondition_violation
from app.strategy_definition.schema import Rule, StrategyDefinition

# A rule without an explicit ``priority`` takes this one, so unset rules tie and run in
# declaration order (spec §11.1: "lower runs first; default by declaration order").
DEFAULT_PRIORITY = 0
# Operations this runtime executes. ``increase`` / ``reduce`` stay reserved.
SUPPORTED_OPERATIONS = frozenset({"open", "close"})


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    result: Tri | None  # None: the ``when_position`` guard failed, so the condition was not run


@dataclass(frozen=True)
class RuleEvaluation:
    results: tuple[RuleResult, ...]  # in evaluation order
    candidates: tuple[CandidateOperation, ...]  # executable operations, evaluation order
    skipped: tuple[SkippedOperation, ...]


class RuleEngine:
    def __init__(self, definition: StrategyDefinition) -> None:
        position_ids = {position.id for position in definition.positions}
        for rule in definition.rules:
            if rule.limits is not None:
                raise UnsupportedOperationError(
                    f"rule {rule.id!r}: limits.max_fires_per_position is not supported by this runtime"
                )
            for operation in rule.then:
                if operation.op not in SUPPORTED_OPERATIONS:
                    raise UnsupportedOperationError(
                        f"rule {rule.id!r}: operation {operation.op!r} is reserved, not implemented"
                    )
                if operation.position not in position_ids:
                    raise RuntimeSetupError(
                        f"rule {rule.id!r} targets unknown position {operation.position!r}"
                    )
        ordered = sorted(
            enumerate(definition.rules),
            key=lambda pair: (
                DEFAULT_PRIORITY if pair[1].priority is None else pair[1].priority,
                pair[0],
            ),
        )
        self._rules: tuple[Rule, ...] = tuple(rule for _, rule in ordered)

    @property
    def rule_order(self) -> tuple[str, ...]:
        return tuple(rule.id for rule in self._rules)

    def evaluate(self, context: EvaluationContext, snapshot: RuntimeSnapshot) -> RuleEvaluation:
        statuses = {position.position_id: position.status for position in snapshot.positions}
        results: list[RuleResult] = []
        candidates: list[CandidateOperation] = []
        skipped: list[SkippedOperation] = []
        for rule in self._rules:
            source = OperationSource("rule", rule.id)
            if rule.when_position is not None and any(
                statuses[position].value != wanted
                for position, wanted in rule.when_position.items()
            ):
                results.append(RuleResult(rule.id, None))
                continue
            result = evaluate_condition(rule.when, context)
            results.append(RuleResult(rule.id, result))
            if not result.fires:
                continue
            for op_index, operation in enumerate(rule.then):
                reason = precondition_violation(statuses[operation.position], operation.op)
                if reason is not None:
                    skipped.append(SkippedOperation(source, operation, reason))
                else:
                    candidates.append(
                        CandidateOperation(source, op_index, operation, len(candidates))
                    )
        return RuleEvaluation(tuple(results), tuple(candidates), tuple(skipped))
