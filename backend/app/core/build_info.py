"""Non-secret build identity, baked into the image at build time.

Only two build arguments are ever read: ``APP_SOURCE_SHA`` (the source commit) and
``APP_BUILD_RUN_ID`` (the CI build run that produced the image). Each value is validated against a
strict format and replaced by ``unknown`` otherwise, so a mis-set variable can never put arbitrary
text (or anything else from the environment) into a response.
"""

import os
import re

UNKNOWN = "unknown"
_SHA = re.compile(r"[0-9a-f]{40}")
_RUN_ID = re.compile(r"[0-9]{1,20}")


def _validated(name: str, pattern: re.Pattern[str]) -> str:
    value = os.getenv(name, "")
    return value if pattern.fullmatch(value) else UNKNOWN


def build_identity() -> dict[str, str]:
    """The approved identity fields, nothing else."""
    return {
        "sha": _validated("APP_SOURCE_SHA", _SHA),
        "build_run_id": _validated("APP_BUILD_RUN_ID", _RUN_ID),
    }
