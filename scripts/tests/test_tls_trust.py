r"""Regression tests for lib/tls_trust.py — the 2026-07-29 SSLKEYLOGFILE outage.

The bug: AVG sets SSLKEYLOGFILE to a kernel device handle
(\\.\avgMonFltProxy\<hex>). CPython's ssl.create_default_context() assigns it to
context.keylog_filename, which opens the path — and a stale handle raises
PermissionError from inside context construction. PM2 froze one such handle into
bravo-scheduler's env, so every HTTPS-using cron child died for 25h, including
notify.py (which is why nothing alerted).

No network. Pure env manipulation.
"""
from __future__ import annotations

import os
import ssl
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.tls_trust import (  # noqa: E402
    ensure_os_trust,
    neutralize_keylog,
    tls_diagnostics,
)

# The literal value pulled from the live poisoned bravo-scheduler environment.
AVG_HANDLE = r"\\.\avgMonFltProxy\FFFF80838C28E160"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Every test starts from a known-clean TLS env."""
    monkeypatch.delenv("SSLKEYLOGFILE", raising=False)
    monkeypatch.delenv("EMPIRE_ALLOW_SSLKEYLOG", raising=False)
    yield


# ── neutralize_keylog ────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "value,should_strip,why",
    [
        (AVG_HANDLE, True, "live AVG device handle from the outage"),
        (r"\\.\pipe\something", True, "any \\\\.\\ device path"),
        (r"\\?\C:\nope\keys.log", True, r"\\?\ extended-length device prefix"),
        (r"C:\definitely\not\a\real\dir\keys.log", True, "parent dir does not exist"),
        ("", False, "empty string is already falsy to ssl.py — nothing to do"),
    ],
)
def test_hostile_values_are_stripped(monkeypatch, value, should_strip, why):
    monkeypatch.setenv("SSLKEYLOGFILE", value)
    removed = neutralize_keylog()
    assert removed is should_strip, why
    if should_strip:
        assert "SSLKEYLOGFILE" not in os.environ, why


def test_real_writable_path_is_kept(monkeypatch, tmp_path):
    """A genuine operator-supplied keylog path is legitimate — don't clobber it."""
    keylog = tmp_path / "keys.log"
    monkeypatch.setenv("SSLKEYLOGFILE", str(keylog))
    assert neutralize_keylog() is False
    assert os.environ["SSLKEYLOGFILE"] == str(keylog)


def test_escape_hatch_preserves_hostile_value(monkeypatch):
    """EMPIRE_ALLOW_SSLKEYLOG=1 means the operator knows what they're doing."""
    monkeypatch.setenv("SSLKEYLOGFILE", AVG_HANDLE)
    monkeypatch.setenv("EMPIRE_ALLOW_SSLKEYLOG", "1")
    assert neutralize_keylog() is False
    assert os.environ["SSLKEYLOGFILE"] == AVG_HANDLE


def test_unset_is_a_noop():
    assert neutralize_keylog() is False
    assert "SSLKEYLOGFILE" not in os.environ


def test_idempotent(monkeypatch):
    monkeypatch.setenv("SSLKEYLOGFILE", AVG_HANDLE)
    assert neutralize_keylog() is True
    assert neutralize_keylog() is False  # already gone
    assert "SSLKEYLOGFILE" not in os.environ


# ── the actual outage reproduction ───────────────────────────────────────────

def test_create_default_context_fails_with_poisoned_env(monkeypatch):
    """Guard the guard: prove the failure mode is real, so this suite fails
    loudly if a future CPython stops reading SSLKEYLOGFILE and these tests
    silently start passing for the wrong reason."""
    monkeypatch.setenv("SSLKEYLOGFILE", AVG_HANDLE)
    with pytest.raises(OSError):
        ssl.create_default_context()


def test_ensure_os_trust_unbreaks_context_creation(monkeypatch):
    """The regression that matters: after ensure_os_trust(), an SSL context can
    be built even though the process inherited AVG's stale handle."""
    monkeypatch.setenv("SSLKEYLOGFILE", AVG_HANDLE)
    ensure_os_trust()
    ctx = ssl.create_default_context()
    assert ctx is not None


def test_ensure_os_trust_unbreaks_urllib3(monkeypatch):
    """notify.py reaches TLS through requests -> urllib3, not ssl directly.
    That is the path that silenced every cron alert, so it gets its own test."""
    monkeypatch.setenv("SSLKEYLOGFILE", AVG_HANDLE)
    ensure_os_trust()
    from urllib3.util.ssl_ import create_urllib3_context

    assert create_urllib3_context() is not None


# ── diagnostics ──────────────────────────────────────────────────────────────

def test_diagnostics_reports_poisoned_state(monkeypatch):
    monkeypatch.setenv("SSLKEYLOGFILE", AVG_HANDLE)
    d = tls_diagnostics()
    assert d["keylog_present"] is True
    assert d["keylog_usable"] is False
    assert d["keylog_allowed"] is False


def test_diagnostics_reports_clean_state():
    d = tls_diagnostics()
    assert d["keylog_present"] is False
    assert d["keylog_usable"] is None
