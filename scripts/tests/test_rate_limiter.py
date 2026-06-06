"""Tests for scripts/lib/rate_limiter.py."""

from __future__ import annotations

import threading
import time

import pytest

from lib.rate_limiter import RateLimiter


def test_config_validation():
    with pytest.raises(ValueError):
        RateLimiter(rate=0, burst=10)
    with pytest.raises(ValueError):
        RateLimiter(rate=-1, burst=10)
    with pytest.raises(ValueError):
        RateLimiter(rate=10, burst=0)


def test_burst_allows_initial_rapid_calls():
    limiter = RateLimiter(rate=5, burst=10)
    decisions = [limiter.check("c1") for _ in range(10)]
    assert all(d.allowed for d in decisions)
    # 11th call rejected (bucket empty)
    assert not limiter.check("c1").allowed


def test_separate_clients_get_separate_buckets():
    limiter = RateLimiter(rate=1, burst=3)
    # Drain client A
    for _ in range(3):
        assert limiter.check("a").allowed
    assert not limiter.check("a").allowed
    # Client B is unaffected
    for _ in range(3):
        assert limiter.check("b").allowed
    assert not limiter.check("b").allowed


def test_tokens_refill_over_time():
    limiter = RateLimiter(rate=100, burst=2)  # very fast refill for test
    assert limiter.check("c1").allowed
    assert limiter.check("c1").allowed
    assert not limiter.check("c1").allowed
    time.sleep(0.05)  # 100/s × 50ms = 5 tokens, capped at burst=2
    assert limiter.check("c1").allowed


def test_decision_headers_include_required_fields():
    limiter = RateLimiter(rate=10, burst=5)
    decision = limiter.check("c1")
    headers = decision.as_headers()
    assert "X-RateLimit-Limit" in headers
    assert "X-RateLimit-Remaining" in headers
    assert "X-RateLimit-Reset" in headers
    # Drain + check Retry-After only appears on reject
    for _ in range(4):
        limiter.check("c1")
    rejected = limiter.check("c1")
    assert not rejected.allowed
    assert "Retry-After" in rejected.as_headers()


def test_retry_after_decreases_as_time_passes():
    limiter = RateLimiter(rate=10, burst=1)
    assert limiter.check("c1").allowed
    first_reject = limiter.check("c1")
    assert not first_reject.allowed
    first_retry = first_reject.retry_after
    time.sleep(0.02)
    second_reject = limiter.check("c1")
    # As time elapses, retry_after shrinks (tokens being refilled)
    assert second_reject.retry_after < first_retry


def test_reset_one_client():
    limiter = RateLimiter(rate=1, burst=2)
    limiter.check("a"); limiter.check("a")
    assert not limiter.check("a").allowed
    limiter.reset("a")
    assert limiter.check("a").allowed
    # Other clients untouched
    limiter.check("b")  # warms bucket b


def test_reset_all_clients():
    limiter = RateLimiter(rate=1, burst=2)
    limiter.check("a"); limiter.check("a")
    limiter.check("b"); limiter.check("b")
    limiter.reset()
    assert limiter.check("a").allowed
    assert limiter.check("b").allowed


def test_thread_safety_no_overshoot():
    """Concurrent callers must NEVER drain past `burst` total tokens in a
    very short window."""
    limiter = RateLimiter(rate=0.01, burst=50)  # essentially no refill during test
    accepted = 0
    lock = threading.Lock()

    def worker():
        nonlocal accepted
        for _ in range(20):
            if limiter.check("shared").allowed:
                with lock:
                    accepted += 1

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 8 threads × 20 attempts = 160 attempts; only `burst=50` can be accepted
    assert accepted == 50


def test_snapshot_reports_active_clients():
    limiter = RateLimiter(rate=1, burst=1, name="api")
    limiter.check("alice")
    limiter.check("bob")
    snap = limiter.snapshot()
    assert snap["name"] == "api"
    assert snap["active_clients"] == 2
