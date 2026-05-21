"""Token-bucket rate limiter for API endpoints.

Pure in-memory, thread-safe, zero external deps. Limits reset on process
restart — that's a feature, not a bug, for API rate limits (production
rate-limit state should live in Redis or similar; this is the local guard
against abuse and accidental loops).

Algorithm: classic token bucket.
  - bucket holds up to `burst` tokens
  - bucket refills at `rate` tokens per second
  - each allowed call consumes one token
  - if no tokens available → reject, return retry_after seconds

Usage:
    from lib.rate_limiter import RateLimiter
    limiter = RateLimiter(rate=10, burst=20)  # 10 req/s steady, burst to 20
    decision = limiter.check(client_id="user-42")
    if not decision.allowed:
        return {"error": "rate_limited", "retry_after": decision.retry_after}

    # Inspect for response headers
    print(decision.limit, decision.remaining, decision.reset_seconds)

Standard rate-limit headers (RFC draft):
    X-RateLimit-Limit:     decision.limit
    X-RateLimit-Remaining: decision.remaining
    X-RateLimit-Reset:     decision.reset_seconds
    Retry-After:           decision.retry_after  (only when not allowed)
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: float       # rate (tokens per second) — exposed as the steady-state cap
    remaining: float   # tokens left in the bucket after this call
    reset_seconds: float  # seconds until bucket is fully refilled
    retry_after: float    # 0 if allowed; seconds until one token frees up otherwise

    def as_headers(self) -> dict[str, str]:
        headers = {
            "X-RateLimit-Limit": str(int(self.limit)),
            "X-RateLimit-Remaining": str(int(self.remaining)),
            "X-RateLimit-Reset": str(int(self.reset_seconds)),
        }
        if not self.allowed:
            headers["Retry-After"] = str(int(max(1, round(self.retry_after))))
        return headers


@dataclass
class _Bucket:
    tokens: float
    last_refill: float


class RateLimiter:
    """Per-client token bucket. Thread-safe."""

    def __init__(self, rate: float, burst: int, *, name: str = "default") -> None:
        if rate <= 0:
            raise ValueError("rate must be > 0")
        if burst < 1:
            raise ValueError("burst must be >= 1")
        self.rate = float(rate)
        self.burst = int(burst)
        self.name = name
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def _refill(self, bucket: _Bucket, now: float) -> None:
        elapsed = now - bucket.last_refill
        if elapsed <= 0:
            return
        bucket.tokens = min(self.burst, bucket.tokens + elapsed * self.rate)
        bucket.last_refill = now

    def check(self, client_id: str = "default") -> RateLimitDecision:
        """Consume one token if available. Returns decision for headers."""
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(client_id)
            if bucket is None:
                bucket = _Bucket(tokens=float(self.burst), last_refill=now)
                self._buckets[client_id] = bucket

            self._refill(bucket, now)

            if bucket.tokens >= 1:
                bucket.tokens -= 1
                allowed = True
                retry_after = 0.0
            else:
                allowed = False
                # Seconds until ONE token is available
                retry_after = (1.0 - bucket.tokens) / self.rate

            # Seconds to refill from current state back to burst
            reset_seconds = (self.burst - bucket.tokens) / self.rate
            return RateLimitDecision(
                allowed=allowed,
                limit=self.rate,
                remaining=max(0.0, bucket.tokens),
                reset_seconds=reset_seconds,
                retry_after=retry_after,
            )

    def allow(self, client_id: str = "default") -> bool:
        """Convenience: boolean form of check()."""
        return self.check(client_id).allowed

    def reset(self, client_id: str | None = None) -> None:
        """Clear one client's bucket (or all of them)."""
        with self._lock:
            if client_id is None:
                self._buckets.clear()
            else:
                self._buckets.pop(client_id, None)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "name": self.name,
                "rate_per_sec": self.rate,
                "burst": self.burst,
                "active_clients": len(self._buckets),
            }
