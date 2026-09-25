"""Admission control for AI Studio requests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock


class RateLimitExceeded(RuntimeError):
    def __init__(self, retry_after_seconds: float) -> None:
        self.retry_after_seconds = max(0.001, retry_after_seconds)
        super().__init__("AI Studio rate limit exceeded")


@dataclass(frozen=True, slots=True)
class BucketPolicy:
    capacity: int = 60
    refill_per_second: float = 1.0

    def __post_init__(self) -> None:
        if self.capacity < 1 or self.refill_per_second <= 0:
            raise ValueError("invalid token bucket policy")


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated_at: float


class TokenBucketLimiter:
    """Thread-safe token bucket keyed by a bounded caller scope."""

    def __init__(
        self, policy: BucketPolicy | None = None, *, clock: Callable[[], float] | None = None
    ) -> None:
        self.policy = policy or BucketPolicy()
        self._clock = clock or __import__("time").monotonic
        self._buckets: dict[str, _Bucket] = {}
        self._lock = Lock()

    def allow(self, key: str, *, cost: int = 1) -> None:
        if not key or len(key) > 256 or cost < 1 or cost > self.policy.capacity:
            raise ValueError("invalid limiter key or cost")
        now = self._clock()
        with self._lock:
            bucket = self._buckets.setdefault(key, _Bucket(self.policy.capacity, now))
            elapsed = max(0.0, now - bucket.updated_at)
            bucket.tokens = min(
                float(self.policy.capacity), bucket.tokens + elapsed * self.policy.refill_per_second
            )
            bucket.updated_at = now
            if bucket.tokens < cost:
                missing = cost - bucket.tokens
                raise RateLimitExceeded(missing / self.policy.refill_per_second)
            bucket.tokens -= cost

    def clear(self, key: str) -> None:
        with self._lock:
            self._buckets.pop(key, None)
