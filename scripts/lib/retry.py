"""Retry + circuit breaker primitives for every integration tool.

Zero external dependencies. Thread-safe. JSON-serializable state so circuit
breaker state survives process restarts (when persistence path is given).

Usage:

    from lib.retry import retry, circuit_breaker, RetryConfig, CircuitBreakerConfig

    # Simple retry — exponential backoff + jitter, default config
    @retry()
    def fetch_user(uid: str) -> dict:
        return httpx.get(f"/users/{uid}").raise_for_status().json()

    # Retry + circuit breaker. After 5 consecutive failures the breaker opens
    # for 60s; calls fail immediately. After 60s one test call is allowed; on
    # success the breaker closes, on failure it re-opens for another 60s.
    @retry(RetryConfig(max_retries=5, base_delay=0.5))
    @circuit_breaker("supabase")
    def db_query(sql: str) -> list[dict]:
        return supabase.rpc("exec", {"sql": sql}).execute().data

The circuit breaker is named so multiple decorated functions can share the
same breaker (e.g., every Supabase call shares `circuit_breaker("supabase")`).
Breaker state lives in a module-level registry; pass `persistence_path` on the
config to mirror state to disk between process restarts.

Logging integrates with structured_log when available, falls back to stderr.
"""

from __future__ import annotations

import json
import random
import sys
import threading
import time
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import Any, Callable, TypeVar

T = TypeVar("T")


_DEFAULT_RETRYABLE: tuple[type[BaseException], ...] = (
    ConnectionError,
    TimeoutError,
    OSError,
)


@dataclass(frozen=True)
class RetryConfig:
    """Retry policy. All times in seconds.

    The delay schedule is:
        delay_n = min(max_delay, base_delay * (exponential_base ** n))
        if jitter: delay_n *= random.uniform(0.5, 1.5)
    """
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_exceptions: tuple[type[BaseException], ...] = _DEFAULT_RETRYABLE

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if self.base_delay <= 0:
            raise ValueError("base_delay must be > 0")
        if self.max_delay < self.base_delay:
            raise ValueError("max_delay must be >= base_delay")
        if self.exponential_base < 1:
            raise ValueError("exponential_base must be >= 1")

    def compute_delay(self, attempt: int, rng: random.Random | None = None) -> float:
        """Delay (seconds) before attempt N (0-indexed). 0 for first call."""
        if attempt <= 0:
            return 0.0
        raw = self.base_delay * (self.exponential_base ** (attempt - 1))
        delay = min(self.max_delay, raw)
        if self.jitter:
            r = rng or random
            delay *= r.uniform(0.5, 1.5)
        return delay


@dataclass(frozen=True)
class CircuitBreakerConfig:
    """Circuit-breaker policy. `persistence_path` is optional — when set, the
    breaker mirrors its state (closed/open/half-open + counters) to that JSON
    file so restarts pick up the same posture."""
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    persistence_path: Path | None = None

    def __post_init__(self) -> None:
        if self.failure_threshold <= 0:
            raise ValueError("failure_threshold must be > 0")
        if self.recovery_timeout <= 0:
            raise ValueError("recovery_timeout must be > 0")


@dataclass
class _BreakerState:
    state: str = "closed"  # closed | open | half-open
    failures: int = 0
    opened_at: float = 0.0
    last_test_call_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "failures": self.failures,
            "opened_at": self.opened_at,
            "last_test_call_at": self.last_test_call_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "_BreakerState":
        return cls(
            state=str(data.get("state", "closed")),
            failures=int(data.get("failures", 0)),
            opened_at=float(data.get("opened_at", 0.0)),
            last_test_call_at=float(data.get("last_test_call_at", 0.0)),
        )


class CircuitBreakerOpen(RuntimeError):
    """Raised when the breaker is open and the call short-circuits."""


class _Breaker:
    """Thread-safe state machine. One instance per breaker name."""

    def __init__(self, name: str, config: CircuitBreakerConfig) -> None:
        self.name = name
        self.config = config
        self._lock = threading.Lock()
        self._state = _BreakerState()
        if config.persistence_path and config.persistence_path.exists():
            try:
                self._state = _BreakerState.from_dict(
                    json.loads(config.persistence_path.read_text(encoding="utf-8"))
                )
            except (OSError, ValueError, json.JSONDecodeError):
                pass

    def _persist(self) -> None:
        if not self.config.persistence_path:
            return
        try:
            self.config.persistence_path.parent.mkdir(parents=True, exist_ok=True)
            self.config.persistence_path.write_text(
                json.dumps(self._state.to_dict()), encoding="utf-8"
            )
        except OSError:
            pass

    def before_call(self) -> None:
        """Raise CircuitBreakerOpen if call should be short-circuited."""
        now = time.monotonic()
        with self._lock:
            if self._state.state == "open":
                if now - self._state.opened_at >= self.config.recovery_timeout:
                    self._state.state = "half-open"
                    self._state.last_test_call_at = now
                    self._persist()
                else:
                    raise CircuitBreakerOpen(
                        f"breaker '{self.name}' open "
                        f"({self._state.failures} consecutive failures; "
                        f"retry in {self.config.recovery_timeout - (now - self._state.opened_at):.1f}s)"
                    )

    def on_success(self) -> None:
        with self._lock:
            if self._state.state in ("half-open", "open"):
                self._state.state = "closed"
                self._state.failures = 0
                self._persist()
            elif self._state.failures:
                self._state.failures = 0
                self._persist()

    def on_failure(self) -> None:
        now = time.monotonic()
        with self._lock:
            self._state.failures += 1
            if self._state.state == "half-open":
                self._state.state = "open"
                self._state.opened_at = now
            elif self._state.failures >= self.config.failure_threshold:
                self._state.state = "open"
                self._state.opened_at = now
            self._persist()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._state.to_dict()

    def reset(self) -> None:
        with self._lock:
            self._state = _BreakerState()
            self._persist()


_BREAKERS: dict[str, _Breaker] = {}
_BREAKER_REGISTRY_LOCK = threading.Lock()


def _get_or_create_breaker(name: str, config: CircuitBreakerConfig) -> _Breaker:
    with _BREAKER_REGISTRY_LOCK:
        b = _BREAKERS.get(name)
        if b is None:
            b = _Breaker(name, config)
            _BREAKERS[name] = b
        return b


def reset_all_breakers() -> None:
    """Test hook: clear every registered breaker."""
    with _BREAKER_REGISTRY_LOCK:
        for b in _BREAKERS.values():
            b.reset()
        _BREAKERS.clear()


def get_breaker_state(name: str) -> dict[str, Any] | None:
    """Inspect a named breaker. Returns None if unknown."""
    b = _BREAKERS.get(name)
    return b.snapshot() if b else None


def _log_retry(name: str, attempt: int, exc: BaseException, delay: float) -> None:
    """Emit a structured-log line if structured_log is wired up, else stderr."""
    try:
        from lib.structured_log import get_logger  # type: ignore
        log = get_logger("retry")
        log.warn(
            "retry_after_failure",
            target=name,
            attempt=attempt,
            error_type=type(exc).__name__,
            error=str(exc)[:200],
            sleep_seconds=round(delay, 3),
        )
        return
    except Exception:
        pass
    print(
        f"[retry] {name} attempt={attempt} error={type(exc).__name__}: "
        f"{str(exc)[:120]} sleep={delay:.2f}s",
        file=sys.stderr,
    )


def retry(config: RetryConfig | None = None, *, name: str | None = None) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator: retry on transient failures with exponential backoff + jitter.

    Example:
        @retry(RetryConfig(max_retries=5))
        def fetch(): ...
    """
    cfg = config or RetryConfig()

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        fn_name = name or getattr(fn, "__qualname__", fn.__name__)

        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exc: BaseException | None = None
            for attempt in range(cfg.max_retries + 1):
                try:
                    return fn(*args, **kwargs)
                except cfg.retryable_exceptions as exc:
                    last_exc = exc
                    if attempt >= cfg.max_retries:
                        break
                    delay = cfg.compute_delay(attempt + 1)
                    _log_retry(fn_name, attempt + 1, exc, delay)
                    time.sleep(delay)
            assert last_exc is not None
            raise last_exc

        return wrapper

    return decorator


def circuit_breaker(
    name: str,
    config: CircuitBreakerConfig | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator: short-circuit calls when the named breaker is open.

    Multiple decorated functions can share a breaker name to fan a single
    failure pattern (one upstream service) across many call sites.

    Raises CircuitBreakerOpen when the breaker rejects a call.
    """
    cfg = config or CircuitBreakerConfig()
    breaker = _get_or_create_breaker(name, cfg)

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            breaker.before_call()
            try:
                result = fn(*args, **kwargs)
            except BaseException:
                breaker.on_failure()
                raise
            breaker.on_success()
            return result

        return wrapper

    return decorator
