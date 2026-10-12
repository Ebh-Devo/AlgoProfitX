import contextvars
import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any


request_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)

SENSITIVE_KEYS = {
    "authorization", "cookie", "set-cookie", "password", "secret_key",
    "database_url", "db_password", "refresh_token", "refresh_token_hash",
    "csrf", "csrf_token", "api_key", "pin", "totp_secret", "access_token",
    "feed_token", "vendor_jwt",
}
REDACTED = "[REDACTED]"
BEARER_PATTERN = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")
URL_CREDENTIAL_PATTERN = re.compile(r"(?i)(postgres(?:ql)?(?:\+asyncpg)?://[^:\s/]+:)[^@\s]+(@)")
# "name=value" / "name: value" / '"name": "value"' where the name looks secret-bearing. Best effort: it
# cannot recognise a secret that appears in free text without such a label.
SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"""(?i)((?:pass(?:word|wd)?|secret|token|api[_-]?key|credential|authorization|cookie)[\w-]*["']?\s*[:=]\s*["']?)(?!\[REDACTED\])[^\s"',;&}]+"""
)


def _sensitive_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return normalized in SENSITIVE_KEYS or any(
        marker in normalized for marker in ("password", "secret", "token", "cookie")
    )


def redact(value: Any, key: str | None = None) -> Any:
    if key and _sensitive_key(key):
        return REDACTED
    if isinstance(value, dict):
        return {str(item_key): redact(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        sanitized = BEARER_PATTERN.sub(f"Bearer {REDACTED}", value)
        sanitized = URL_CREDENTIAL_PATTERN.sub(r"\1[REDACTED]\2", sanitized)
        return SECRET_ASSIGNMENT_PATTERN.sub(rf"\1{REDACTED}", sanitized)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": getattr(record, "event", record.getMessage()),
        }
        request_id = getattr(record, "request_id", None) or request_id_context.get()
        if request_id:
            payload["request_id"] = request_id
        payload.update(redact(getattr(record, "fields", {})))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(redact(payload), separators=(",", ":"), default=str)


class ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event = getattr(record, "event", record.getMessage())
        fields = redact(getattr(record, "fields", {}))
        request_id = getattr(record, "request_id", None) or request_id_context.get()
        suffix = " ".join(f"{key}={value}" for key, value in fields.items())
        prefix = f"[{record.levelname}] {event}"
        if request_id:
            prefix += f" request_id={request_id}"
        return f"{prefix} {suffix}".rstrip()


def configure_logging(level: str, log_format: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if log_format == "json" else ConsoleFormatter())
    logger = logging.getLogger("app")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False


def log_event(
    event: str,
    *,
    level: int = logging.INFO,
    logger_name: str = "app",
    exc_info: bool = False,
    **fields: Any,
) -> None:
    logging.getLogger(logger_name).log(
        level,
        event,
        extra={"event": event, "fields": redact(fields)},
        exc_info=exc_info,
    )
