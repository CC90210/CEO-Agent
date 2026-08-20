"""Supabase clients must survive AVG cutting their sockets.

Measured 2026-07-30 across the scheduler logs: 92 check-cycle failures, 58 of
them `[WinError 10054] An existing connection was forcibly closed`. Two library
defaults turned a momentary socket kill into a failed cron job — postgrest
builds its transport with retries=0, and its 120s timeout sits INSIDE the
scheduler's 30s child budget, so a stall could only ever surface as the parent
killing the child with no diagnosable error.

These tests assert the configuration is actually applied to a live client, not
that a function ran.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import db_resilience as dbr  # noqa: E402


def _patched_class():
    """supabase's sync Client, or None when supabase isn't installed here."""
    try:
        from supabase._sync.client import SyncClient
        return SyncClient
    except Exception:  # noqa: BLE001
        try:
            from supabase._sync.client import Client
            return Client
        except Exception:  # noqa: BLE001
            return None


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    """Isolate a process-global class patch in BOTH directions.

    install() replaces supabase's Client.__init__ for the whole process.
    importlib.reload() resets this module's _installed flag but cannot touch the
    class, so before this fixture existed:

      inbound  — tests/test_msys_noise_filter.py and tests/test_bridge_script_policy.py
                 pull supabase into sys.modules at COLLECTION time, satisfying
                 install()'s `"supabase" not in sys.modules` guard. Then
                 scripts/tests/test_alert_gating_and_machine_senders.py:156 does
                 `import notify` at RUN time, whose module body calls
                 ensure_os_trust() -> tls_trust._harden_db() -> install(). That
                 file collects at index 1 and this one at index 9, so by the time
                 test_library_defaults_are_the_problem_we_are_fixing ran, the
                 class was already hardened and it saw retries=2. It passed
                 alone and failed in the full suite;
      outbound — this file's own install() calls (below) leaked the patch to
                 every one of the ~940 tests collected after it.

    So: enter every test on the library's OWN __init__, and leave behind exactly
    what we found.
    """
    monkeypatch.delenv("EMPIRE_DB_HARDEN", raising=False)
    # Reload BEFORE uninstall so uninstall() clears the flag on the reloaded
    # module object, not the one we're about to discard.
    importlib.reload(dbr)
    cls = _patched_class()
    entry_init = cls.__init__ if cls is not None else None
    dbr.uninstall()
    try:
        yield
    finally:
        dbr.uninstall()
        if cls is not None and entry_init is not None and cls.__init__ is not entry_init:
            cls.__init__ = entry_init


DUMMY_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRlc3QiLCJyb2xlIjoiYW5vbiIsImlhdCI6MTYwOTQ1OTIwMCwiZXhwIjoyMDE1Mzg1NjAwfQ."
    "signature"
)


def _client():
    """A real legacy Supabase client; construction performs no network call.

    Use the package's internal factory deliberately. The public
    ``supabase.create_client`` is the Turso cutover boundary and is patched in
    normal operation; this resilience helper is retained only for the explicit
    emergency rollback mode and must be tested against the real pinned client.
    """
    from supabase._sync.client import create_client as create_supabase_client

    return create_supabase_client(
        "https://xxxxxxxxxxxx.supabase.co",
        DUMMY_JWT,
    )


# ── the defaults the library ships, which are the bug ────────────────────────

def test_library_defaults_are_the_problem_we_are_fixing():
    """Guard the guard. If a supabase upgrade ever ships sane defaults, this
    fails and tells us the workaround can go — rather than silently persisting
    forever."""
    c = _client()
    d = dbr.diagnostics(c)
    assert d["retries"] == 0, (
        "postgrest now retries by default — re-evaluate whether this module is "
        f"still needed (got {d['retries']})")
    assert "120" in d["timeout"]


# ── hardening a client directly ──────────────────────────────────────────────

def test_harden_applies_retries_and_timeout():
    c = _client()
    changed = dbr.harden_supabase_client(c, retries=3, timeout=17.0)
    assert "postgrest" in changed["transport"], changed
    d = dbr.diagnostics(c)
    assert d["retries"] == 3
    assert "17" in d["timeout"]


def test_timeout_stays_under_the_schedulers_child_budget():
    """The whole point. scheduler.run_script's shortest job budget is 30s; a
    120s client timeout means the parent ALWAYS kills the child first and the
    log never gets a real error message."""
    c = _client()
    dbr.harden_supabase_client(c)
    d = dbr.diagnostics(c)
    value = float(str(d["timeout"]).split("timeout=")[1].rstrip(")"))
    assert value < 30, f"client timeout {value}s is not under the 30s child budget"


def test_harden_never_raises_on_an_unrecognised_client():
    """It reaches into library internals. A supabase upgrade that renames
    `session` must degrade to 'no hardening', never to 'no database'."""
    class Alien:
        postgrest = object()

    changed = dbr.harden_supabase_client(Alien())
    assert changed["transport"] == []      # nothing done
    assert isinstance(changed["errors"], list)


def test_harden_is_safe_on_a_client_with_no_subclients():
    changed = dbr.harden_supabase_client(object())
    assert changed["transport"] == []


# ── the class patch: every client, however constructed ───────────────────────

def test_install_hardens_clients_made_via_a_pre_bound_factory():
    """THE reason this patches the class instead of create_client.

    Modules do `from supabase import create_client` at import time, binding the
    ORIGINAL function — so patching supabase.create_client afterwards is too
    late. Patching the class the factory instantiates catches it anyway.
    """
    import supabase  # noqa: F401  (must be in sys.modules for install())
    from supabase._sync.client import create_client as prebound

    dbr.install()
    d = dbr.diagnostics(prebound("https://xxxxxxxxxxxx.supabase.co", DUMMY_JWT))
    assert d["retries"] == dbr.DEFAULT_RETRIES
    assert str(int(dbr.DEFAULT_TIMEOUT_SEC)) in d["timeout"]


def test_install_patches_the_class_exactly_once():
    """Asserts the INVARIANT, not the return value.

    The class patch outlives a module reload — deliberately, since the class is
    process-global — so install()'s return value depends on whether any earlier
    caller already patched. An order-dependent test would pass or fail on
    pytest's collection order. What must hold is that repeated installs never
    NEST the wrapper: each layer would re-harden on every construction, and a
    stack of them would grow without bound across a long-lived daemon.
    """
    import supabase  # noqa: F401
    cls = _patched_class()
    assert cls is not None

    dbr.install()
    first = cls.__init__
    assert getattr(first, "_empire_hardened", False) is True

    importlib.reload(dbr)          # resets the module flag, not the class
    dbr.install()
    assert cls.__init__ is first, "install() nested a second wrapper"


def test_install_noops_when_supabase_is_not_imported(monkeypatch):
    """Most scripts calling ensure_os_trust() never touch the DB; importing
    supabase for them would add boot cost for nothing."""
    monkeypatch.setitem(sys.modules, "supabase", None)
    monkeypatch.delitem(sys.modules, "supabase", raising=False)
    importlib.reload(dbr)
    assert dbr.install() is False


def test_opt_out_env_var_disables_everything(monkeypatch):
    monkeypatch.setenv("EMPIRE_DB_HARDEN", "0")
    importlib.reload(dbr)
    import supabase  # noqa: F401
    assert dbr.install() is False


# ── the wiring into ensure_os_trust ──────────────────────────────────────────

def test_ensure_os_trust_installs_the_hardening():
    """It is hooked there because that is the fleet's single 'make the network
    work on this machine' entry point — the same AVG interception breaks CA
    verification AND kills sockets."""
    import supabase  # noqa: F401
    from lib.tls_trust import ensure_os_trust

    ensure_os_trust()
    d = dbr.diagnostics(_client())
    assert d["retries"] == dbr.DEFAULT_RETRIES, "ensure_os_trust did not harden"


def test_ensure_os_trust_survives_a_broken_db_resilience(monkeypatch):
    """Hardening is an optimisation. If it throws, every tool on the fleet must
    still start."""
    import lib.tls_trust as tt

    monkeypatch.setattr(dbr, "install", lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setitem(sys.modules, "lib.db_resilience", dbr)
    assert tt.ensure_os_trust() in ("truststore", "certifi", "env-override", "none")
