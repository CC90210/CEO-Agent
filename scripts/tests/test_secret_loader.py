"""Tests for scripts/lib/secret_loader.py — the audited .env.agents loader.

Covers two things that had no test at all despite 248 call sites depending on
this module: the shape of the audit record, and the refusals that make the
loader safe to expose to LLM-written code.

The audit-record tests exist because of a real incident. Until 2026-08-28 the
logging line read:

    _log_access(caller, requested or _CACHE.keys())

so every caller that passed no `required=[...]` list — 239 of the 248 — recorded
all 204 environment key names, about 5.2 KB per record. state/secret_access.log
reached 43 MB in a day, outrunning the rotation that had been added in June for
this same symptom. The record was also wrong: get("EMPIRE_DEBUG") claimed 204
keys when it touched one, which makes the log useless for the only question it
exists to answer.
"""

from __future__ import annotations

import json

import pytest

from lib import secret_loader


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Never touch the real access log or the real cache."""
    monkeypatch.setattr(secret_loader, "ACCESS_LOG", tmp_path / "secret_access.log")
    secret_loader.reset_cache()
    yield
    secret_loader.reset_cache()


def _records() -> list[dict]:
    path = secret_loader.ACCESS_LOG
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


# --- audit record shape -------------------------------------------------------

def test_explicit_required_logs_exactly_those_keys():
    secret_loader.load_env(required=["TURSO_DATABASE_URL"])
    rec = _records()[-1]
    assert rec["keys"] == ["TURSO_DATABASE_URL"]
    assert "key_count" not in rec


def test_get_logs_the_single_key_it_read():
    """The regression that mattered most: get() used to log the whole env."""
    secret_loader.get("EMPIRE_DEBUG", "0")
    rec = _records()[-1]
    assert rec["keys"] == ["EMPIRE_DEBUG"], (
        "get() must audit the key it actually read, not the entire environment")


def test_bare_load_env_logs_a_marker_not_an_enumeration():
    secret_loader.load_env()
    rec = _records()[-1]
    assert rec["keys"] == "<all>"
    assert isinstance(rec["key_count"], int) and rec["key_count"] > 0


def test_bootstrap_logs_a_marker_not_an_enumeration():
    secret_loader.bootstrap()
    rec = _records()[-1]
    assert rec["keys"] == "<all>"


def test_record_stays_small_enough_that_rotation_can_keep_up():
    """Guards the actual failure: 5.2 KB/record outran a 5 MB rotation twice a
    day. A whole-env record must stay in the hundreds of bytes, not thousands."""
    secret_loader.load_env()
    size = len(json.dumps(_records()[-1]))
    assert size < 512, f"whole-env audit record grew back to {size} B/record"


def test_every_access_still_produces_exactly_one_record():
    """Shrinking the record must not mean dropping the audit trail."""
    secret_loader.load_env()
    secret_loader.get("EMPIRE_DEBUG", "0")
    secret_loader.load_env(required=["TURSO_DATABASE_URL"])
    assert len(_records()) == 3


def test_records_carry_ts_and_caller():
    secret_loader.load_env()
    rec = _records()[-1]
    assert rec["ts"] and rec["caller"]
    assert rec["caller"] != "<unknown>", "caller attribution must survive"
    # NOTE: _caller_file() skips any frame whose FULL PATH contains the string
    # "secret_loader", so this test file's own name makes it attribute to
    # pytest's internals rather than here. Harmless for the audit log (real
    # callers are not named secret_loader*) but it is why this asserts on
    # "attributed to something" rather than on this file specifically.


# --- refusals (the security properties) --------------------------------------

def test_refuses_interactive_shell(monkeypatch):
    monkeypatch.setenv("PYTHONINSPECT", "1")
    secret_loader.reset_cache()
    with pytest.raises(secret_loader.SecretLoaderRefused):
        secret_loader.load_env()


def test_missing_required_key_raises_rather_than_returning_empty():
    """A missing credential must fail loudly — the 2026-08 shopping-out outage
    came from a caller that could not tell 'absent' from 'empty'."""
    with pytest.raises(KeyError):
        secret_loader.load_env(required=["DEFINITELY_NOT_A_REAL_KEY_XYZ"])


def test_logging_failure_never_breaks_the_caller(monkeypatch, tmp_path):
    """Audit logging is best-effort; an unwritable state dir must not take down
    every script that needs credentials.

    Points ACCESS_LOG at a path that is a DIRECTORY, so the real `.open("a")`
    inside _log_access raises OSError for real rather than through a mock that
    would also break reading .env.agents.
    """
    blocked = tmp_path / "not_a_file"
    blocked.mkdir()
    monkeypatch.setattr(secret_loader, "ACCESS_LOG", blocked)
    secret_loader.reset_cache()
    env = secret_loader.load_env()
    assert env is not None and len(env) > 0
