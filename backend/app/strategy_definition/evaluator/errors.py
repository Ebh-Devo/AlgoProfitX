"""Errors raised by the condition evaluator.

An undefined operand (warm-up, missing candle) is an expected data state and yields
``UNKNOWN``. Everything here is an invalid definition or evaluation request and is never
converted into a result.
"""


class EvaluatorError(Exception):
    """Base class for evaluator failures."""


class UnsupportedConstructError(EvaluatorError):
    """A condition/operand kind or operator the evaluator does not support."""


class MissingContextValueError(EvaluatorError):
    """The context was never given a series the definition requires."""


class InvalidEvaluationRequestError(EvaluatorError):
    """Malformed evaluator input, e.g. a future offset or a non-Decimal value."""
