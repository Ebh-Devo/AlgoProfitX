import asyncio
import hashlib
import ipaddress
import math
import time
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol

from fastapi import HTTPException, Request, status

from app.core.metrics import metrics
from app.core.observability import log_event


@dataclass(frozen=True)
class RateLimitRule:
    scope: str
    key: str
    limit: int
    window_seconds: int


@dataclass
class _Window:
    count: int
    expires_at: float


class RateLimitStore(Protocol):
    async def consume(self, rules: Sequence[RateLimitRule]) -> int | None:
        """Consume all rules atomically, returning retry seconds when rejected."""

    async def clear(self) -> None:
        """Clear process-local state, primarily for deterministic tests."""


class InMemoryRateLimitStore:
    """Async-safe, process-local fixed-window storage."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._windows: dict[tuple[str, str], _Window] = {}
        self._lock = asyncio.Lock()

    async def consume(self, rules: Sequence[RateLimitRule]) -> int | None:
        now = self._clock()
        async with self._lock:
            expired_keys = [
                bucket_key
                for bucket_key, window in self._windows.items()
                if now >= window.expires_at
            ]
            for bucket_key in expired_keys:
                self._windows.pop(bucket_key, None)

            active: list[tuple[RateLimitRule, _Window]] = []
            for rule in rules:
                bucket_key = (rule.scope, rule.key)
                window = self._windows.get(bucket_key)
                if window is None or now >= window.expires_at:
                    window = _Window(count=0, expires_at=now + rule.window_seconds)
                    self._windows[bucket_key] = window
                active.append((rule, window))

            rejected = [
                window.expires_at - now
                for rule, window in active
                if window.count >= rule.limit
            ]
            if rejected:
                return max(1, math.ceil(max(rejected)))

            for _, window in active:
                window.count += 1
            return None

    async def clear(self) -> None:
        async with self._lock:
            self._windows.clear()


class ConcurrencyLimiter:
    """Async-safe, process-local concurrency counters keyed by user."""

    def __init__(self) -> None:
        self._active: dict[tuple[str, str], int] = {}
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def slot(
        self, scope: str, key: str, maximum: int
    ) -> AsyncIterator[None]:
        bucket_key = (scope, key)
        async with self._lock:
            active = self._active.get(bucket_key, 0)
            if active >= maximum:
                _record_event("concurrency_limit_exceeded", scope, key)
                metrics.increment(
                    "concurrency_limit.violations", tags={"scope": scope}
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error_code": "concurrency_limit_exceeded",
                        "message": "Too many concurrent operations",
                    },
                    headers={"Retry-After": "1"},
                )
            self._active[bucket_key] = active + 1

        try:
            yield
        finally:
            async with self._lock:
                remaining = self._active.get(bucket_key, 1) - 1
                if remaining > 0:
                    self._active[bucket_key] = remaining
                else:
                    self._active.pop(bucket_key, None)

    async def clear(self) -> None:
        async with self._lock:
            self._active.clear()


def normalized_client_ip(request: Request) -> str:
    """Use only the ASGI peer address; forwarded headers are intentionally ignored."""
    host = request.client.host if request.client else "unknown"
    try:
        return ipaddress.ip_address(host).compressed
    except ValueError:
        return host.casefold()


def normalized_account_key(email: str) -> str:
    normalized = email.strip().casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _record_event(event: str, scope: str, key: str) -> None:
    fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
    log_event(
        event,
        level=30,
        logger_name="app.security",
        scope=scope,
        key_fingerprint=fingerprint,
    )


def record_authentication_failure(client_key: str) -> None:
    _record_event("authentication_failed", "login", client_key)


class AbuseController:
    def __init__(
        self,
        store: RateLimitStore | None = None,
        concurrency: ConcurrencyLimiter | None = None,
    ) -> None:
        self.store = store or InMemoryRateLimitStore()
        self.concurrency = concurrency or ConcurrencyLimiter()

    async def enforce(self, rules: Sequence[RateLimitRule], enabled: bool) -> None:
        if not enabled:
            return
        retry_after = await self.store.consume(rules)
        if retry_after is None:
            return
        first = rules[0]
        _record_event("rate_limit_exceeded", first.scope, first.key)
        metrics.increment("rate_limit.violations", tags={"scope": first.scope})
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error_code": "rate_limit_exceeded",
                "message": "Too many requests",
            },
            headers={"Retry-After": str(retry_after)},
        )

    async def clear(self) -> None:
        await self.store.clear()
        await self.concurrency.clear()


abuse_controller = AbuseController()
