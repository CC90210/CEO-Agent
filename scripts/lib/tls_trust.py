"""tls_trust.py — one-call Windows/OS TLS trust setup for every network tool.

The 2026-07-17 CA-bundle lesson: on this Windows fleet, Python's bundled
certifi roots miss what the OS store has, so direct HTTPS calls die with
CERTIFICATE_VERIFY_FAILED (hit Supabase cron/heartbeat first, then
vercel_env_tool). The fix is the OS trust store via `truststore`, with a
certifi env-var fallback — but as of extraction it existed as four separate
inline copies (agent_heartbeat, cron_engine, email_validate_tool,
vercel_env_tool) while 30+ other HTTPS-calling scripts had none.

CANONICAL PATTERN for any script that talks HTTPS (requests/httpx/urllib):

    from lib.tls_trust import ensure_os_trust
    ensure_os_trust()   # call once, before the first network call

Behavior (mirrors agent_heartbeat._configure_ca_bundle, the fullest copy):
- Neutralizes a hostile/unusable SSLKEYLOGFILE (see below) — FIRST, because it
  breaks context construction itself, before any CA question is reached.
- Respects an operator override: if SSL_CERT_FILE or REQUESTS_CA_BUNDLE is
  already set, does nothing.
- Prefers `truststore.inject_into_ssl()` (OS store — the real fix).
- Falls back to pointing SSL_CERT_FILE/REQUESTS_CA_BUNDLE at certifi.
- Never raises; safe to call multiple times.
"""
from __future__ import annotations

import os

_done = False
_keylog_done = False

# ── SSLKEYLOGFILE poisoning (2026-07-29 outage) ──────────────────────────────
#
# The local AV (AVG) sets SSLKEYLOGFILE to a kernel device handle so its TLS
# scanner can log session keys:
#
#     SSLKEYLOGFILE=\\.\avgMonFltProxy\FFFF80838C28E160
#
# CPython's ssl.create_default_context() reads that var unconditionally and
# does `context.keylog_filename = <value>` (Lib/ssl.py). The handle is issued
# per AV session and goes STALE; opening it then raises PermissionError
# [Errno 13] / FileNotFoundError [Errno 2] — from inside SSL context
# construction, i.e. before a single byte is sent.
#
# PM2 makes this lethal rather than transient: the daemon captures the handle
# that was live when IT started and hands that frozen value to every child it
# spawns, forever. bravo-scheduler ran 25h on a dead handle, so every cron
# child that built an httpx/requests client died at construction —
# `Inbound Email Sweep` (31/145 runs), `Funnel Fast-Poll`, and, worst of all,
# notify.py itself, which meant the failures could not even be alerted on.
#
# We never want TLS session keys written to disk in production anyway (anyone
# holding that file can decrypt captured traffic), so the guard is aggressive:
# drop the var unless it points at a path we can actually append to, and let
# EMPIRE_ALLOW_SSLKEYLOG=1 opt back in for deliberate debugging.
_KEYLOG_VAR = "SSLKEYLOGFILE"
_DEVICE_PREFIXES = ("\\\\.\\", "\\\\?\\", "//./", "//?/")


def _keylog_is_usable(raw: str) -> bool:
    """True only if `raw` is a path Python can actually open for appending.

    Deliberately does the real open() rather than inferring from the string:
    the AV handle looks like a plain path to os.path, and a stale handle is
    indistinguishable from a live one until you touch it.
    """
    if not raw:
        return False
    if raw.startswith(_DEVICE_PREFIXES):
        return False
    try:
        parent = os.path.dirname(os.path.abspath(raw))
        if parent and not os.path.isdir(parent):
            return False
        with open(raw, "a", encoding="utf-8"):
            pass
        return True
    except OSError:
        return False


def neutralize_keylog() -> bool:
    """Drop a hostile/unusable SSLKEYLOGFILE from os.environ.

    Returns True if the variable was removed. Idempotent, never raises. Must
    run BEFORE the first ssl.create_default_context() in the process.
    """
    global _keylog_done
    try:
        raw = os.environ.get(_KEYLOG_VAR)
        if not raw:
            _keylog_done = True
            return False
        if (os.environ.get("EMPIRE_ALLOW_SSLKEYLOG") or "").strip() == "1":
            _keylog_done = True
            return False
        if _keylog_is_usable(raw):
            _keylog_done = True
            return False
        os.environ.pop(_KEYLOG_VAR, None)
        _keylog_done = True
        return True
    except Exception:  # noqa: BLE001 — a TLS helper must never break a caller
        return False


def tls_diagnostics() -> dict:
    """Non-mutating snapshot for health checks (machine_parity, harness_eval).

    Reports what the CURRENT process environment looks like — call before
    ensure_os_trust() to see the inherited state, after to confirm the fix.
    """
    raw = os.environ.get(_KEYLOG_VAR)
    return {
        "keylog_present": bool(raw),
        "keylog_value": raw,
        "keylog_usable": _keylog_is_usable(raw) if raw else None,
        "keylog_allowed": (os.environ.get("EMPIRE_ALLOW_SSLKEYLOG") or "").strip() == "1",
        "trust_path": "truststore" if _done else None,
        "ca_override": _genuine_override(),
    }


def _genuine_override() -> str | None:
    """Return an operator-supplied CA bundle path worth honouring, else None.

    The plain "is SSL_CERT_FILE set?" test was too permissive (2026-07-28
    incident). Two paths do NOT represent operator intent and must not
    suppress the OS-store fix:

    * a path that no longer exists — a stale value inherited from a
      long-running parent, not a live choice;
    * certifi's own bundle — that is merely Python's default written out
      explicitly, and on this fleet it is exactly what CANNOT verify the
      AV-scanner-MITM'd chain.

    A real corporate bundle (exists, and isn't certifi's) still wins.

    Both vars are inspected INDEPENDENTLY. An earlier draft used
    `SSL_CERT_FILE or REQUESTS_CA_BUNDLE`, which read only the first non-empty
    one — so a stale SSL_CERT_FILE alongside a valid REQUESTS_CA_BUNDLE was
    judged "not genuine" and the caller then deleted BOTH, destroying a real
    corporate bundle. Either var holding a real bundle now protects both.
    """
    for var in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
        raw = os.environ.get(var)
        if not raw:
            continue
        try:
            candidate = os.path.realpath(raw)
            if not os.path.isfile(candidate):
                continue
            try:
                import certifi  # type: ignore

                if candidate == os.path.realpath(certifi.where()):
                    continue
            except ImportError:
                pass
            return raw
        except OSError:
            continue
    return None


def ensure_os_trust() -> str:
    """Idempotent. Returns which path was taken: 'env-override' | 'truststore'
    | 'certifi' | 'none' (nothing available — system defaults apply).

    Always neutralizes a hostile SSLKEYLOGFILE first — that failure mode kills
    ssl.create_default_context() outright, so it has to be cleared before any
    CA decision matters (and regardless of which CA branch we end up taking).
    """
    global _done
    neutralize_keylog()
    if _genuine_override():
        return "env-override"
    try:
        import truststore  # type: ignore

        if not _done:
            # Injection alone is enough — deliberately NO os.environ mutation.
            # Measured 2026-07-28 on this box: with truststore injected, requests,
            # httpx, and the supabase client all verify successfully even while
            # SSL_CERT_FILE/REQUESTS_CA_BUNDLE still point at certifi. The
            # inherited-env failure was never "the env var beat the injection" —
            # it was the guard above returning early so nothing was injected AT
            # ALL. Popping the vars would therefore buy nothing, while risking
            # deletion of a real corporate bundle for this process and every
            # child that inherits its environment.
            truststore.inject_into_ssl()
            _done = True
        return "truststore"
    except Exception:  # noqa: BLE001 — ImportError or injection failure
        pass
    try:
        import certifi  # type: ignore

        ca_path = certifi.where()
        os.environ.setdefault("SSL_CERT_FILE", ca_path)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", ca_path)
        return "certifi"
    except ImportError:
        return "none"
