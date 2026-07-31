"""Make Supabase calls survive this machine's antivirus.

THE PROBLEM, measured 2026-07-30. AVG intercepts TLS on CC's rig and
intermittently kills live sockets. Across the scheduler logs: 92 check-cycle
failures, 58 of them `[WinError 10054] An existing connection was forcibly
closed`, plus SSL UNEXPECTED_EOF, "Server disconnected", and read timeouts.
Supabase is not flaky; the local middlebox is cutting the agent's connections.

Two library defaults turned that into job failures:

  1. postgrest builds its httpx transport with `retries=0`, so a connection
     that dies mid-flight is never retried — even though a killed socket is the
     textbook retryable error.
  2. its client timeout is 120s, while the scheduler gives a child 30s. A stall
     could therefore ONLY ever surface as the parent killing the child, never as
     a clean in-child error with a diagnosable message. That asymmetry is why
     CC's 11:53 page said "timed out after 30s" and nothing else.

WHY PATCH THE CLASS. There are 44 `create_client(url, key)` sites across
scripts/, each in a directory with its own sys.path bootstrap, so editing them
all is 44 chances to break an import for one behaviour change. supabase 2.28.2
exposes no `httpx_client` option, and patching `supabase.create_client` is too
late — modules do `from supabase import create_client` at import time, which
binds the original function. Patching the CLASS that factory instantiates
catches every client however it was built.

httpx's `retries=` is connection-level only: it retries ConnectError /
ConnectTimeout and does NOT retry a request that got a response. That is exactly
the semantics wanted — a killed socket is retried, a failing query is not, and
no write is ever silently re-sent after the server saw it.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Optional

# Connection retries. 2 is deliberate: AVG's kills are momentary, so the first
# retry almost always wins, and a high count would just burn the caller's
# timeout budget before failing.
DEFAULT_RETRIES = int(os.environ.get("EMPIRE_DB_RETRIES", "2"))

# Must stay BELOW the tightest caller budget or the caller kills the child first
# and we learn nothing. scheduler.run_script's shortest job timeout is 30s.
DEFAULT_TIMEOUT_SEC = float(os.environ.get("EMPIRE_DB_TIMEOUT_SEC", "25"))

_installed = False


def _disabled() -> bool:
    return (os.environ.get("EMPIRE_DB_HARDEN") or "").strip().lower() in (
        "0", "false", "no", "off",
    )


def harden_supabase_client(
    client: Any,
    *,
    retries: int = DEFAULT_RETRIES,
    timeout: Optional[float] = DEFAULT_TIMEOUT_SEC,
) -> dict:
    """Give one client's HTTP sessions connection retries and a sane timeout.

    Best-effort by contract: reaches into library internals, so every step is
    guarded individually. A supabase upgrade that renames `session` must degrade
    to "no hardening", never to "no database". Returns what it actually changed
    so callers and tests can assert on it rather than trust it.
    """
    changed = {"transport": [], "timeout": [], "errors": []}
    try:
        import httpx
    except Exception as exc:  # noqa: BLE001
        changed["errors"].append(f"httpx unavailable: {exc}")
        return changed

    # postgrest is the one that matters (every .table() call); storage and auth
    # are hardened too because they fail the same way for the same reason.
    for name in ("postgrest", "storage", "functions"):
        sub = getattr(client, name, None)
        if sub is None:
            continue
        session = getattr(sub, "session", None)
        if session is None:
            continue
        try:
            session._transport = httpx.HTTPTransport(retries=retries)
            changed["transport"].append(name)
        except Exception as exc:  # noqa: BLE001
            changed["errors"].append(f"{name} transport: {exc}")
        if timeout is not None:
            try:
                session.timeout = httpx.Timeout(timeout)
                changed["timeout"].append(name)
            except Exception as exc:  # noqa: BLE001
                changed["errors"].append(f"{name} timeout: {exc}")
    return changed


def install(
    *,
    retries: int = DEFAULT_RETRIES,
    timeout: Optional[float] = DEFAULT_TIMEOUT_SEC,
) -> bool:
    """Harden every Supabase client created from here on. Idempotent.

    No-ops when supabase is not imported — most scripts that call
    ensure_os_trust() never touch the database, and importing supabase for them
    would add boot cost for nothing. Anything that DOES use it has imported the
    module before it can construct a client.
    """
    global _installed
    if _installed or _disabled():
        return False
    if "supabase" not in sys.modules:
        return False
    try:
        from supabase._sync.client import Client as SyncClient
    except Exception:  # noqa: BLE001
        return False

    original_init = SyncClient.__init__
    if getattr(original_init, "_empire_hardened", False):
        _installed = True
        return False

    def _init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        original_init(self, *args, **kwargs)
        try:
            harden_supabase_client(self, retries=retries, timeout=timeout)
        except Exception:  # noqa: BLE001
            pass  # a hardening failure must never break client construction

    _init._empire_hardened = True  # type: ignore[attr-defined]
    SyncClient.__init__ = _init  # type: ignore[method-assign]
    _installed = True
    return True


def diagnostics(client: Any) -> dict:
    """What a live client is actually configured with — for harness checks."""
    out: dict = {}
    session = getattr(getattr(client, "postgrest", None), "session", None)
    if session is None:
        return {"postgrest_session": None}
    transport = getattr(session, "_transport", None)
    out["transport"] = type(transport).__name__ if transport else None
    out["retries"] = getattr(getattr(transport, "_pool", None), "_retries", None)
    out["timeout"] = str(getattr(session, "timeout", None))
    return out
