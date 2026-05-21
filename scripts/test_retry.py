"""Tests for scripts/lib/retry.py — retry + circuit breaker."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from lib.retry import (
    CircuitBreakerConfig,
    CircuitBreakerOpen,
    RetryConfig,
    _Breaker,
    circuit_breaker,
    get_breaker_state,
    reset_all_breakers,
    retry,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_all_breakers()
    yield
    reset_all_breakers()


# ── RetryConfig ───────────────────────────────────────────────────────────

def test_retry_config_validation_negative_retries():
    with pytest.raises(ValueError):
        RetryConfig(max_retries=-1)


def test_retry_config_validation_zero_delay():
    with pytest.raises(ValueError):
        RetryConfig(base_delay=0)


def test_retry_config_compute_delay_no_jitter():
    cfg = RetryConfig(base_delay=1.0, exponential_base=2.0, jitter=False)
    assert cfg.compute_delay(0) == 0.0
    assert cfg.compute_delay(1) == 1.0
    assert cfg.compute_delay(2) == 2.0
    assert cfg.compute_delay(3) == 4.0


def test_retry_config_compute_delay_clamped_to_max():
    cfg = RetryConfig(base_delay=10.0, max_delay=15.0, exponential_base=2.0, jitter=False)
    assert cfg.compute_delay(1) == 10.0
    assert cfg.compute_delay(2) == 15.0  # 20 clamped to 15
    assert cfg.compute_delay(5) == 15.0


def test_retry_config_jitter_adds_randomness():
    cfg = RetryConfig(base_delay=10.0, max_delay=100.0, exponential_base=1.0, jitter=True)
    samples = [cfg.compute_delay(1) for _ in range(200)]
    # All within [5, 15] (0.5x - 1.5x of base)
    assert all(5.0 <= s <= 15.0 for s in samples)
    # Statistically distinct values
    assert len(set(round(s, 4) for s in samples)) > 100


# ── @retry ────────────────────────────────────────────────────────────────

def test_retry_success_on_first_try():
    calls = []

    @retry(RetryConfig(max_retries=3, base_delay=0.001, jitter=False))
    def fn():
        calls.append(1)
        return "ok"

    assert fn() == "ok"
    assert len(calls) == 1


def test_retry_recovers_after_transient_failure():
    calls = []

    @retry(RetryConfig(max_retries=3, base_delay=0.001, jitter=False))
    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("boom")
        return "ok"

    assert fn() == "ok"
    assert len(calls) == 3


def test_retry_max_retries_exceeded_raises_final_error():
    calls = []

    @retry(RetryConfig(max_retries=2, base_delay=0.001, jitter=False))
    def fn():
        calls.append(1)
        raise ConnectionError("persistent")

    with pytest.raises(ConnectionError, match="persistent"):
        fn()
    assert len(calls) == 3  # initial + 2 retries


def test_retry_skips_non_retryable_exceptions():
    calls = []

    @retry(RetryConfig(max_retries=3, base_delay=0.001, jitter=False))
    def fn():
        calls.append(1)
        raise ValueError("not retryable")

    with pytest.raises(ValueError):
        fn()
    assert len(calls) == 1


def test_retry_decorator_works_on_class_method():
    class Service:
        def __init__(self):
            self.calls = 0

        @retry(RetryConfig(max_retries=2, base_delay=0.001, jitter=False))
        def call(self):
            self.calls += 1
            if self.calls < 2:
                raise ConnectionError("transient")
            return "done"

    svc = Service()
    assert svc.call() == "done"
    assert svc.calls == 2


# ── CircuitBreaker state machine ──────────────────────────────────────────

def test_breaker_config_validation():
    with pytest.raises(ValueError):
        CircuitBreakerConfig(failure_threshold=0)
    with pytest.raises(ValueError):
        CircuitBreakerConfig(recovery_timeout=-1)


def test_breaker_closes_after_threshold_failures():
    cfg = CircuitBreakerConfig(failure_threshold=3, recovery_timeout=60)

    @circuit_breaker("test_close_open", cfg)
    def fn(boom: bool):
        if boom:
            raise ConnectionError("nope")
        return "ok"

    # 3 failures triggers open
    for _ in range(3):
        with pytest.raises(ConnectionError):
            fn(True)
    state = get_breaker_state("test_close_open")
    assert state is not None
    assert state["state"] == "open"

    # Next call short-circuits
    with pytest.raises(CircuitBreakerOpen):
        fn(False)


def test_breaker_half_open_after_recovery_timeout():
    cfg = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.05)

    @circuit_breaker("test_half_open", cfg)
    def fn(boom: bool):
        if boom:
            raise ConnectionError("nope")
        return "ok"

    for _ in range(2):
        with pytest.raises(ConnectionError):
            fn(True)
    assert get_breaker_state("test_half_open")["state"] == "open"

    time.sleep(0.06)  # exceed recovery timeout

    # Test call allowed; success closes the breaker
    assert fn(False) == "ok"
    assert get_breaker_state("test_half_open")["state"] == "closed"


def test_breaker_half_open_failure_reopens():
    cfg = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.05)

    @circuit_breaker("test_half_reopen", cfg)
    def fn(boom: bool):
        if boom:
            raise ConnectionError("nope")
        return "ok"

    for _ in range(2):
        with pytest.raises(ConnectionError):
            fn(True)
    time.sleep(0.06)

    # Test call fails — breaker re-opens
    with pytest.raises(ConnectionError):
        fn(True)
    assert get_breaker_state("test_half_reopen")["state"] == "open"


def test_breaker_state_persists_to_disk(tmp_path):
    persist = tmp_path / "breaker.json"
    cfg = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=60, persistence_path=persist)

    @circuit_breaker("test_persist", cfg)
    def fn():
        raise ConnectionError("nope")

    for _ in range(2):
        with pytest.raises(ConnectionError):
            fn()

    assert persist.exists()
    state_on_disk = __import__("json").loads(persist.read_text())
    assert state_on_disk["state"] == "open"
    assert state_on_disk["failures"] == 2


def test_breaker_thread_safety_no_corruption():
    cfg = CircuitBreakerConfig(failure_threshold=50, recovery_timeout=60)

    @circuit_breaker("test_threadsafe", cfg)
    def fn(boom):
        if boom:
            raise ConnectionError("nope")
        return "ok"

    def worker():
        for i in range(20):
            try:
                fn(i % 3 == 0)
            except (ConnectionError, CircuitBreakerOpen):
                pass

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Final state should still be valid
    state = get_breaker_state("test_threadsafe")
    assert state["state"] in ("closed", "open", "half-open")
    assert state["failures"] >= 0


def test_retry_plus_breaker_integration():
    """Real-world stack: @retry on top of @circuit_breaker.

    The breaker opens after 3 failures. The retry decorator should hit the
    breaker, NOT keep retrying past the breaker's open state.
    """
    cfg_breaker = CircuitBreakerConfig(failure_threshold=3, recovery_timeout=60)
    cfg_retry = RetryConfig(max_retries=10, base_delay=0.001, jitter=False,
                            retryable_exceptions=(ConnectionError, CircuitBreakerOpen))

    calls = []

    @retry(cfg_retry)
    @circuit_breaker("test_integration", cfg_breaker)
    def fn():
        calls.append(1)
        raise ConnectionError("persistent")

    with pytest.raises((ConnectionError, CircuitBreakerOpen)):
        fn()

    # Real underlying calls capped at threshold (3) — even though retry would
    # otherwise hammer 11 times.
    assert len(calls) == 3
    assert get_breaker_state("test_integration")["state"] == "open"
